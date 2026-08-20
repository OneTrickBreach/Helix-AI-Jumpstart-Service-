"""Build a scenario's nine tables in memory, with no disk access.

Why this exists: the settings ledger (:mod:`src.scenario.ledger`) has to answer
"which CSV column does this setting actually write?" for all 59 settings. The
honest way to answer it is to generate the data twice — once as-is, once with one
setting changed — and diff. Doing that through ``data/generator/generate.py``'s
``generate()`` would require a scenario YAML on disk and a directory to write to,
and Phase 1 must have **no write path at all**.

So this module calls the generator's *own* builders, in the generator's *own*
order, against an in-memory config dict. It deliberately duplicates nothing but
the orchestration, and ``test_in_memory_build_matches_the_generated_csvs`` pins it
to the real thing: if ``generate()`` ever builds differently, that test fails.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_generator() -> Any:
    """Import ``data/generator/generate.py``.

    ``data`` is not a package, so this goes through the file path rather than a
    normal import. The module is cached under a private name so repeated calls in
    a test session do not re-execute it.
    """
    cached = sys.modules.get("_helix_generator")
    if cached is not None:
        return cached
    path = REPO_ROOT / "data" / "generator" / "generate.py"
    spec = importlib.util.spec_from_file_location("_helix_generator", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load the generator from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_helix_generator"] = module
    spec.loader.exec_module(module)
    return module


# The CSV field order, per table, exactly as ``generate()`` writes it. Kept here
# so a diff compares what the pipeline would really read.
TABLE_FIELDNAMES: dict[str, tuple[str, ...]] = {
    "nodes": (
        "node_id", "node_type", "name", "region",
        "capacity_units_per_period", "storage_capacity_units",
    ),
    "skus": (
        "sku_id", "sku_type", "description", "unit_holding_cost", "ordering_cost",
        "backorder_penalty", "lost_sale_penalty", "production_cost", "unit_volume_cubic_m",
    ),
    "bom": ("parent_sku_id", "component_sku_id", "quantity_per_parent", "tier_depth"),
    "demand": (
        "period", "demand_type", "node_id", "sku_id", "parent_finished_good_id",
        "quantity_units", "base_quantity_units", "seasonal_factor", "trend_factor",
        "noise_multiplier", "lump_multiplier", "shock_multiplier",
    ),
    "production_lines": ("line_id", "plant_id", "sku_id", "max_throughput_units_per_period"),
    "lanes": (
        "lane_id", "from_node_id", "to_node_id", "lane_type", "sku_scope",
        "lead_time_mean_days", "lead_time_std_days", "lane_cost_per_unit",
        "capacity_units_per_period", "distance_km", "transport_cost_per_km",
        "co2_kg_per_unit", "lane_ordinal",
    ),
    "lane_periods": (
        "lane_id", "period", "effective_capacity_units", "effective_lead_time_mean_days",
        "capacity_multiplier", "lead_time_multiplier", "disruption_code",
    ),
    "service_targets": (
        "customer_id", "sku_id", "fill_rate_target", "days_inventory_target", "criticality_tier",
    ),
    "initial_inventory": ("node_id", "sku_id", "on_hand_units", "in_transit_units", "backlog_units"),
}

# The six tables the forecast and the optimizer actually load values from. The
# other three (``nodes``, ``bom``, ``production_lines``) are ingested and drawn
# on the dataset view but never read downstream — the Iteration 5 §1.3 finding,
# re-proven behaviourally by the ablation in tests/test_iteration6a_ledger.py.
PIPELINE_TABLES = (
    "demand", "lanes", "lane_periods", "skus", "initial_inventory", "service_targets",
)


def build_tables(config: dict[str, Any], seed: int = 12345) -> dict[str, list[dict[str, Any]]]:
    """The nine tables for ``config``, as ``generate()`` would write them.

    Mirrors ``generate()``'s body up to (but not including) the writes. The build
    order matters: ``build_capacities`` mutates ``nodes`` in place, so it has to
    run before ``nodes`` is read back.
    """
    import numpy as np

    gen = _load_generator()
    effective_seed = int(config.get("random_seed_override") or seed)
    rng = np.random.default_rng(effective_seed)
    scenario = str(config.get("scenario") or "unnamed")

    skus, bom, finished_goods, _subassemblies, raw_components = gen.build_skus_and_bom(
        config, rng, scenario, effective_seed
    )
    nodes = gen.build_nodes(config, scenario, effective_seed)
    finished_demand, finished_by_period_sku = gen.build_finished_good_demand(
        config, rng, scenario, effective_seed, finished_goods
    )
    component_demand = gen.build_component_demand(
        config, scenario, effective_seed, bom, finished_by_period_sku
    )
    demand_rows = sorted(
        finished_demand + component_demand,
        key=lambda row: (
            int(row["period"]), row["demand_type"], row["node_id"],
            row["sku_id"], row["parent_finished_good_id"],
        ),
    )
    production_lines = gen.build_capacities(
        config, scenario, effective_seed, finished_goods, demand_rows, nodes
    )
    lanes, lane_periods = gen.build_lanes(
        config, rng, scenario, effective_seed, raw_components, demand_rows
    )
    service_targets = gen.build_service_targets(config, scenario, effective_seed, finished_goods)
    initial_inventory = gen.build_initial_inventory(config, scenario, effective_seed, demand_rows)

    return {
        "nodes": sorted(nodes, key=lambda row: row["node_id"]),
        "skus": sorted(skus, key=lambda row: row["sku_id"]),
        "bom": sorted(bom, key=lambda row: (row["parent_sku_id"], row["component_sku_id"])),
        "demand": demand_rows,
        "production_lines": production_lines,
        "lanes": lanes,
        "lane_periods": lane_periods,
        "service_targets": service_targets,
        "initial_inventory": initial_inventory,
    }


def formatted_columns(tables: dict[str, list[dict[str, Any]]]) -> dict[tuple[str, str], list[str]]:
    """``(table, column) -> the column's values as the CSV would hold them``.

    Formatting through the generator's own ``fmt`` matters: it rounds floats to
    six decimal places, which is the precision the pipeline actually reads. Two
    configs that differ only below that threshold produce identical CSVs, so a
    raw float comparison would report a change the optimizer can never see.
    """
    gen = _load_generator()
    out: dict[tuple[str, str], list[str]] = {}
    for table, fieldnames in TABLE_FIELDNAMES.items():
        rows = tables.get(table, [])
        for field in fieldnames:
            out[(table, field)] = [gen.fmt(row.get(field, "")) for row in rows]
    return out
