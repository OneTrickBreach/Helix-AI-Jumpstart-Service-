"""Shared optimization and scoring helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass

import polars as pl

from src.ingest.state import ScenarioState


@dataclass(frozen=True)
class PolicyParams:
    safety_stock_multiplier: float = 1.0
    order_up_to_multiplier: float = 1.0
    order_batch_multiplier: float = 1.0


def sku_costs(state: ScenarioState) -> dict[str, dict[str, float]]:
    rows = state.skus.select(
        "sku_id",
        "unit_holding_cost",
        "ordering_cost",
        "backorder_penalty",
        "lost_sale_penalty",
    ).to_dicts()
    return {row["sku_id"]: {k: float(v) for k, v in row.items() if k != "sku_id"} for row in rows}


def service_targets(state: ScenarioState) -> dict[tuple[str, str], dict[str, float]]:
    rows = state.service_targets.select(
        "customer_id",
        "sku_id",
        "fill_rate_target",
        "days_inventory_target",
    ).to_dicts()
    return {
        (row["customer_id"], row["sku_id"]): {
            "fill_rate_target": float(row["fill_rate_target"]),
            "days_inventory_target": float(row["days_inventory_target"]),
        }
        for row in rows
    }


def lane_lookup(state: ScenarioState) -> dict[str, dict]:
    return {row["lane_id"]: row for row in state.lanes.to_dicts()}


def select_greedy_lanes(state: ScenarioState) -> dict[str, dict]:
    latest_period = state.horizon()
    periods = state.lane_periods.filter(pl.col("period") == latest_period).select(
        "lane_id", "effective_capacity_units", "effective_lead_time_mean_days"
    )
    merged = state.lanes.join(periods, on="lane_id", how="left")
    assignments: dict[str, dict] = {}
    for lane_type in ["inbound_raw", "plant_to_dc", "dc_to_customer"]:
        frame = merged.filter(
            (pl.col("lane_type") == lane_type)
            & (pl.col("effective_capacity_units").fill_null(pl.col("capacity_units_per_period")) > 0)
        )
        if frame.is_empty():
            continue
        frame = frame.with_columns(
            (
                pl.col("lane_cost_per_unit")
                + (pl.col("distance_km") * pl.col("transport_cost_per_km"))
                + (pl.col("effective_lead_time_mean_days").fill_null(pl.col("lead_time_mean_days")) * 0.05)
            ).alias("route_score")
        ).sort(["route_score", "lane_ordinal"])
        row = frame.row(0, named=True)
        assignments[lane_type] = {
            "lane_id": row["lane_id"],
            "from_node_id": row["from_node_id"],
            "to_node_id": row["to_node_id"],
            "lane_type": lane_type,
            "effective_lead_time_days": float(row["effective_lead_time_mean_days"] or row["lead_time_mean_days"]),
            "cost_per_unit": float(row["lane_cost_per_unit"])
            + float(row["distance_km"]) * float(row["transport_cost_per_km"]),
            "engine": "greedy_shortest_route",
        }
    return assignments


def _required_flow_by_lane_type(state: ScenarioState) -> dict[str, float]:
    horizon = max(1, state.horizon())
    finished_total = float(
        state.demand.filter(pl.col("demand_type") == "finished_good_customer")
        .select(pl.sum("quantity_units"))
        .item()
        or 0.0
    )
    raw_component_ids = set(
        state.skus.filter(pl.col("sku_type") == "raw_component").select("sku_id").to_series().to_list()
    )
    raw_total = float(
        state.demand.filter(
            (pl.col("demand_type") == "derived_component") & pl.col("sku_id").is_in(raw_component_ids)
        )
        .select(pl.sum("quantity_units"))
        .item()
        or 0.0
    )
    finished_per_period = finished_total / horizon
    return {
        "inbound_raw": raw_total / horizon,
        "plant_to_dc": finished_per_period,
        "dc_to_customer": finished_per_period,
    }


def select_ortools_lanes(state: ScenarioState) -> dict[str, dict]:
    """Capacitated min-cost lane allocation solved with OR-Tools `linear_solver`.

    `select_greedy_lanes` always commits 100% of the required flow to the
    single cheapest lane per type, even when that lane cannot carry the
    volume. This solves a small transportation LP per lane type instead:
    split the required period flow across all candidate lanes to minimize
    total cost subject to each lane's effective capacity. This is what
    actually differentiates the OR-Tools/cuOpt-fallback routing posture from
    the greedy baseline, and it matters most when a shock scenario drives a
    lane's effective capacity to zero.
    """
    from ortools.linear_solver import pywraplp

    latest_period = state.horizon()
    periods = state.lane_periods.filter(pl.col("period") == latest_period).select(
        "lane_id", "effective_capacity_units", "effective_lead_time_mean_days"
    )
    merged = (
        state.lanes.join(periods, on="lane_id", how="left")
        .with_columns(
            pl.col("effective_capacity_units").fill_null(pl.col("capacity_units_per_period")).alias("capacity"),
            pl.col("effective_lead_time_mean_days").fill_null(pl.col("lead_time_mean_days")).alias("lead_time"),
        )
        .with_columns(
            (pl.col("lane_cost_per_unit") + pl.col("distance_km") * pl.col("transport_cost_per_km")).alias(
                "unit_cost"
            )
        )
    )
    required_flow = _required_flow_by_lane_type(state)

    assignments: dict[str, dict] = {}
    for lane_type in ["inbound_raw", "plant_to_dc", "dc_to_customer"]:
        frame = merged.filter(pl.col("lane_type") == lane_type)
        if frame.is_empty():
            continue
        candidates = frame.to_dicts()
        total_capacity = sum(max(0.0, float(c["capacity"])) for c in candidates)
        if total_capacity <= 0:
            continue

        demand = max(0.0, required_flow.get(lane_type, 0.0))
        flows = [0.0 for _ in candidates]
        solved = False
        if demand > 0:
            solver = pywraplp.Solver.CreateSolver("GLOP")
            if solver is not None:
                flow_vars = [
                    solver.NumVar(0.0, max(0.0, float(c["capacity"])), f"flow_{i}")
                    for i, c in enumerate(candidates)
                ]
                solver.Add(solver.Sum(flow_vars) >= min(demand, total_capacity))
                solver.Minimize(solver.Sum(v * float(c["unit_cost"]) for v, c in zip(flow_vars, candidates)))
                status = solver.Solve()
                if status == pywraplp.Solver.OPTIMAL:
                    flows = [v.solution_value() for v in flow_vars]
                    solved = True

        if not solved:
            feasible = [c for c in candidates if float(c["capacity"]) > 0]
            cheapest = min(feasible, key=lambda c: c["unit_cost"])
            flows = [demand if c is cheapest else 0.0 for c in candidates]

        total_flow = sum(flows)
        if total_flow > 0:
            weighted_cost = sum(f * c["unit_cost"] for f, c in zip(flows, candidates)) / total_flow
            weighted_lead = sum(f * c["lead_time"] for f, c in zip(flows, candidates)) / total_flow
            primary = candidates[max(range(len(candidates)), key=lambda i: flows[i])]
        else:
            primary = min(candidates, key=lambda c: c["unit_cost"])
            weighted_cost = float(primary["unit_cost"])
            weighted_lead = float(primary["lead_time"])

        assignments[lane_type] = {
            "lane_id": primary["lane_id"],
            "from_node_id": primary["from_node_id"],
            "to_node_id": primary["to_node_id"],
            "lane_type": lane_type,
            "effective_lead_time_days": float(weighted_lead),
            "cost_per_unit": float(weighted_cost),
            "engine": "ortools_transportation_lp",
            "required_flow_units": round(demand, 6),
            "lane_splits": [
                {"lane_id": c["lane_id"], "flow_units": round(f, 6)}
                for c, f in zip(candidates, flows)
                if f > 1e-9
            ],
        }
    return assignments


def build_plan(
    state: ScenarioState,
    forecast: dict,
    params: PolicyParams,
    method: str,
    lane_engine: str,
) -> dict:
    costs = sku_costs(state)
    targets = service_targets(state)
    inventory = {
        (row["node_id"], row["sku_id"]): float(row["on_hand_units"] + row["in_transit_units"] - row["backlog_units"])
        for row in state.initial_inventory.to_dicts()
    }
    lanes = select_ortools_lanes(state) if lane_engine != "greedy" else select_greedy_lanes(state)
    avg_transport_cost = (
        sum(row["cost_per_unit"] for row in lanes.values()) / len(lanes) if lanes else 0.0
    )

    plan_rows: list[dict] = []
    total_demand = total_order = total_inventory_position = 0.0
    holding = ordering = backorder = lost_sale = transport = 0.0

    forecast_by_series: dict[tuple[str, str], list[float]] = {}
    for row in forecast["rows"]:
        forecast_by_series.setdefault((row["customer_id"], row["sku_id"]), []).append(
            float(row["forecast_quantity_units"])
        )

    for key, quantities in sorted(forecast_by_series.items()):
        customer_id, sku_id = key
        mean_demand = sum(quantities) / len(quantities) if quantities else 0.0
        variance = sum((q - mean_demand) ** 2 for q in quantities) / len(quantities) if quantities else 0.0
        std = math.sqrt(variance)
        target = targets.get(key, {"fill_rate_target": 0.95, "days_inventory_target": 14.0})
        lead_time_periods = max(1.0, sum(l["effective_lead_time_days"] for l in lanes.values()) / (7.0 * max(len(lanes), 1)))
        safety_stock = params.safety_stock_multiplier * target["fill_rate_target"] * std * math.sqrt(lead_time_periods)
        reorder_point = (mean_demand * lead_time_periods) + safety_stock
        order_up_to = reorder_point + (mean_demand * max(1.0, params.order_up_to_multiplier))
        starting_position = max(0.0, inventory.get(key, 0.0))
        cost = costs[sku_id]

        # Simulate the (s, S) policy period-by-period across the forecast
        # horizon instead of a single day-0 snapshot. A single snapshot check
        # (order_up_to - starting_position) is insensitive to every tunable
        # parameter whenever starting inventory alone already covers the
        # horizon (common here, since initial stock is provisioned against a
        # days-of-inventory target) — every policy then computes the exact
        # same zero order quantity, making baseline/classical/PPO identical
        # by construction. Rolling forward period-by-period is what actually
        # lets safety-stock/order-up-to/batch tuning change the outcome.
        lead_time_steps = max(0, round(lead_time_periods))
        on_hand = starting_position
        pending_receipts: dict[int, float] = {}
        series_order_qty = 0.0
        series_ordering_cost = 0.0
        series_holding_cost = 0.0
        series_backorder_cost = 0.0
        series_lost_sale_cost = 0.0
        series_fulfilled = 0.0
        series_demand = 0.0
        ending_inventory = starting_position

        for step, demand_t in enumerate(quantities, start=1):
            on_hand += pending_receipts.pop(step, 0.0)
            position = on_hand + sum(pending_receipts.values())
            order_qty = 0.0
            if position <= reorder_point:
                order_qty = max(0.0, order_up_to - position) * max(0.1, params.order_batch_multiplier)
            if order_qty > 0:
                arrival_step = step + lead_time_steps
                pending_receipts[arrival_step] = pending_receipts.get(arrival_step, 0.0) + order_qty
                series_ordering_cost += cost["ordering_cost"]
                series_order_qty += order_qty

            fulfilled = min(demand_t, on_hand)
            shortage = max(0.0, demand_t - on_hand)
            on_hand = max(0.0, on_hand - demand_t)

            series_holding_cost += on_hand * cost["unit_holding_cost"]
            series_backorder_cost += shortage * cost["backorder_penalty"] * 0.65
            series_lost_sale_cost += shortage * cost["lost_sale_penalty"] * 0.35
            series_fulfilled += fulfilled
            series_demand += demand_t
            ending_inventory = on_hand

        fill_rate = series_fulfilled / series_demand if series_demand else 1.0

        holding += series_holding_cost
        ordering += series_ordering_cost
        backorder += series_backorder_cost
        lost_sale += series_lost_sale_cost
        transport += series_order_qty * avg_transport_cost
        total_demand += mean_demand
        total_order += series_order_qty
        total_inventory_position += ending_inventory

        plan_rows.append(
            {
                "customer_id": customer_id,
                "sku_id": sku_id,
                "mean_forecast_units": round(mean_demand, 6),
                "inventory_position_units": round(starting_position, 6),
                "reorder_point_units": round(reorder_point, 6),
                "order_up_to_units": round(order_up_to, 6),
                "order_quantity_units": round(series_order_qty, 6),
                "projected_fill_rate": round(fill_rate, 6),
                "ending_inventory_units": round(ending_inventory, 6),
            }
        )

    fill_rate = (
        sum(row["projected_fill_rate"] * row["mean_forecast_units"] for row in plan_rows)
        / total_demand
        if total_demand
        else 1.0
    )
    days_inventory = (total_inventory_position / total_demand * 7.0) if total_demand else 0.0
    cost_breakdown = {
        "holding": round(holding, 6),
        "ordering": round(ordering, 6),
        "backorder": round(backorder, 6),
        "lost_sale": round(lost_sale, 6),
        "transport": round(transport, 6),
    }
    total_cost = round(sum(cost_breakdown.values()), 6)
    return {
        "scenario": state.scenario,
        "method": method,
        "policy": {
            "safety_stock_multiplier": params.safety_stock_multiplier,
            "order_up_to_multiplier": params.order_up_to_multiplier,
            "order_batch_multiplier": params.order_batch_multiplier,
        },
        "plan": plan_rows,
        "lane_assignments": list(lanes.values()),
        "metrics": {
            "cost_breakdown": cost_breakdown,
            "total_cost": total_cost,
            "fill_rate": round(fill_rate, 6),
            "days_of_inventory": round(days_inventory, 6),
            "total_order_units": round(total_order, 6),
            "objective": round(total_cost + max(0.0, 0.95 - fill_rate) * 100000.0, 6),
        },
    }
