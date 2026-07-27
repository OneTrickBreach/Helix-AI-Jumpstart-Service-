"""Per-period multi-echelon inventory MDP for PPO.

The agent observes current inventory state each period and outputs adaptive
(s,S) policy multipliers.  Unlike the old whole-horizon parameter search,
this is a true sequential decision process: on_hand depletes, orders arrive
after lead-time, and the agent can react to demand shocks as they happen.
"""

from __future__ import annotations

import math

import numpy as np

try:
    import gymnasium as gym
    from gymnasium import spaces
except Exception:  # pragma: no cover
    gym = None
    spaces = None

from src.forecast.statistical import forecast_finished_goods
from src.ingest.state import ScenarioState
from src.optimize.common import (
    compute_cvar,
    select_ortools_lanes,
    service_targets,
    sku_costs,
)


class MultiEchelonInventoryEnv(gym.Env if gym else object):
    metadata = {"render_modes": []}

    def __init__(self, state: ScenarioState, horizon: int = 8):
        self.scenario_state = state
        self.horizon = horizon
        self.forecast = forecast_finished_goods(state, horizon=horizon)

        self.series = sorted(
            {(r["customer_id"], r["sku_id"]) for r in self.forecast["rows"]}
        )
        self.n_series = max(1, len(self.series))
        self.series_idx = {key: i for i, key in enumerate(self.series)}

        forecast_by_series: dict[tuple[str, str], list[float]] = {}
        for row in self.forecast["rows"]:
            key = (row["customer_id"], row["sku_id"])
            forecast_by_series.setdefault(key, []).append(
                float(row["forecast_quantity_units"])
            )

        self.demand_matrix = np.zeros((horizon, self.n_series), dtype=np.float64)
        for key in self.series:
            i = self.series_idx[key]
            for t, q in enumerate(forecast_by_series.get(key, [])[:horizon]):
                self.demand_matrix[t, i] = q

        self.mean_demand = np.mean(self.demand_matrix, axis=0)
        self.std_demand = np.std(self.demand_matrix, axis=0)

        costs = sku_costs(state)
        targets = service_targets(state)
        self.holding_cost = np.zeros(self.n_series, dtype=np.float64)
        self.ordering_cost = np.zeros(self.n_series, dtype=np.float64)
        self.backorder_penalty = np.zeros(self.n_series, dtype=np.float64)
        self.lost_sale_penalty = np.zeros(self.n_series, dtype=np.float64)
        self.fill_rate_target = np.zeros(self.n_series, dtype=np.float64)
        for key in self.series:
            customer_id, sku_id = key
            i = self.series_idx[key]
            c = costs[sku_id]
            tgt = targets.get(key, {"fill_rate_target": 0.95})
            self.holding_cost[i] = c["unit_holding_cost"]
            self.ordering_cost[i] = c["ordering_cost"]
            self.backorder_penalty[i] = c["backorder_penalty"]
            self.lost_sale_penalty[i] = c["lost_sale_penalty"]
            self.fill_rate_target[i] = tgt["fill_rate_target"]

        self.lanes = select_ortools_lanes(state)
        self.avg_transport_cost = (
            sum(r["cost_per_unit"] for r in self.lanes.values()) / len(self.lanes)
            if self.lanes
            else 0.0
        )
        self.lead_time_periods = max(
            1.0,
            sum(l["effective_lead_time_days"] for l in self.lanes.values())
            / (7.0 * max(len(self.lanes), 1)),
        )
        self.lead_time_steps = max(0, round(self.lead_time_periods))

        inventory = {
            (row["node_id"], row["sku_id"]): float(
                row["on_hand_units"] + row["in_transit_units"] - row["backlog_units"]
            )
            for row in state.initial_inventory.to_dicts()
        }
        self.initial_on_hand = np.array(
            [max(0.0, inventory.get(k, 0.0)) for k in self.series], dtype=np.float64
        )

        self.norm_scale = np.maximum(self.mean_demand, 1.0)

        obs_dim = self.n_series * 4 + 1
        if spaces:
            self.observation_space = spaces.Box(
                low=-10.0, high=10.0, shape=(obs_dim,), dtype=np.float32
            )
            self.action_space = spaces.Box(
                low=0.65, high=1.45, shape=(3,), dtype=np.float32
            )

    # ------------------------------------------------------------------
    def reset(self, *, seed: int | None = None, options: dict | None = None):
        if seed is not None and gym:
            super().reset(seed=seed)

        self.t = 0
        self.on_hand = self.initial_on_hand.copy()
        self.pending_receipts: dict[int, np.ndarray] = {}
        self.cum_fulfilled = np.zeros(self.n_series, dtype=np.float64)
        self.cum_demand = np.zeros(self.n_series, dtype=np.float64)
        self.period_costs: list[float] = []

        self.ep_orders = np.zeros(self.n_series, dtype=np.float64)
        self.ep_ordering = np.zeros(self.n_series, dtype=np.float64)
        self.ep_holding = np.zeros(self.n_series, dtype=np.float64)
        self.ep_backorder = np.zeros(self.n_series, dtype=np.float64)
        self.ep_lost_sale = np.zeros(self.n_series, dtype=np.float64)
        self.ep_actions: list[list[float]] = []

        return self._obs(), {}

    # ------------------------------------------------------------------
    def _obs(self) -> np.ndarray:
        pipeline = np.zeros(self.n_series, dtype=np.float64)
        for arr in self.pending_receipts.values():
            pipeline += arr

        with np.errstate(divide="ignore", invalid="ignore"):
            fill = np.where(
                self.cum_demand > 0,
                self.cum_fulfilled / self.cum_demand,
                np.ones(self.n_series),
            )

        demand_next = (
            self.demand_matrix[self.t]
            if self.t < self.horizon
            else np.zeros(self.n_series)
        )

        obs = np.concatenate(
            [
                self.on_hand / self.norm_scale,
                pipeline / self.norm_scale,
                demand_next / self.norm_scale,
                fill,
                [self.t / max(1, self.horizon)],
            ]
        )
        return obs.astype(np.float32)

    # ------------------------------------------------------------------
    def step(self, action):
        action = np.asarray(action, dtype=np.float32).reshape(-1)
        if action.size < 3:
            action = np.pad(action, (0, 3 - action.size), constant_values=1.0)

        ssm = float(np.clip(action[0], 0.65, 1.45))
        outm = float(np.clip(action[1], 0.65, 1.45))
        obm = float(np.clip(action[2], 0.65, 1.45))
        self.ep_actions.append([ssm, outm, obm])

        step_1 = self.t + 1  # 1-indexed, matching build_plan convention

        arrivals = self.pending_receipts.pop(step_1, None)
        if arrivals is not None:
            self.on_hand += arrivals

        period_cost = 0.0
        for i in range(self.n_series):
            safety = (
                ssm
                * self.fill_rate_target[i]
                * self.std_demand[i]
                * math.sqrt(self.lead_time_periods)
            )
            reorder_pt = self.mean_demand[i] * self.lead_time_periods + safety
            order_up_to = reorder_pt + self.mean_demand[i] * max(1.0, outm)

            position = self.on_hand[i] + sum(
                a[i] for a in self.pending_receipts.values()
            )
            order_qty = 0.0
            if position <= reorder_pt:
                order_qty = max(0.0, order_up_to - position) * max(0.1, obm)

            if order_qty > 0:
                arr_step = step_1 + self.lead_time_steps
                if arr_step not in self.pending_receipts:
                    self.pending_receipts[arr_step] = np.zeros(
                        self.n_series, dtype=np.float64
                    )
                self.pending_receipts[arr_step][i] += order_qty
                self.ep_ordering[i] += self.ordering_cost[i]
                self.ep_orders[i] += order_qty
                period_cost += self.ordering_cost[i]
                period_cost += order_qty * self.avg_transport_cost

            demand_t = self.demand_matrix[self.t, i]
            fulfilled = min(demand_t, self.on_hand[i])
            shortage = max(0.0, demand_t - self.on_hand[i])
            self.on_hand[i] = max(0.0, self.on_hand[i] - demand_t)

            self.cum_fulfilled[i] += fulfilled
            self.cum_demand[i] += demand_t

            h = self.on_hand[i] * self.holding_cost[i]
            b = shortage * self.backorder_penalty[i] * 0.65
            ls = shortage * self.lost_sale_penalty[i] * 0.35
            period_cost += h + b + ls
            self.ep_holding[i] += h
            self.ep_backorder[i] += b
            self.ep_lost_sale[i] += ls

        self.period_costs.append(period_cost)
        self.t += 1
        terminated = self.t >= self.horizon

        return self._obs(), float(-period_cost), terminated, False, {
            "period_cost": period_cost
        }

    # ------------------------------------------------------------------
    def extract_plan(self) -> dict:
        """Build a benchmark-compatible plan dict from the completed episode."""
        plan_rows: list[dict] = []
        total_demand = total_order = total_inv = 0.0

        for i, (cust, sku) in enumerate(self.series):
            fr = (
                float(self.cum_fulfilled[i] / self.cum_demand[i])
                if self.cum_demand[i] > 0
                else 1.0
            )
            plan_rows.append(
                {
                    "customer_id": cust,
                    "sku_id": sku,
                    "mean_forecast_units": round(float(self.mean_demand[i]), 6),
                    "inventory_position_units": round(
                        float(self.initial_on_hand[i]), 6
                    ),
                    "reorder_point_units": 0.0,
                    "order_up_to_units": 0.0,
                    "order_quantity_units": round(float(self.ep_orders[i]), 6),
                    "projected_fill_rate": round(fr, 6),
                    "ending_inventory_units": round(float(self.on_hand[i]), 6),
                }
            )
            total_demand += float(self.mean_demand[i])
            total_order += float(self.ep_orders[i])
            total_inv += float(self.on_hand[i])

        fill_rate = (
            sum(r["projected_fill_rate"] * r["mean_forecast_units"] for r in plan_rows)
            / total_demand
            if total_demand
            else 1.0
        )

        holding = float(self.ep_holding.sum())
        ordering = float(self.ep_ordering.sum())
        backorder = float(self.ep_backorder.sum())
        lost_sale = float(self.ep_lost_sale.sum())
        transport = round(float(self.ep_orders.sum()) * self.avg_transport_cost, 6)

        cost_breakdown = {
            "holding": round(holding, 6),
            "ordering": round(ordering, 6),
            "backorder": round(backorder, 6),
            "lost_sale": round(lost_sale, 6),
            "transport": transport,
        }
        total_cost = round(sum(cost_breakdown.values()), 6)
        days_inv = (total_inv / total_demand * 7.0) if total_demand else 0.0

        mean_act = (
            np.mean(self.ep_actions, axis=0).tolist()
            if self.ep_actions
            else [1.0, 1.0, 1.0]
        )
        period_costs_rounded = [round(c, 6) for c in self.period_costs]

        return {
            "scenario": self.scenario_state.scenario,
            "method": "ppo_candidate",
            "policy": {
                "safety_stock_multiplier": round(float(mean_act[0]), 6),
                "order_up_to_multiplier": round(float(mean_act[1]), 6),
                "order_batch_multiplier": round(float(mean_act[2]), 6),
                "adaptive": True,
                "per_period_actions": [
                    [round(a, 4) for a in act] for act in self.ep_actions
                ],
            },
            "plan": plan_rows,
            "lane_assignments": list(self.lanes.values()),
            "metrics": {
                "cost_breakdown": cost_breakdown,
                "total_cost": total_cost,
                "fill_rate": round(fill_rate, 6),
                "days_of_inventory": round(days_inv, 6),
                "total_order_units": round(total_order, 6),
                "objective": round(
                    total_cost + max(0.0, 0.95 - fill_rate) * 100000.0, 6
                ),
                "period_costs": period_costs_rounded,
                "cvar_75": round(compute_cvar(period_costs_rounded, 0.75), 6),
            },
        }
