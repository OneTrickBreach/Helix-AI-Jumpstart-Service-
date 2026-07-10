#!/usr/bin/env python3
"""Generate seeded synthetic Manufacturing SCO data.

The generator is intentionally CPU-only and deterministic. It uses a local NumPy
Generator instance, stable ID ordering, fixed float formatting, and no timestamps.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"
DEFAULT_SEED = 12345


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def load_scenario(name: str) -> dict[str, Any]:
    path = SCENARIO_DIR / f"{name}.yaml"
    if not path.exists():
        available = ", ".join(sorted(p.stem for p in SCENARIO_DIR.glob("*.yaml")))
        raise SystemExit(f"Unknown scenario '{name}'. Available scenarios: {available}")
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise SystemExit(f"Scenario config is invalid: {path}")
    if config.get("scenario") != name:
        raise SystemExit(f"Scenario file {path} must declare scenario: {name}")
    return config


def fmt(value: Any) -> Any:
    if isinstance(value, (np.floating, float)):
        return f"{float(value):.6f}"
    if isinstance(value, (np.integer, int)):
        return str(int(value))
    if value is None:
        return ""
    return str(value)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: fmt(row.get(field, "")) for field in fieldnames})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def tagged(row: dict[str, Any], scenario: str, seed: int) -> dict[str, Any]:
    return {**row, "scenario": scenario, "seed": seed}


def periods_from_shock(shock: dict[str, Any] | None) -> set[int]:
    if not shock:
        return set()
    start = int(shock.get("start_period", 0))
    duration = int(shock.get("duration_periods", 0))
    return set(range(start, start + duration))


def build_skus_and_bom(
    config: dict[str, Any],
    rng: np.random.Generator,
    scenario: str,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str], list[str]]:
    size = config["network"]
    costs = config["costs"]
    fg_count = int(size["finished_goods"])
    sa_per_fg = int(size["subassemblies_per_finished_good"])
    rc_per_sa = int(size["raw_components_per_subassembly"])

    skus: list[dict[str, Any]] = []
    bom: list[dict[str, Any]] = []
    finished_goods: list[str] = []
    subassemblies: list[str] = []
    raw_components: list[str] = []

    for fg_idx in range(1, fg_count + 1):
        fg_id = f"FG-{fg_idx:03d}"
        finished_goods.append(fg_id)
        skus.append(
            tagged(
                {
                    "sku_id": fg_id,
                    "sku_type": "finished_good",
                    "description": f"Synthetic finished good {fg_idx:03d}",
                    "unit_holding_cost": costs["holding_cost"]["finished_good"],
                    "ordering_cost": costs["ordering_cost"]["finished_good"],
                    "backorder_penalty": costs["backorder_penalty"]["finished_good"],
                    "lost_sale_penalty": costs["lost_sale_penalty"]["finished_good"],
                    "production_cost": round(float(rng.uniform(18.0, 42.0)), 6),
                    "unit_volume_cubic_m": round(float(rng.uniform(0.05, 0.18)), 6),
                },
                scenario,
                seed,
            )
        )

        for sa_idx in range(1, sa_per_fg + 1):
            sa_global = (fg_idx - 1) * sa_per_fg + sa_idx
            sa_id = f"SA-{sa_global:03d}"
            subassemblies.append(sa_id)
            skus.append(
                tagged(
                    {
                        "sku_id": sa_id,
                        "sku_type": "subassembly",
                        "description": f"Synthetic subassembly {sa_global:03d}",
                        "unit_holding_cost": costs["holding_cost"]["subassembly"],
                        "ordering_cost": costs["ordering_cost"]["subassembly"],
                        "backorder_penalty": costs["backorder_penalty"]["subassembly"],
                        "lost_sale_penalty": costs["lost_sale_penalty"]["subassembly"],
                        "production_cost": round(float(rng.uniform(5.0, 15.0)), 6),
                        "unit_volume_cubic_m": round(float(rng.uniform(0.01, 0.06)), 6),
                    },
                    scenario,
                    seed,
                )
            )
            bom.append(
                tagged(
                    {
                        "parent_sku_id": fg_id,
                        "component_sku_id": sa_id,
                        "quantity_per_parent": int(rng.integers(1, 4)),
                        "tier_depth": 1,
                    },
                    scenario,
                    seed,
                )
            )

            for rc_idx in range(1, rc_per_sa + 1):
                rc_global = (sa_global - 1) * rc_per_sa + rc_idx
                rc_id = f"RC-{rc_global:003d}"
                raw_components.append(rc_id)
                skus.append(
                    tagged(
                        {
                            "sku_id": rc_id,
                            "sku_type": "raw_component",
                            "description": f"Synthetic raw component {rc_global:03d}",
                            "unit_holding_cost": costs["holding_cost"]["raw_component"],
                            "ordering_cost": costs["ordering_cost"]["raw_component"],
                            "backorder_penalty": costs["backorder_penalty"]["raw_component"],
                            "lost_sale_penalty": costs["lost_sale_penalty"]["raw_component"],
                            "production_cost": 0.0,
                            "unit_volume_cubic_m": round(float(rng.uniform(0.002, 0.025)), 6),
                        },
                        scenario,
                        seed,
                    )
                )
                bom.append(
                    tagged(
                        {
                            "parent_sku_id": sa_id,
                            "component_sku_id": rc_id,
                            "quantity_per_parent": int(rng.integers(1, 5)),
                            "tier_depth": 2,
                        },
                        scenario,
                        seed,
                    )
                )

    return skus, bom, finished_goods, subassemblies, raw_components


def build_nodes(config: dict[str, Any], scenario: str, seed: int) -> list[dict[str, Any]]:
    size = config["network"]
    nodes: list[dict[str, Any]] = []
    specs = [
        ("supplier", "SUP", int(size["suppliers"])),
        ("plant", "PLANT", int(size["plants"])),
        ("distribution_center", "DC", int(size["distribution_centers"])),
        ("customer", "CUST", int(size["customers"])),
    ]
    for node_type, prefix, count in specs:
        for idx in range(1, count + 1):
            nodes.append(
                tagged(
                    {
                        "node_id": f"{prefix}-{idx:03d}",
                        "node_type": node_type,
                        "name": f"Synthetic {node_type.replace('_', ' ')} {idx:03d}",
                        "region": f"Region-{((idx - 1) % 4) + 1}",
                        "capacity_units_per_period": 0,
                        "storage_capacity_units": 0,
                    },
                    scenario,
                    seed,
                )
            )
    return nodes


def build_finished_good_demand(
    config: dict[str, Any],
    rng: np.random.Generator,
    scenario: str,
    seed: int,
    finished_goods: list[str],
) -> tuple[list[dict[str, Any]], dict[tuple[int, str], int]]:
    demand_cfg = config["demand"]
    horizon = int(config["simulation"]["horizon_periods"])
    customers = [f"CUST-{idx:03d}" for idx in range(1, int(config["network"]["customers"]) + 1)]
    base = float(demand_cfg["base_units_per_customer_period"])
    seasonal_amp = float(demand_cfg["seasonality_amplitude"])
    trend = float(demand_cfg["trend_per_period"])
    noise_std = float(demand_cfg["noise_std"])
    lump_probability = float(demand_cfg["lump_probability"])
    lump_low, lump_high = demand_cfg["lump_multiplier_range"]
    periods_per_year = int(demand_cfg.get("periods_per_year", 52))
    shock = demand_cfg.get("shock")
    shock_periods = periods_from_shock(shock)
    shock_multiplier = float(shock.get("multiplier", 1.0)) if shock else 1.0

    sku_factors = {sku: float(rng.uniform(0.75, 1.25)) for sku in finished_goods}
    customer_factors = {customer: float(rng.uniform(0.65, 1.35)) for customer in customers}
    phases = {sku: float(rng.uniform(0.0, 2.0 * math.pi)) for sku in finished_goods}

    rows: list[dict[str, Any]] = []
    finished_by_period_sku: dict[tuple[int, str], int] = defaultdict(int)
    for period in range(1, horizon + 1):
        trend_factor = 1.0 + trend * (period - 1)
        for customer in customers:
            for sku in finished_goods:
                seasonal_factor = 1.0 + seasonal_amp * math.sin(
                    2.0 * math.pi * (period - 1) / periods_per_year + phases[sku]
                )
                active_shock = shock_multiplier if period in shock_periods else 1.0
                noise = float(rng.lognormal(mean=-0.5 * noise_std**2, sigma=noise_std))
                lump_multiplier = (
                    float(rng.uniform(lump_low, lump_high))
                    if float(rng.random()) < lump_probability
                    else 1.0
                )
                base_quantity = base * sku_factors[sku] * customer_factors[customer]
                quantity = max(
                    0,
                    int(
                        round(
                            base_quantity
                            * seasonal_factor
                            * trend_factor
                            * active_shock
                            * noise
                            * lump_multiplier
                        )
                    ),
                )
                finished_by_period_sku[(period, sku)] += quantity
                rows.append(
                    tagged(
                        {
                            "period": period,
                            "demand_type": "finished_good_customer",
                            "node_id": customer,
                            "sku_id": sku,
                            "parent_finished_good_id": sku,
                            "quantity_units": quantity,
                            "base_quantity_units": round(base_quantity, 6),
                            "seasonal_factor": round(seasonal_factor, 6),
                            "trend_factor": round(trend_factor, 6),
                            "noise_multiplier": round(noise, 6),
                            "lump_multiplier": round(lump_multiplier, 6),
                            "shock_multiplier": round(active_shock, 6),
                        },
                        scenario,
                        seed,
                    )
                )
    return rows, finished_by_period_sku


def build_component_demand(
    config: dict[str, Any],
    scenario: str,
    seed: int,
    bom: list[dict[str, Any]],
    finished_by_period_sku: dict[tuple[int, str], int],
) -> list[dict[str, Any]]:
    horizon = int(config["simulation"]["horizon_periods"])
    plants = [f"PLANT-{idx:03d}" for idx in range(1, int(config["network"]["plants"]) + 1)]
    children_by_parent: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    for row in bom:
        children_by_parent[row["parent_sku_id"]].append(
            (row["component_sku_id"], int(row["quantity_per_parent"]), int(row["tier_depth"]))
        )

    rows: list[dict[str, Any]] = []
    for period in range(1, horizon + 1):
        for (fg_period, fg_id), fg_quantity in sorted(finished_by_period_sku.items()):
            if fg_period != period:
                continue
            plant = plants[(int(fg_id.split("-")[1]) - 1) % len(plants)]
            for sa_id, sa_qty_per, _tier in sorted(children_by_parent[fg_id]):
                sa_quantity = fg_quantity * sa_qty_per
                rows.append(
                    tagged(
                        {
                            "period": period,
                            "demand_type": "derived_component",
                            "node_id": plant,
                            "sku_id": sa_id,
                            "parent_finished_good_id": fg_id,
                            "quantity_units": sa_quantity,
                            "base_quantity_units": float(sa_quantity),
                            "seasonal_factor": 1.0,
                            "trend_factor": 1.0,
                            "noise_multiplier": 1.0,
                            "lump_multiplier": 1.0,
                            "shock_multiplier": 1.0,
                        },
                        scenario,
                        seed,
                    )
                )
                for rc_id, rc_qty_per, _tier in sorted(children_by_parent[sa_id]):
                    rc_quantity = sa_quantity * rc_qty_per
                    rows.append(
                        tagged(
                            {
                                "period": period,
                                "demand_type": "derived_component",
                                "node_id": plant,
                                "sku_id": rc_id,
                                "parent_finished_good_id": fg_id,
                                "quantity_units": rc_quantity,
                                "base_quantity_units": float(rc_quantity),
                                "seasonal_factor": 1.0,
                                "trend_factor": 1.0,
                                "noise_multiplier": 1.0,
                                "lump_multiplier": 1.0,
                                "shock_multiplier": 1.0,
                            },
                            scenario,
                            seed,
                        )
                    )
    return rows


def build_capacities(
    config: dict[str, Any],
    scenario: str,
    seed: int,
    finished_goods: list[str],
    demand_rows: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    horizon = int(config["simulation"]["horizon_periods"])
    tightness = float(config["capacity"]["capacity_tightness"])
    plants = [f"PLANT-{idx:03d}" for idx in range(1, int(config["network"]["plants"]) + 1)]
    lines_per_plant = int(config["network"]["lines_per_plant"])

    fg_totals: dict[str, int] = defaultdict(int)
    for row in demand_rows:
        if row["demand_type"] == "finished_good_customer":
            fg_totals[row["sku_id"]] += int(row["quantity_units"])

    line_rows: list[dict[str, Any]] = []
    plant_capacity: dict[str, int] = defaultdict(int)
    for plant in plants:
        plant_index = int(plant.split("-")[1]) - 1
        assigned_skus = [
            sku for idx, sku in enumerate(finished_goods) if idx % len(plants) == plant_index
        ] or finished_goods
        for line_idx in range(1, lines_per_plant + 1):
            sku = assigned_skus[(line_idx - 1) % len(assigned_skus)]
            avg_units = fg_totals[sku] / horizon
            line_capacity = max(1, int(math.ceil(avg_units * tightness / max(1, lines_per_plant / len(assigned_skus)))))
            plant_capacity[plant] += line_capacity
            line_rows.append(
                tagged(
                    {
                        "line_id": f"{plant}-LINE-{line_idx:02d}",
                        "plant_id": plant,
                        "sku_id": sku,
                        "max_throughput_units_per_period": line_capacity,
                    },
                    scenario,
                    seed,
                )
            )

    for node in nodes:
        node_type = node["node_type"]
        if node_type == "plant":
            capacity = int(math.ceil(plant_capacity[node["node_id"]] * 1.05))
            node["capacity_units_per_period"] = capacity
            node["storage_capacity_units"] = int(capacity * float(config["capacity"]["plant_storage_periods"]))
        elif node_type == "supplier":
            node["capacity_units_per_period"] = int(config["capacity"]["supplier_capacity_units_per_period"])
            node["storage_capacity_units"] = int(config["capacity"]["supplier_storage_units"])
        elif node_type == "distribution_center":
            node["capacity_units_per_period"] = int(config["capacity"]["dc_throughput_units_per_period"])
            node["storage_capacity_units"] = int(config["capacity"]["dc_storage_units"])
        else:
            node["capacity_units_per_period"] = 0
            node["storage_capacity_units"] = int(config["capacity"]["customer_storage_units"])

    return line_rows


def build_lanes(
    config: dict[str, Any],
    rng: np.random.Generator,
    scenario: str,
    seed: int,
    raw_components: list[str],
    demand_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    size = config["network"]
    lane_cfg = config["lanes"]
    horizon = int(config["simulation"]["horizon_periods"])
    suppliers = [f"SUP-{idx:03d}" for idx in range(1, int(size["suppliers"]) + 1)]
    plants = [f"PLANT-{idx:03d}" for idx in range(1, int(size["plants"]) + 1)]
    dcs = [f"DC-{idx:03d}" for idx in range(1, int(size["distribution_centers"]) + 1)]
    customers = [f"CUST-{idx:03d}" for idx in range(1, int(size["customers"]) + 1)]
    tightness = float(config["capacity"]["capacity_tightness"])
    total_finished = sum(
        int(row["quantity_units"])
        for row in demand_rows
        if row["demand_type"] == "finished_good_customer"
    )
    total_components = sum(
        int(row["quantity_units"])
        for row in demand_rows
        if row["demand_type"] == "derived_component"
    )
    avg_finished = total_finished / horizon
    avg_components = total_components / horizon

    lanes: list[dict[str, Any]] = []

    def add_lane(
        lane_type: str,
        from_node: str,
        to_node: str,
        sku_scope: str,
        base_capacity: float,
        ordinal: int,
    ) -> None:
        params = lane_cfg[lane_type]
        lead_mean = max(1.0, float(params["lead_time_mean_days"]) * float(rng.uniform(0.9, 1.1)))
        lead_std = max(0.1, float(params["lead_time_std_days"]) * float(rng.uniform(0.85, 1.15)))
        cost = float(params["cost_per_unit"]) * float(rng.uniform(0.9, 1.15))
        capacity = max(1, int(math.ceil(base_capacity)))
        distance = max(10, int(round(float(params["distance_km"]) * float(rng.uniform(0.75, 1.25)))))
        lanes.append(
            tagged(
                {
                    "lane_id": f"LANE-{len(lanes) + 1:04d}",
                    "from_node_id": from_node,
                    "to_node_id": to_node,
                    "lane_type": lane_type,
                    "sku_scope": sku_scope,
                    "lead_time_mean_days": round(lead_mean, 6),
                    "lead_time_std_days": round(lead_std, 6),
                    "lane_cost_per_unit": round(cost, 6),
                    "capacity_units_per_period": capacity,
                    "distance_km": distance,
                    "transport_cost_per_km": round(float(params["transport_cost_per_km"]), 6),
                    "co2_kg_per_unit": round(float(params["co2_kg_per_unit"]), 6),
                    "lane_ordinal": ordinal,
                },
                scenario,
                seed,
            )
        )

    ordinal = 0
    inbound_base = avg_components * tightness * 1.25 / max(1, len(suppliers) * len(plants))
    for supplier in suppliers:
        for plant in plants:
            component = raw_components[ordinal % len(raw_components)]
            ordinal += 1
            add_lane("inbound_raw", supplier, plant, component, inbound_base, ordinal)

    plant_dc_base = avg_finished * tightness * 1.35 / max(1, len(plants) * len(dcs))
    for plant in plants:
        for dc in dcs:
            ordinal += 1
            add_lane("plant_to_dc", plant, dc, "finished_goods", plant_dc_base, ordinal)

    customer_base = avg_finished * tightness * 1.35 / max(1, len(dcs) * len(customers))
    for dc in dcs:
        for customer in customers:
            ordinal += 1
            add_lane("dc_to_customer", dc, customer, "finished_goods", customer_base, ordinal)

    lane_periods = build_lane_periods(config, scenario, seed, lanes)
    return lanes, lane_periods


def build_lane_periods(
    config: dict[str, Any],
    scenario: str,
    seed: int,
    lanes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    horizon = int(config["simulation"]["horizon_periods"])
    disruption = config.get("lane_disruption") or {}
    disruption_periods = periods_from_shock(disruption)
    affected_count = int(disruption.get("affected_lane_count", 0))
    affected_lane_type = disruption.get("lane_type", "inbound_raw")
    capacity_multiplier = float(disruption.get("capacity_multiplier", 1.0))
    lead_time_multiplier = float(disruption.get("lead_time_multiplier", 1.0))
    affected_lanes = {
        row["lane_id"]
        for row in sorted(
            [lane for lane in lanes if lane["lane_type"] == affected_lane_type],
            key=lambda lane: (-int(lane["capacity_units_per_period"]), lane["lane_id"]),
        )[:affected_count]
    }

    rows: list[dict[str, Any]] = []
    for lane in lanes:
        for period in range(1, horizon + 1):
            disrupted = lane["lane_id"] in affected_lanes and period in disruption_periods
            cap_multiplier = capacity_multiplier if disrupted else 1.0
            lt_multiplier = lead_time_multiplier if disrupted else 1.0
            rows.append(
                tagged(
                    {
                        "lane_id": lane["lane_id"],
                        "period": period,
                        "effective_capacity_units": int(
                            math.floor(int(lane["capacity_units_per_period"]) * cap_multiplier)
                        ),
                        "effective_lead_time_mean_days": round(
                            float(lane["lead_time_mean_days"]) * lt_multiplier,
                            6,
                        ),
                        "capacity_multiplier": round(cap_multiplier, 6),
                        "lead_time_multiplier": round(lt_multiplier, 6),
                        "disruption_code": disruption.get("name", "") if disrupted else "",
                    },
                    scenario,
                    seed,
                )
            )
    return rows


def build_service_targets(
    config: dict[str, Any],
    scenario: str,
    seed: int,
    finished_goods: list[str],
) -> list[dict[str, Any]]:
    service = config["service_targets"]
    customers = [f"CUST-{idx:03d}" for idx in range(1, int(config["network"]["customers"]) + 1)]
    rows: list[dict[str, Any]] = []
    for customer in customers:
        for sku in finished_goods:
            rows.append(
                tagged(
                    {
                        "customer_id": customer,
                        "sku_id": sku,
                        "fill_rate_target": float(service["fill_rate_target"]),
                        "days_inventory_target": float(service["days_inventory_target"]),
                        "criticality_tier": service["criticality_tier"],
                    },
                    scenario,
                    seed,
                )
            )
    return rows


def build_initial_inventory(
    config: dict[str, Any],
    scenario: str,
    seed: int,
    demand_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    horizon = int(config["simulation"]["horizon_periods"])
    doi = float(config["service_targets"]["days_inventory_target"])
    periods_per_year = int(config["demand"].get("periods_per_year", 52))
    period_days = 365.0 / periods_per_year
    avg_by_node_sku: dict[tuple[str, str], float] = defaultdict(float)
    for row in demand_rows:
        if row["demand_type"] == "finished_good_customer":
            avg_by_node_sku[(row["node_id"], row["sku_id"])] += int(row["quantity_units"]) / horizon
    rows: list[dict[str, Any]] = []
    for (node_id, sku_id), avg_period_units in sorted(avg_by_node_sku.items()):
        on_hand = int(math.ceil(avg_period_units * doi / period_days))
        rows.append(
            tagged(
                {
                    "node_id": node_id,
                    "sku_id": sku_id,
                    "on_hand_units": on_hand,
                    "in_transit_units": int(math.ceil(avg_period_units * 0.4)),
                    "backlog_units": 0,
                },
                scenario,
                seed,
            )
        )
    return rows


def generate(seed: int, scenario: str, output_dir: Path) -> None:
    config = load_scenario(scenario)
    effective_seed = int(config.get("random_seed_override") or seed)
    rng = np.random.default_rng(effective_seed)

    skus, bom, finished_goods, _subassemblies, raw_components = build_skus_and_bom(
        config, rng, scenario, effective_seed
    )
    nodes = build_nodes(config, scenario, effective_seed)
    finished_demand, finished_by_period_sku = build_finished_good_demand(
        config, rng, scenario, effective_seed, finished_goods
    )
    component_demand = build_component_demand(
        config, scenario, effective_seed, bom, finished_by_period_sku
    )
    demand_rows = sorted(
        finished_demand + component_demand,
        key=lambda row: (
            int(row["period"]),
            row["demand_type"],
            row["node_id"],
            row["sku_id"],
            row["parent_finished_good_id"],
        ),
    )
    production_lines = build_capacities(
        config, scenario, effective_seed, finished_goods, demand_rows, nodes
    )
    lanes, lane_periods = build_lanes(
        config, rng, scenario, effective_seed, raw_components, demand_rows
    )
    service_targets = build_service_targets(config, scenario, effective_seed, finished_goods)
    initial_inventory = build_initial_inventory(config, scenario, effective_seed, demand_rows)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    write_json(
        output_dir / "metadata.json",
        {
            "generator": "manufacturing-synthetic-data",
            "generator_version": 1,
            "scenario": scenario,
            "requested_seed": seed,
            "seed": effective_seed,
            "random_seed_override": config.get("random_seed_override"),
            "scenario_config": config,
            "outputs": [
                "nodes.csv",
                "skus.csv",
                "bom.csv",
                "demand.csv",
                "production_lines.csv",
                "lanes.csv",
                "lane_periods.csv",
                "service_targets.csv",
                "initial_inventory.csv",
            ],
            "synthetic_data_notice": "All records are synthetic and generated from configuration plus seed; no customer data is used.",
        },
    )

    common = ["scenario", "seed"]
    write_csv(
        output_dir / "nodes.csv",
        [
            "node_id",
            "node_type",
            "name",
            "region",
            "capacity_units_per_period",
            "storage_capacity_units",
            *common,
        ],
        sorted(nodes, key=lambda row: row["node_id"]),
    )
    write_csv(
        output_dir / "skus.csv",
        [
            "sku_id",
            "sku_type",
            "description",
            "unit_holding_cost",
            "ordering_cost",
            "backorder_penalty",
            "lost_sale_penalty",
            "production_cost",
            "unit_volume_cubic_m",
            *common,
        ],
        sorted(skus, key=lambda row: row["sku_id"]),
    )
    write_csv(
        output_dir / "bom.csv",
        ["parent_sku_id", "component_sku_id", "quantity_per_parent", "tier_depth", *common],
        sorted(bom, key=lambda row: (row["parent_sku_id"], row["component_sku_id"])),
    )
    write_csv(
        output_dir / "demand.csv",
        [
            "period",
            "demand_type",
            "node_id",
            "sku_id",
            "parent_finished_good_id",
            "quantity_units",
            "base_quantity_units",
            "seasonal_factor",
            "trend_factor",
            "noise_multiplier",
            "lump_multiplier",
            "shock_multiplier",
            *common,
        ],
        demand_rows,
    )
    write_csv(
        output_dir / "production_lines.csv",
        ["line_id", "plant_id", "sku_id", "max_throughput_units_per_period", *common],
        sorted(production_lines, key=lambda row: row["line_id"]),
    )
    write_csv(
        output_dir / "lanes.csv",
        [
            "lane_id",
            "from_node_id",
            "to_node_id",
            "lane_type",
            "sku_scope",
            "lead_time_mean_days",
            "lead_time_std_days",
            "lane_cost_per_unit",
            "capacity_units_per_period",
            "distance_km",
            "transport_cost_per_km",
            "co2_kg_per_unit",
            "lane_ordinal",
            *common,
        ],
        sorted(lanes, key=lambda row: row["lane_id"]),
    )
    write_csv(
        output_dir / "lane_periods.csv",
        [
            "lane_id",
            "period",
            "effective_capacity_units",
            "effective_lead_time_mean_days",
            "capacity_multiplier",
            "lead_time_multiplier",
            "disruption_code",
            *common,
        ],
        lane_periods,
    )
    write_csv(
        output_dir / "service_targets.csv",
        [
            "customer_id",
            "sku_id",
            "fill_rate_target",
            "days_inventory_target",
            "criticality_tier",
            *common,
        ],
        service_targets,
    )
    write_csv(
        output_dir / "initial_inventory.csv",
        ["node_id", "sku_id", "on_hand_units", "in_transit_units", "backlog_units", *common],
        initial_inventory,
    )


def main() -> None:
    args = parse_args()
    generate(args.seed, args.scenario, Path(args.output_dir))


if __name__ == "__main__":
    main()
