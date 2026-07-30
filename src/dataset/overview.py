"""Deterministic, pre-aggregated description of a generated scenario dataset.

Iteration 4, Phase 1. This module answers "what data did that result run on?" for a
non-technical viewer, and it answers it *from the files on disk* — never from a
constant. Every count, total, and range below is computed from
``data/generated/<scenario>/`` at request time.

Three rules govern this module:

1. **No hardcoded topology figures.** If the generator config changes, every number
   here changes with it. ``tests/test_iteration4_dataset.py`` proves this by mutating
   a copy of the data and asserting the overview follows.
2. **Aggregate, never dump.** No section returns more than ``MAX_SECTION_ROWS`` rows.
   Long tables are top-N by an explicitly named materiality measure and carry a
   ``showing`` block saying how much was withheld. ``stress-large`` is 44k+ demand
   rows; shipping those to a browser would be pointless.
3. **Deterministic.** Two calls against unchanged files return byte-identical JSON.
   That means no wall-clock stamps, no set iteration, and explicit sort keys on
   every list.

Reuses ``src.ingest.state`` for loading rather than re-parsing CSVs, so the counts
reported here cannot drift from the counts the pipeline actually ingests.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import polars as pl

from src.dataset.narrative import TABLE_WORDS, build_narrative, change_sentence, humanize
from src.forecast.statistical import LUMPY_ZERO_FRACTION_THRESHOLD, zero_fraction
from src.ingest.state import (
    DEFAULT_DATA_ROOT,
    REQUIRED_TABLES,
    ScenarioState,
    load_scenario_state,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_CONFIG_ROOT = REPO_ROOT / "data" / "scenarios"
METADATA_FILENAME = "metadata.json"

# Aggregation budget. These are presentation limits, not facts about any dataset.
MAX_SECTION_ROWS = 200
TOP_N = 12

# Calendar basis for turning periods into days. Derived from the generator's own
# `periods_per_year`, so a monthly dataset would report months, not weeks.
DAYS_PER_YEAR = 365.25
PERIOD_UNIT_BY_PERIODS_PER_YEAR = {365: "day", 52: "week", 26: "fortnight", 12: "month"}

BASELINE_SCENARIO = "baseline"

# Which tables each pipeline stage actually reads. Verified against the source, not
# assumed — see `src/forecast/statistical.py` and `src/optimize/common.py`. `nodes`,
# `bom` and `production_lines` are loaded and validated at ingest but are NOT read
# downstream: component demand is pre-derived through the BOM at generation time and
# lands in `demand.csv` as `derived_component` rows, so the optimizer reads those
# rows instead of walking the BOM. Stated plainly rather than drawn as a tidy arrow.
STAGE_TABLE_READS = {
    "ingest": sorted(REQUIRED_TABLES),
    "forecast": ["demand"],
    "optimize": [
        "demand",
        "initial_inventory",
        "lane_periods",
        "lanes",
        "service_targets",
        "skus",
    ],
}

NODE_TYPE_LABELS = {
    "supplier": "Supplier",
    "plant": "Factory",
    "distribution_center": "Distribution center",
    "customer": "Customer",
}
SKU_TYPE_LABELS = {
    "finished_good": "Finished product",
    "subassembly": "Subassembly",
    "raw_component": "Raw component",
}
LANE_TYPE_LABELS = {
    "inbound_raw": "Supplier to factory",
    "plant_to_dc": "Factory to distribution center",
    "dc_to_customer": "Distribution center to customer",
}

COST_INPUT_LABEL = "INPUT PARAMETERS — these are the costs fed to the optimizer, not measured results"


class UnknownScenarioError(LookupError):
    """No scenario config and no generated data directory by that name."""


class DatasetNotGeneratedError(RuntimeError):
    """The scenario is known, but its data has not been generated yet."""


def _round(value: Any, digits: int = 2) -> Any:
    if value is None:
        return None
    return round(float(value), digits)


def known_scenarios(data_root: Path | str = DEFAULT_DATA_ROOT) -> list[str]:
    """Scenario names discoverable from configs on disk, generated data, or both."""
    names = {path.stem for path in SCENARIO_CONFIG_ROOT.glob("*.yaml")}
    root = Path(data_root)
    if root.exists():
        names.update(path.name for path in root.iterdir() if path.is_dir())
    return sorted(names)


def _resolve_scenario_dir(scenario: str, data_root: Path) -> Path:
    """Resolve the scenario directory, refusing anything outside the data root.

    The API's scenario pattern permits '.' and '-', so a literal '..' satisfies it.
    Containment is enforced here rather than trusted to the pattern.
    """
    root = data_root.resolve()
    candidate = (root / scenario).resolve()
    if candidate != root and root not in candidate.parents:
        raise UnknownScenarioError(f"Scenario '{scenario}' is not a valid scenario name")
    return candidate


def _load_metadata(scenario_dir: Path) -> tuple[dict, str | None]:
    path = scenario_dir / METADATA_FILENAME
    if not path.exists():
        return {}, None
    metadata = json.loads(path.read_text(encoding="utf-8"))
    generated_at = (
        dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
        .isoformat(timespec="seconds")
    )
    return metadata, generated_at


def _period_unit(periods_per_year: Any) -> str:
    try:
        return PERIOD_UNIT_BY_PERIODS_PER_YEAR.get(int(periods_per_year), "period")
    except (TypeError, ValueError):
        return "period"


def _days_per_period(periods_per_year: Any) -> float | None:
    try:
        per_year = int(periods_per_year)
    except (TypeError, ValueError):
        return None
    return _round(DAYS_PER_YEAR / per_year, 4) if per_year else None


def _showing(shown: int, total: int, ranked_by: str) -> dict:
    return {
        "shown": shown,
        "total": total,
        "truncated": shown < total,
        "ranked_by": ranked_by,
        "note": f"showing top {shown} of {total}" if shown < total else f"showing all {total}",
    }


def _provenance(
    scenario: str,
    state: ScenarioState,
    metadata: dict,
    generated_at: str | None,
) -> dict:
    row_counts = state.row_counts()
    return {
        "scenario": scenario,
        "is_synthetic": True,
        "badge_text": (
            f"Synthetic demo dataset · seed {metadata.get('seed')} · "
            "generated on-device · not customer data"
        ),
        "requested_seed": metadata.get("requested_seed"),
        "effective_seed": metadata.get("seed"),
        "random_seed_override": metadata.get("random_seed_override"),
        "generator": metadata.get("generator"),
        "generator_version": metadata.get("generator_version"),
        "generated_at_utc": generated_at,
        "generated_at_source": f"filesystem mtime of {METADATA_FILENAME}",
        "synthetic_data_notice": metadata.get("synthetic_data_notice"),
        "data_location": str(state.root.relative_to(REPO_ROOT))
        if REPO_ROOT in state.root.parents
        else str(state.root),
        "regeneration_command": f"make demo-data   # or: make data SCENARIO={scenario}",
        "byte_identical_claim": (
            "Regenerating with the same seed and scenario reproduces these files "
            "byte-for-byte (enforced by "
            "tests/test_data_generator.py::test_same_seed_and_scenario_are_byte_identical)."
        ),
        "source_files": [
            {"table": name, "file": REQUIRED_TABLES[name], "rows": row_counts[name]}
            for name in sorted(REQUIRED_TABLES)
        ],
    }


def _network(state: ScenarioState) -> dict:
    nodes = state.nodes
    by_type = {
        row["node_type"]: row["n"]
        for row in nodes.group_by("node_type")
        .agg(pl.len().alias("n"))
        .sort("node_type")
        .to_dicts()
    }
    by_region = {
        row["region"]: row["n"]
        for row in nodes.group_by("region")
        .agg(pl.len().alias("n"))
        .sort("region")
        .to_dicts()
    }
    node_rows = nodes.sort(["node_type", "node_id"]).head(MAX_SECTION_ROWS).to_dicts()
    node_list = [
        {
            "node_id": row["node_id"],
            "node_type": row["node_type"],
            "plain_label": NODE_TYPE_LABELS.get(row["node_type"], row["node_type"]),
            "name": row["name"],
            "region": row["region"],
            "capacity_units_per_period": row["capacity_units_per_period"],
            "storage_capacity_units": row["storage_capacity_units"],
        }
        for row in node_rows
    ]

    lanes = state.lanes
    edge_rows = (
        lanes.sort(["lane_type", "lane_id"]).head(MAX_SECTION_ROWS).to_dicts()
    )
    edges = [
        {
            "lane_id": row["lane_id"],
            "from": row["from_node_id"],
            "to": row["to_node_id"],
            "lane_type": row["lane_type"],
            "sku_scope": row["sku_scope"],
            "lead_time_days": _round(row["lead_time_mean_days"]),
            "cost_per_unit": _round(row["lane_cost_per_unit"], 4),
            "capacity_units_per_period": row["capacity_units_per_period"],
        }
        for row in edge_rows
    ]

    tier_order = ["supplier", "plant", "distribution_center", "customer"]
    return {
        "node_count": nodes.height,
        "nodes_by_type": by_type,
        "nodes_by_region": by_region,
        "tiers": [
            {
                "tier": tier,
                "plain_label": NODE_TYPE_LABELS.get(tier, tier),
                "count": by_type.get(tier, 0),
            }
            for tier in tier_order
            if tier in by_type
        ],
        "node_list": node_list,
        "node_list_showing": _showing(len(node_list), nodes.height, "kind of place, then name"),
        "edges": edges,
        "edges_showing": _showing(len(edges), lanes.height, "kind of lane, then name"),
    }


def _demand_units_by_sku(state: ScenarioState) -> pl.DataFrame:
    return (
        state.demand.filter(pl.col("demand_type") == "finished_good_customer")
        .group_by("sku_id")
        .agg(pl.sum("quantity_units").alias("units"))
        .sort(["units", "sku_id"], descending=[True, False])
    )


def _products(state: ScenarioState) -> dict:
    skus = state.skus
    by_type = {
        row["sku_type"]: row["n"]
        for row in skus.group_by("sku_type")
        .agg(pl.len().alias("n"))
        .sort("sku_type")
        .to_dicts()
    }

    bom = state.bom
    parents = bom.select("parent_sku_id").unique().sort("parent_sku_id").to_series().to_list()
    bom_tree = []
    for parent in parents[:TOP_N]:
        children = (
            bom.filter(pl.col("parent_sku_id") == parent)
            .sort("component_sku_id")
            .select("component_sku_id", "quantity_per_parent", "tier_depth")
            .to_dicts()
        )
        bom_tree.append(
            {
                "parent_sku_id": parent,
                "children": [
                    {
                        "sku_id": child["component_sku_id"],
                        "quantity_per_parent": child["quantity_per_parent"],
                        "tier_depth": child["tier_depth"],
                    }
                    for child in children
                ],
            }
        )

    demand_by_sku = _demand_units_by_sku(state)
    total_units = float(demand_by_sku.select(pl.sum("units")).item() or 0.0)
    top_rows = demand_by_sku.head(TOP_N).to_dicts()
    top_by_demand = [
        {
            "sku_id": row["sku_id"],
            "units": _round(row["units"]),
            "share_of_finished_good_demand": _round(
                row["units"] / total_units if total_units else 0.0, 6
            ),
        }
        for row in top_rows
    ]

    return {
        "sku_count": skus.height,
        "sku_count_by_type": by_type,
        "sku_type_labels": {
            key: SKU_TYPE_LABELS.get(key, key) for key in sorted(by_type)
        },
        "bom_row_count": bom.height,
        "bom_parent_count": len(parents),
        "bom_max_tier_depth": int(bom.select(pl.max("tier_depth")).item())
        if bom.height
        else 0,
        "bom_tree": bom_tree,
        "bom_tree_showing": _showing(len(bom_tree), len(parents), "parent product"),
        "top_by_demand_share": top_by_demand,
        "top_by_demand_share_showing": _showing(
            len(top_by_demand), demand_by_sku.height, "total finished-good demand units"
        ),
    }


def _demand(state: ScenarioState, periods_per_year: Any) -> dict:
    demand = state.demand
    fg = demand.filter(pl.col("demand_type") == "finished_good_customer")

    rows_by_type = {
        row["demand_type"]: row["n"]
        for row in demand.group_by("demand_type")
        .agg(pl.len().alias("n"))
        .sort("demand_type")
        .to_dicts()
    }

    per_period = (
        fg.group_by("period")
        .agg(pl.sum("quantity_units").alias("units"))
        .sort("period")
    )
    units_per_period = [
        {"period": row["period"], "units": _round(row["units"])}
        for row in per_period.head(MAX_SECTION_ROWS).to_dicts()
    ]

    # Same grain and threshold the forecaster actually uses, imported rather than
    # restated, so this can never disagree with which model runs per series.
    history_by_series: dict[tuple[str, str], list[float]] = {
        (node_id, sku_id): [
            float(v) for v in frame.sort("period")["quantity_units"].to_list()
        ]
        for (node_id, sku_id), frame in fg.group_by(
            ["node_id", "sku_id"], maintain_order=True
        )
    }
    lumpy = {
        key
        for key, values in history_by_series.items()
        if zero_fraction(values) >= LUMPY_ZERO_FRACTION_THRESHOLD
    }
    series_count = len(history_by_series)

    top_series_ids = [
        (row["node_id"], row["sku_id"])
        for row in (
            fg.group_by(["node_id", "sku_id"])
            .agg(pl.sum("quantity_units").alias("units"))
            .sort(["units", "node_id", "sku_id"], descending=[True, False, False])
            .head(TOP_N)
            .to_dicts()
        )
    ]
    top_series = [
        {
            "node_id": node_id,
            "sku_id": sku_id,
            "is_lumpy": (node_id, sku_id) in lumpy,
            "forecast_method": "croston_sba"
            if (node_id, sku_id) in lumpy
            else "auto_ets",
            "units_by_period": [
                _round(v) for v in history_by_series[(node_id, sku_id)][:MAX_SECTION_ROWS]
            ],
        }
        for node_id, sku_id in top_series_ids
    ]

    shocked = demand.filter(pl.col("shock_multiplier") != 1.0)
    shock_window = None
    if shocked.height:
        multipliers = sorted(
            {_round(v, 4) for v in shocked["shock_multiplier"].to_list()}
        )
        shock_window = {
            "from_period": int(shocked.select(pl.min("period")).item()),
            "to_period": int(shocked.select(pl.max("period")).item()),
            "multipliers": multipliers,
            "affected_rows": shocked.height,
            "affected_sku_count": shocked.select("sku_id").n_unique(),
        }

    history_periods = int(demand.select(pl.max("period")).item()) if demand.height else 0
    return {
        "total_rows": demand.height,
        "rows_by_type": rows_by_type,
        "history_periods": history_periods,
        "period_unit": _period_unit(periods_per_year),
        "days_per_period": _days_per_period(periods_per_year),
        "series_count": series_count,
        "series_grain": ["node_id", "sku_id"],
        "total_units_finished_goods": _round(fg.select(pl.sum("quantity_units")).item() or 0.0),
        "units_per_period": units_per_period,
        "units_per_period_showing": _showing(
            len(units_per_period), per_period.height, "period ascending"
        ),
        "lumpy_series_count": len(lumpy),
        "lumpy_zero_fraction_threshold": LUMPY_ZERO_FRACTION_THRESHOLD,
        "max_zero_fraction": _round(
            max((zero_fraction(v) for v in history_by_series.values()), default=0.0), 6
        ),
        "forecast_method_split": {
            "croston_sba": len(lumpy),
            "auto_ets": series_count - len(lumpy),
        },
        # Guards against a misleading "we pick between two forecasters" claim. On
        # these generated datasets every series is continuous, so the split is
        # always 100% AutoETS. The generator's `lump_probability` produces occasional
        # demand *spikes*, not zero-demand periods, and it is the zero fraction —
        # not spikiness — that selects CrostonSBA.
        "forecast_method_note": (
            "Method is chosen per series by the fraction of periods with zero demand: "
            f">= {LUMPY_ZERO_FRACTION_THRESHOLD} uses CrostonSBA, otherwise AutoETS. "
            "Spiky-but-continuous demand still uses AutoETS."
        ),
        "top_series": top_series,
        "top_series_showing": _showing(
            len(top_series), series_count, "total finished-good demand units"
        ),
        "shock_window": shock_window,
    }


def _lanes(state: ScenarioState) -> dict:
    lanes = state.lanes
    by_type = {
        row["lane_type"]: row["n"]
        for row in lanes.group_by("lane_type")
        .agg(pl.len().alias("n"))
        .sort("lane_type")
        .to_dicts()
    }

    ranked = lanes.with_columns(
        (pl.col("capacity_units_per_period") * pl.col("lane_cost_per_unit")).alias(
            "_exposure"
        )
    ).sort(["_exposure", "lane_id"], descending=[True, False])
    table = [
        {
            "lane_id": row["lane_id"],
            "from": row["from_node_id"],
            "to": row["to_node_id"],
            "lane_type": row["lane_type"],
            "plain_label": LANE_TYPE_LABELS.get(row["lane_type"], row["lane_type"]),
            "sku_scope": row["sku_scope"],
            "lead_time_days": _round(row["lead_time_mean_days"]),
            "lead_time_std_days": _round(row["lead_time_std_days"]),
            "cost_per_unit": _round(row["lane_cost_per_unit"], 4),
            "capacity_units_per_period": row["capacity_units_per_period"],
            "distance_km": row["distance_km"],
            "co2_kg_per_unit": _round(row["co2_kg_per_unit"], 4),
        }
        for row in ranked.head(MAX_SECTION_ROWS).to_dicts()
    ]

    lane_periods = state.lane_periods
    disrupted = lane_periods.filter(pl.col("disruption_code").is_not_null())
    timeline = []
    if disrupted.height:
        grouped = (
            disrupted.group_by(["lane_id", "disruption_code"])
            .agg(
                pl.min("period").alias("from_period"),
                pl.max("period").alias("to_period"),
                pl.len().alias("periods_affected"),
                pl.min("capacity_multiplier").alias("min_capacity_multiplier"),
                pl.max("lead_time_multiplier").alias("max_lead_time_multiplier"),
            )
            .sort(["lane_id", "from_period"])
        )
        lane_lookup = {
            row["lane_id"]: row
            for row in lanes.select(
                "lane_id", "from_node_id", "to_node_id", "sku_scope", "lane_type"
            ).to_dicts()
        }
        timeline = [
            {
                "lane_id": row["lane_id"],
                "from": lane_lookup.get(row["lane_id"], {}).get("from_node_id"),
                "to": lane_lookup.get(row["lane_id"], {}).get("to_node_id"),
                "lane_type": lane_lookup.get(row["lane_id"], {}).get("lane_type"),
                "sku_scope": lane_lookup.get(row["lane_id"], {}).get("sku_scope"),
                "disruption_code": row["disruption_code"],
                "from_period": row["from_period"],
                "to_period": row["to_period"],
                "periods_affected": row["periods_affected"],
                "min_capacity_multiplier": _round(row["min_capacity_multiplier"], 4),
                "max_lead_time_multiplier": _round(row["max_lead_time_multiplier"], 4),
            }
            for row in grouped.head(MAX_SECTION_ROWS).to_dicts()
        ]

    lead_times = lanes.select("lead_time_mean_days")
    costs = lanes.select("lane_cost_per_unit")
    return {
        "lane_count": lanes.height,
        "count_by_type": by_type,
        "lane_type_labels": {
            key: LANE_TYPE_LABELS.get(key, key) for key in sorted(by_type)
        },
        "lane_period_row_count": lane_periods.height,
        "periods_covered": int(lane_periods.select(pl.max("period")).item())
        if lane_periods.height
        else 0,
        "lead_time_days_range": {
            "min": _round(lead_times.min().item()),
            "max": _round(lead_times.max().item()),
        },
        "cost_per_unit_range": {
            "min": _round(costs.min().item(), 4),
            "max": _round(costs.max().item(), 4),
        },
        "table": table,
        "table_showing": _showing(
            len(table), lanes.height, "capacity per period multiplied by cost per unit"
        ),
        "disruption_timeline": timeline,
        "disrupted_lane_count": disrupted.select("lane_id").n_unique()
        if disrupted.height
        else 0,
    }


def _capacity(state: ScenarioState) -> dict:
    lines = state.production_lines
    line_rows = [
        {
            "line_id": row["line_id"],
            "plant_id": row["plant_id"],
            "sku_id": row["sku_id"],
            "max_throughput_units_per_period": row["max_throughput_units_per_period"],
        }
        for row in lines.sort(
            ["max_throughput_units_per_period", "line_id"], descending=[True, False]
        )
        .head(MAX_SECTION_ROWS)
        .to_dicts()
    ]
    by_plant = {
        row["plant_id"]: row["n"]
        for row in lines.group_by("plant_id")
        .agg(pl.len().alias("n"))
        .sort("plant_id")
        .to_dicts()
    }
    storage = (
        state.nodes.group_by("node_type")
        .agg(
            pl.sum("storage_capacity_units").alias("storage_units"),
            pl.sum("capacity_units_per_period").alias("throughput_units_per_period"),
        )
        .sort("node_type")
        .to_dicts()
    )
    return {
        "production_line_count": lines.height,
        "lines_by_plant": by_plant,
        "total_throughput_units_per_period": _round(
            lines.select(pl.sum("max_throughput_units_per_period")).item() or 0.0
        ),
        "lines": line_rows,
        "lines_showing": _showing(
            len(line_rows), lines.height, "units built per period"
        ),
        "storage_by_node_type": [
            {
                "node_type": row["node_type"],
                "plain_label": NODE_TYPE_LABELS.get(row["node_type"], row["node_type"]),
                "storage_capacity_units": _round(row["storage_units"]),
                "throughput_units_per_period": _round(row["throughput_units_per_period"]),
            }
            for row in storage
        ],
    }


def _costs(state: ScenarioState) -> dict:
    skus = state.skus
    cost_columns = [
        ("unit_holding_cost", "Holding cost per unit per period"),
        ("ordering_cost", "Cost to place one order"),
        ("backorder_penalty", "Penalty per unit backordered"),
        ("lost_sale_penalty", "Penalty per unit of lost sale"),
        ("production_cost", "Cost to produce one unit"),
    ]
    by_type = []
    for row in (
        skus.group_by("sku_type")
        .agg(
            [pl.min(column).alias(f"{column}_min") for column, _ in cost_columns]
            + [pl.max(column).alias(f"{column}_max") for column, _ in cost_columns]
        )
        .sort("sku_type")
        .to_dicts()
    ):
        by_type.append(
            {
                "sku_type": row["sku_type"],
                "plain_label": SKU_TYPE_LABELS.get(row["sku_type"], row["sku_type"]),
                "parameters": [
                    {
                        "parameter": column,
                        "plain_label": label,
                        "min": _round(row[f"{column}_min"], 4),
                        "max": _round(row[f"{column}_max"], 4),
                    }
                    for column, label in cost_columns
                ],
            }
        )

    lanes = state.lanes
    return {
        "label": COST_INPUT_LABEL,
        "by_sku_type": by_type,
        "transport": {
            "cost_per_unit_min": _round(lanes.select(pl.min("lane_cost_per_unit")).item(), 4),
            "cost_per_unit_max": _round(lanes.select(pl.max("lane_cost_per_unit")).item(), 4),
            "cost_per_km_min": _round(lanes.select(pl.min("transport_cost_per_km")).item(), 6),
            "cost_per_km_max": _round(lanes.select(pl.max("transport_cost_per_km")).item(), 6),
        },
    }


def _service_targets(state: ScenarioState) -> dict:
    targets = state.service_targets
    tiers = {
        row["criticality_tier"]: row["n"]
        for row in targets.group_by("criticality_tier")
        .agg(pl.len().alias("n"))
        .sort("criticality_tier")
        .to_dicts()
    }
    fill = targets.select("fill_rate_target")
    days = targets.select("days_inventory_target")
    return {
        "row_count": targets.height,
        "customer_count": targets.select("customer_id").n_unique(),
        "sku_count": targets.select("sku_id").n_unique(),
        "criticality_tiers": tiers,
        "fill_rate_target_range": {
            "min": _round(fill.min().item(), 4),
            "max": _round(fill.max().item(), 4),
        },
        "days_inventory_target_range": {
            "min": _round(days.min().item()),
            "max": _round(days.max().item()),
        },
    }


def _initial_inventory(state: ScenarioState, demand_section: dict) -> dict:
    inventory = state.initial_inventory
    on_hand = float(inventory.select(pl.sum("on_hand_units")).item() or 0.0)
    in_transit = float(inventory.select(pl.sum("in_transit_units")).item() or 0.0)
    backlog = float(inventory.select(pl.sum("backlog_units")).item() or 0.0)

    annotated = inventory.join(
        state.nodes.select("node_id", "node_type"), on="node_id", how="left"
    ).join(state.skus.select("sku_id", "sku_type"), on="sku_id", how="left")
    by_node_type = (
        annotated.group_by("node_type")
        .agg(pl.sum("on_hand_units").alias("on_hand"))
        .sort("node_type")
        .to_dicts()
    )
    # Stated from the data so the cover estimate below is self-describing: if the
    # generator ever stocks components at plants, this says so instead of going stale.
    held_node_types = sorted(
        {row for row in annotated["node_type"].to_list() if row is not None}
    )
    held_sku_types = sorted(
        {row for row in annotated["sku_type"].to_list() if row is not None}
    )

    # Cover = on-hand divided by average finished-good demand per period, converted
    # to days with the generator's own calendar. An estimate over the whole network,
    # not a per-node guarantee — labelled as such in `basis`.
    periods = len(demand_section["units_per_period"]) or 1
    mean_units = (
        sum(entry["units"] for entry in demand_section["units_per_period"]) / periods
    )
    days_per_period = demand_section["days_per_period"]
    periods_of_cover = on_hand / mean_units if mean_units else None
    return {
        "row_count": inventory.height,
        "total_on_hand_units": _round(on_hand),
        "total_in_transit_units": _round(in_transit),
        "total_backlog_units": _round(backlog),
        "on_hand_by_node_type": [
            {
                "node_type": row["node_type"],
                "plain_label": NODE_TYPE_LABELS.get(row["node_type"], row["node_type"]),
                "on_hand_units": _round(row["on_hand"]),
            }
            for row in by_node_type
        ],
        "held_at_node_types": held_node_types,
        "held_sku_types": held_sku_types,
        "periods_of_cover_estimate": _round(periods_of_cover, 4),
        "days_of_cover_estimate": _round(periods_of_cover * days_per_period, 2)
        if periods_of_cover is not None and days_per_period
        else None,
        "basis": (
            "total on-hand units divided by mean finished-good demand per period, "
            f"converted to days. Stock in this dataset is held at: "
            f"{', '.join(held_node_types) or 'none'}; covering sku types: "
            f"{', '.join(held_sku_types) or 'none'}. A whole-network estimate, "
            "not a per-node guarantee."
        ),
    }


def _scenario_diff(
    scenario: str,
    metadata: dict,
    demand_section: dict,
    lanes_section: dict,
    data_root: Path,
) -> dict:
    """What is different about this scenario, derived from data plus the config used.

    Structured records only. Phase 2 owns the readable prose layer; every field here
    exists so that layer (and the Phase 4 map overlay) has real values to render.
    """
    changes: list[dict] = []

    shock = demand_section.get("shock_window")
    if shock:
        changes.append(
            {
                "kind": "demand_shock",
                "what": "finished-goods demand is multiplied above its normal level",
                "where": {"sku_count": shock["affected_sku_count"]},
                "when": {
                    "from_period": shock["from_period"],
                    "to_period": shock["to_period"],
                },
                "magnitude": {"multipliers": shock["multipliers"]},
                "evidence": "demand.csv shock_multiplier != 1.0",
            }
        )

    for entry in lanes_section.get("disruption_timeline", []):
        changes.append(
            {
                "kind": "lane_disruption",
                "what": entry["disruption_code"],
                "where": {
                    "lane_id": entry["lane_id"],
                    "from_node_id": entry["from"],
                    "to_node_id": entry["to"],
                    "sku_scope": entry["sku_scope"],
                    "lane_type": entry["lane_type"],
                },
                "when": {
                    "from_period": entry["from_period"],
                    "to_period": entry["to_period"],
                    "periods_affected": entry["periods_affected"],
                },
                "magnitude": {
                    "capacity_multiplier": entry["min_capacity_multiplier"],
                    "lead_time_multiplier": entry["max_lead_time_multiplier"],
                },
                "evidence": "lane_periods.csv disruption_code is not null",
            }
        )

    # Config deltas against baseline's own metadata, so the comparison uses the
    # config that actually generated each dataset rather than the YAML on disk now.
    config_changes: list[dict] = []
    comparable = False
    baseline_metadata: dict = {}
    if scenario != BASELINE_SCENARIO:
        baseline_meta_path = data_root / BASELINE_SCENARIO / METADATA_FILENAME
        if baseline_meta_path.exists():
            baseline_metadata = json.loads(
                baseline_meta_path.read_text(encoding="utf-8")
            )
            comparable = True

    if comparable:
        this_config = metadata.get("scenario_config") or {}
        base_config = baseline_metadata.get("scenario_config") or {}
        for group in sorted(set(this_config) | set(base_config)):
            if group in {"scenario", "description", "random_seed_override"}:
                continue
            mine, theirs = this_config.get(group), base_config.get(group)
            if isinstance(mine, dict) and isinstance(theirs, dict):
                for key in sorted(set(mine) | set(theirs)):
                    if mine.get(key) != theirs.get(key):
                        config_changes.append(
                            {
                                "group": group,
                                "parameter": key,
                                "baseline_value": theirs.get(key),
                                "scenario_value": mine.get(key),
                            }
                        )
            elif mine != theirs:
                config_changes.append(
                    {
                        "group": group,
                        "parameter": group,
                        "baseline_value": theirs,
                        "scenario_value": mine,
                    }
                )

    return {
        "vs": BASELINE_SCENARIO,
        "is_baseline": scenario == BASELINE_SCENARIO,
        "comparable": comparable or scenario == BASELINE_SCENARIO,
        "comparison_note": None
        if comparable or scenario == BASELINE_SCENARIO
        else "baseline dataset is not generated, so config deltas cannot be computed",
        "description": (metadata.get("scenario_config") or {}).get("description"),
        "changes": changes,
        "config_changes": config_changes[:MAX_SECTION_ROWS],
        "config_changes_showing": _showing(
            min(len(config_changes), MAX_SECTION_ROWS),
            len(config_changes),
            "setting group, then setting name",
        ),
    }


def _at_a_glance(
    metadata: dict,
    network: dict,
    products: dict,
    demand: dict,
    lanes: dict,
) -> list[dict]:
    unit = demand["period_unit"]
    return [
        {
            "key": "places",
            "label": "Places in the network",
            "value": network["node_count"],
            "unit": "locations",
            "plain_english_note": "suppliers, factories, distribution centers and customers",
        },
        {
            "key": "products",
            "label": "Products tracked",
            "value": products["sku_count"],
            "unit": "products",
            "plain_english_note": "finished products plus the parts they are built from",
        },
        {
            "key": "lanes",
            "label": "Shipping lanes",
            "value": lanes["lane_count"],
            "unit": "lanes",
            "plain_english_note": "routes goods can travel between two places",
        },
        {
            "key": "history",
            "label": f"{unit.capitalize()}s of history",
            "value": demand["history_periods"],
            "unit": f"{unit}s",
            "plain_english_note": "how far back the demand record goes",
        },
        {
            "key": "demand_records",
            "label": "Demand records",
            "value": demand["total_rows"],
            "unit": "rows",
            "plain_english_note": "one row per product, place and time period",
        },
        {
            "key": "seed",
            "label": "Random seed (reproducible)",
            "value": metadata.get("seed"),
            "unit": None,
            "plain_english_note": "regenerating with this seed rebuilds the identical dataset",
        },
    ]


def build_dataset_overview(
    scenario: str,
    data_root: Path | str = DEFAULT_DATA_ROOT,
) -> dict:
    """Build a complete, pre-aggregated description of one scenario's dataset.

    Raises:
        UnknownScenarioError: no config and no generated data by that name (API 404).
        DatasetNotGeneratedError: scenario is known but not generated yet (API 409).
    """
    root = Path(data_root)
    scenario_dir = _resolve_scenario_dir(scenario, root)

    if not scenario_dir.is_dir():
        if scenario in known_scenarios(root):
            raise DatasetNotGeneratedError(
                f"Scenario '{scenario}' has no generated data. Run `make demo-data` "
                f"(or `make data SCENARIO={scenario}`) and try again."
            )
        raise UnknownScenarioError(f"Unknown scenario '{scenario}'")

    try:
        state = load_scenario_state(scenario, data_root=root)
    except FileNotFoundError as exc:
        raise DatasetNotGeneratedError(
            f"Scenario '{scenario}' is missing generated files. Run `make demo-data` "
            f"(or `make data SCENARIO={scenario}`) and try again. Detail: {exc}"
        ) from exc

    metadata, generated_at = _load_metadata(scenario_dir)
    config = metadata.get("scenario_config") or {}
    periods_per_year = (config.get("demand") or {}).get("periods_per_year")

    network = _network(state)
    products = _products(state)
    demand = _demand(state, periods_per_year)
    lanes = _lanes(state)

    scenario_diff = _scenario_diff(scenario, metadata, demand, lanes, root)

    overview = {
        "provenance": _provenance(scenario, state, metadata, generated_at),
        "at_a_glance": _at_a_glance(metadata, network, products, demand, lanes),
        "network": network,
        "products": products,
        "demand": demand,
        "lanes": lanes,
        "capacity": _capacity(state),
        "costs": _costs(state),
        "service_targets": _service_targets(state),
        "initial_inventory": _initial_inventory(state, demand),
        "scenario_diff": scenario_diff,
        "pipeline_link": {
            "stage_inputs": STAGE_TABLE_READS,
            # Human labels travel with the payload so the browser never has to
            # invent one and drift from the wording used in the narrative.
            "table_labels": {
                name: humanize(name, TABLE_WORDS) for name in sorted(REQUIRED_TABLES)
            },
            "note": (
                "Tables each stage actually reads, verified against the source. "
                "nodes, bom and production_lines are loaded and validated at ingest "
                "but are not read by forecast or optimize: component demand is "
                "derived through the BOM when the data is generated and stored as "
                "derived_component rows in demand.csv, so the optimizer reads those "
                "rows rather than walking the BOM itself."
            ),
        },
    }

    # Phase 2: deterministic prose over the values above. No LLM on this path.
    period_unit = demand["period_unit"]
    for change in scenario_diff["changes"]:
        change["plain_english"] = change_sentence(change, period_unit)
    overview["narrative"] = build_narrative(overview)
    return overview


def read_table_csv(
    scenario: str,
    table: str,
    data_root: Path | str = DEFAULT_DATA_ROOT,
) -> tuple[str, str]:
    """Return ``(filename, csv_text)`` for one whitelisted table of one scenario.

    Only the nine tables in ``src.ingest.state.REQUIRED_TABLES`` are reachable, and
    the resolved path must sit inside the data root, so neither the table nor the
    scenario argument can escape the directory.
    """
    if table not in REQUIRED_TABLES:
        raise UnknownScenarioError(
            f"Unknown table '{table}'. Known tables: {', '.join(sorted(REQUIRED_TABLES))}"
        )

    root = Path(data_root)
    scenario_dir = _resolve_scenario_dir(scenario, root)
    filename = REQUIRED_TABLES[table]
    path = (scenario_dir / filename).resolve()
    if scenario_dir.resolve() != path.parent:
        raise UnknownScenarioError(f"Refusing to read outside the data root: {table}")

    if not path.exists():
        if scenario in known_scenarios(root):
            raise DatasetNotGeneratedError(
                f"Scenario '{scenario}' has no generated '{table}' table. "
                "Run `make demo-data` and try again."
            )
        raise UnknownScenarioError(f"Unknown scenario '{scenario}'")

    return filename, path.read_text(encoding="utf-8")
