"""Flatten the artifacts that already exist into atomic, citable facts.

Nothing here computes a plan, runs an optimizer, or calls a model. It reads:

* ``build_dataset_overview(scenario)`` — Iteration 4's deterministic description
  of the generated data (13 sections, read from the CSVs at request time);
* ``benchmark/<scenario>-head-to-head-comparison.json`` — the recorded output of
  ``run_head_to_head``, i.e. the numbers the results screen shows;
* ``benchmark/<scenario>-rag-advisory-rationale.json`` — the recorded advisory
  run (its text, its citations, its LLM profile);
* ``benchmark/suite-summary.json`` — the recorded device-memory envelope;
* ``data/corpus/<vertical>/*.md`` — the six real planner documents, as prose
  evidence only, injection-scanned exactly like the RAG retrieval path.

Every fact carries the source it came from, so an answer can cite it. A fact's
``numbers`` are the only numeric values that answer is allowed to state.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.dataset.overview import (
    DatasetNotGeneratedError,
    UnknownScenarioError,
    build_dataset_overview,
)
from src.ingest.corpus import DEFAULT_VERTICAL, load_corpus_documents
from src.ingest.state import DEFAULT_DATA_ROOT
from src.rag.advisory import CorpusDocument, scan_prompt_injection


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BENCHMARK_ROOT = REPO_ROOT / "benchmark"

# Caps. A fact list is scored in-process, so the cost of a large one is memory
# and scoring time, not prompt size (only the top few facts are ever sent to the
# model). stress-large has 42 nodes / 152 lanes / 288 series, and all of them
# matter for "what is the lead time on LANE-0100" style questions.
MAX_ROW_FACTS_PER_SECTION = 200

ENTITY_PATTERN = re.compile(r"\b(?:SUP|PLANT|DC|CUST|FG|SA|RC|LANE)-\d+\b", re.I)

# Plain words a planner uses for each entity type, used both for keyword scoring
# and for the "there is no warehouse 4" answer.
NODE_TYPE_WORDS: dict[str, tuple[str, ...]] = {
    "supplier": ("supplier", "suppliers", "vendor", "vendors"),
    "plant": ("factory", "factories", "plant", "plants", "manufacturing site"),
    "distribution_center": (
        "distribution center",
        "distribution centers",
        "distribution centre",
        "dc",
        "dcs",
        "warehouse",
        "warehouses",
        "depot",
        "depots",
    ),
    "customer": ("customer", "customers", "store", "stores", "site", "sites"),
}
NODE_TYPE_SINGULAR = {
    "supplier": "supplier",
    "plant": "factory",
    "distribution_center": "distribution center",
    "customer": "customer",
}


@dataclass(frozen=True)
class Fact:
    """One atomic, sourced statement.

    ``text`` is what the model is shown and what a template answer quotes.
    ``numbers`` is what the grounding validator authorizes.
    """

    fact_id: str
    source: str
    kind: str
    label: str
    text: str
    keywords: tuple[str, ...] = ()
    numbers: tuple[float, ...] = ()
    entities: tuple[str, ...] = ()
    injection_flagged: bool = False


@dataclass
class FactBundle:
    scenario: str
    facts: list[Fact] = field(default_factory=list)
    entities: dict[str, dict[str, Any]] = field(default_factory=dict)
    node_ids_by_type: dict[str, list[str]] = field(default_factory=dict)
    sources: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    injection_flags: list[dict[str, Any]] = field(default_factory=list)

    def by_id(self, fact_id: str) -> Fact | None:
        return next((fact for fact in self.facts if fact.fact_id == fact_id), None)

    def kinds(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for fact in self.facts:
            counts[fact.kind] = counts.get(fact.kind, 0) + 1
        return counts


class _Collector:
    def __init__(self) -> None:
        self.facts: list[Fact] = []

    def add(
        self,
        fact_id: str,
        source: str,
        kind: str,
        label: str,
        text: str,
        *,
        keywords: tuple[str, ...] | list[str] = (),
        numbers: tuple[float, ...] | list[float] = (),
        entities: tuple[str, ...] | list[str] = (),
        injection_flagged: bool = False,
    ) -> None:
        cleaned_numbers = tuple(
            float(value) for value in numbers if isinstance(value, (int, float)) and not isinstance(value, bool)
        )
        self.facts.append(
            Fact(
                fact_id=fact_id,
                source=source,
                kind=kind,
                label=label,
                text=re.sub(r"\s+", " ", text).strip(),
                keywords=tuple(dict.fromkeys(str(word).lower() for word in keywords if word)),
                numbers=cleaned_numbers,
                entities=tuple(dict.fromkeys(str(item) for item in entities if item)),
                injection_flagged=injection_flagged,
            )
        )


def _label(row: dict[str, Any], fallback_key: str = "node_type") -> str:
    """A row's display label, tolerating a missing or null one.

    The dataset layer derives ``plain_label`` from a lookup, which yields None if
    the underlying data is internally inconsistent (a row referencing a node that
    is not in nodes.csv, say). That should degrade to a readable word, not crash
    the whole bundle and 500 the endpoint.
    """
    value = row.get("plain_label")
    if isinstance(value, str) and value.strip():
        return value
    fallback = row.get(fallback_key)
    if isinstance(fallback, str) and fallback.strip():
        return fallback.replace("_", " ")
    return "unknown"


def _num(value: Any, digits: int = 2) -> str:
    """Format a number the way the answer should quote it."""
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int) or (isinstance(value, float) and float(value).is_integer()):
        return f"{int(value):,}"
    return f"{float(value):,.{digits}f}"


def _pct(fraction: Any, digits: int = 2) -> str:
    if fraction is None:
        return "unknown"
    return f"{float(fraction) * 100:.{digits}f}%"


def _join(items: list[str], limit: int = 8) -> str:
    values = [str(item) for item in items]
    if not values:
        return "none"
    if len(values) > limit:
        head = ", ".join(values[:limit])
        return f"{head} and {len(values) - limit} more"
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + f" and {values[-1]}"


# ---------------------------------------------------------------------------
# dataset_overview -> facts
# ---------------------------------------------------------------------------


def _dataset_facts(collector: _Collector, overview: dict[str, Any]) -> dict[str, list[str]]:
    src = "dataset_overview"
    provenance = overview["provenance"]
    scenario = provenance["scenario"]

    collector.add(
        "dataset.provenance.synthetic",
        f"{src}.provenance",
        "dataset",
        "Data provenance",
        f"This is synthetic demo data for scenario {scenario}, generated on this device with seed "
        f"{provenance['effective_seed']}. {provenance['synthetic_data_notice']} "
        f"It lives at {provenance['data_location']} and is regenerated with: {provenance['regeneration_command']}.",
        keywords=["synthetic", "real", "customer data", "seed", "provenance", "where", "generated", "reproducible"],
        numbers=[provenance["effective_seed"]],
    )
    collector.add(
        "dataset.provenance.reproducible",
        f"{src}.provenance",
        "dataset",
        "Reproducibility",
        provenance["byte_identical_claim"],
        keywords=["reproducible", "deterministic", "byte", "same", "regenerate", "seed"],
    )
    for entry in provenance.get("source_files", []):
        collector.add(
            f"dataset.provenance.table.{entry['table']}",
            f"{src}.provenance",
            "dataset",
            f"Rows in {entry['table']}",
            f"The {entry['table']} table ({entry['file']}) holds {_num(entry['rows'])} rows.",
            keywords=["rows", "table", "file", "csv", entry["table"], entry["table"].replace("_", " ")],
            numbers=[entry["rows"]],
        )

    for key, value in overview["narrative"].items():
        collector.add(
            f"dataset.narrative.{key}",
            f"{src}.narrative",
            "dataset",
            key.replace("_", " "),
            str(value),
            keywords=["summary", "overview", "describe", "what is this", "network", "scenario", "forecast", "pipeline"]
            if key != "provenance_sentence"
            else ["provenance", "figures", "estimated"],
        )

    for tile in overview["at_a_glance"]:
        collector.add(
            f"dataset.at_a_glance.{tile['key']}",
            f"{src}.at_a_glance",
            "dataset",
            tile["label"],
            f"{tile['label']}: {_num(tile['value'])} {tile['unit']}"
            + (f" ({tile['plain_english_note']})." if tile.get("plain_english_note") else "."),
            keywords=["how many", tile["key"], tile["label"].lower(), str(tile["unit"]).lower()],
            numbers=[tile["value"]],
        )

    network = overview["network"]
    node_ids_by_type: dict[str, list[str]] = {}
    for node in network.get("node_list", []):
        node_ids_by_type.setdefault(node["node_type"], []).append(node["node_id"])
    collector.add(
        "dataset.network.node_count",
        f"{src}.network",
        "dataset",
        "Locations in the network",
        f"The network has {_num(network['node_count'])} locations in total.",
        keywords=["how many", "locations", "places", "nodes", "sites", "network size"],
        numbers=[network["node_count"]],
    )
    for node_type, count in sorted(network["nodes_by_type"].items()):
        ids = node_ids_by_type.get(node_type, [])
        singular = NODE_TYPE_SINGULAR.get(node_type, node_type.replace("_", " "))
        collector.add(
            f"dataset.network.count.{node_type}",
            f"{src}.network",
            "dataset",
            f"Number of {singular}s",
            f"This scenario has {_num(count)} {singular}{'' if count == 1 else 's'}"
            + (f": {_join(ids, limit=12)}." if ids else "."),
            keywords=["how many", *NODE_TYPE_WORDS.get(node_type, (node_type,)), "which", "list"],
            numbers=[count],
            entities=ids,
        )
    for tier in network.get("tiers", []):
        collector.add(
            f"dataset.network.tier.{tier['tier']}",
            f"{src}.network",
            "dataset",
            f"{_label(tier, 'tier')} tier",
            f"The {_label(tier, 'tier').lower()} tier holds {_num(tier['count'])} locations.",
            keywords=["tier", "echelon", _label(tier, "tier").lower()],
            numbers=[tier["count"]],
        )
    for region, count in sorted(network.get("nodes_by_region", {}).items()):
        collector.add(
            f"dataset.network.region.{region}",
            f"{src}.network",
            "dataset",
            f"Locations in {region}",
            f"{region} contains {_num(count)} locations.",
            keywords=["region", "regions", "geography", region.lower()],
            numbers=[count],
            entities=[region],
        )
    for node in network.get("node_list", [])[:MAX_ROW_FACTS_PER_SECTION]:
        collector.add(
            f"dataset.network.node.{node['node_id']}",
            f"{src}.network",
            "dataset",
            f"Location {node['node_id']}",
            f"{node['node_id']} is a {_label(node).lower()} in {node['region']}, "
            f"with storage capacity {_num(node['storage_capacity_units'])} units and "
            f"production capacity {_num(node['capacity_units_per_period'])} units per period.",
            keywords=["location", "node", node["node_id"].lower(), _label(node).lower(), "storage", "capacity"],
            numbers=[node["storage_capacity_units"], node["capacity_units_per_period"]],
            entities=[node["node_id"], node["region"]],
        )

    products = overview["products"]
    collector.add(
        "dataset.products.count",
        f"{src}.products",
        "dataset",
        "Products tracked",
        f"The dataset tracks {_num(products['sku_count'])} products: "
        + _join(
            [
                f"{_num(count)} {products['sku_type_labels'].get(sku_type, sku_type).lower()}s"
                for sku_type, count in sorted(products["sku_count_by_type"].items())
            ]
        )
        + ".",
        keywords=["how many", "products", "skus", "items", "parts", "finished good", "raw component", "subassembly"],
        numbers=[products["sku_count"], *products["sku_count_by_type"].values()],
    )
    collector.add(
        "dataset.products.bom",
        f"{src}.products",
        "dataset",
        "Bill of materials",
        f"The bill of materials has {_num(products['bom_row_count'])} rows across "
        f"{_num(products['bom_parent_count'])} parent products, nested {_num(products['bom_max_tier_depth'])} tiers deep.",
        keywords=["bom", "bill of materials", "recipe", "made of", "components", "tiers", "depth"],
        numbers=[products["bom_row_count"], products["bom_parent_count"], products["bom_max_tier_depth"]],
    )
    for parent in products.get("bom_tree", [])[:MAX_ROW_FACTS_PER_SECTION]:
        children = parent.get("children", [])
        parts = _join(
            [f"{_num(child['quantity_per_parent'])} of {child['sku_id']}" for child in children],
            limit=10,
        )
        collector.add(
            f"dataset.products.bom.{parent['parent_sku_id']}",
            f"{src}.products",
            "dataset",
            f"What {parent['parent_sku_id']} is made of",
            f"Each unit of {parent['parent_sku_id']} needs {parts}.",
            keywords=["bom", "made of", "recipe", "components", "needs", parent["parent_sku_id"].lower()],
            numbers=[child["quantity_per_parent"] for child in children],
            entities=[parent["parent_sku_id"], *[child["sku_id"] for child in children]],
        )
    for row in products.get("top_by_demand_share", []):
        collector.add(
            f"dataset.products.share.{row['sku_id']}",
            f"{src}.products",
            "dataset",
            f"Demand share of {row['sku_id']}",
            f"{row['sku_id']} accounts for {_num(row['units'])} units of finished-good demand, "
            f"{_pct(row['share_of_finished_good_demand'])} of the finished-good total.",
            keywords=["share", "biggest", "largest", "most demand", "top product", row["sku_id"].lower()],
            numbers=[row["units"], row["share_of_finished_good_demand"]],
            entities=[row["sku_id"]],
        )

    demand = overview["demand"]
    collector.add(
        "dataset.demand.shape",
        f"{src}.demand",
        "dataset",
        "Demand history",
        f"The demand history covers {_num(demand['history_periods'])} {demand['period_unit']}s "
        f"({_num(demand['days_per_period'])} days per period) across {_num(demand['series_count'])} series, "
        f"{_num(demand['total_rows'])} rows in total, and "
        f"{_num(demand['total_units_finished_goods'])} finished-good units.",
        keywords=["demand", "history", "weeks", "periods", "series", "how much demand", "rows"],
        numbers=[
            demand["history_periods"],
            demand["days_per_period"],
            demand["series_count"],
            demand["total_rows"],
            demand["total_units_finished_goods"],
        ],
    )
    collector.add(
        "dataset.demand.lumpiness",
        f"{src}.demand",
        "dataset",
        "Intermittent (lumpy) demand",
        f"No series in this dataset is intermittent: {_num(demand['lumpy_series_count'])} of "
        f"{_num(demand['series_count'])} series clear the {_num(demand['lumpy_zero_fraction_threshold'])} "
        f"zero-demand threshold, and the highest share of zero-demand periods on any series is "
        f"{_num(demand['max_zero_fraction'])}. Every series has orders in every period, so none is lumpier than "
        f"the others in the intermittent sense. {demand['forecast_method_note']}",
        keywords=[
            "lumpy",
            "lumpiest",
            "intermittent",
            "spiky",
            "erratic",
            "zero demand",
            "croston",
            "which product",
            "forecast method",
        ],
        numbers=[
            demand["lumpy_series_count"],
            demand["series_count"],
            demand["lumpy_zero_fraction_threshold"],
            demand["max_zero_fraction"],
        ],
    )
    collector.add(
        "dataset.demand.forecast_split",
        f"{src}.demand",
        "dataset",
        "Forecast method split",
        f"All {_num(demand['forecast_method_split']['auto_ets'])} series are forecast with AutoETS and "
        f"{_num(demand['forecast_method_split']['croston_sba'])} with Croston-SBA.",
        keywords=["forecast", "method", "autoets", "croston", "how do you forecast"],
        numbers=[demand["forecast_method_split"]["auto_ets"], demand["forecast_method_split"]["croston_sba"]],
    )
    periods = demand.get("units_per_period", [])
    if periods:
        peak = max(periods, key=lambda row: row["units"])
        trough = min(periods, key=lambda row: row["units"])
        collector.add(
            "dataset.demand.peak_period",
            f"{src}.demand",
            "dataset",
            "Busiest and quietest period",
            f"Demand peaks in {demand['period_unit']} {_num(peak['period'])} at {_num(peak['units'])} units and "
            f"bottoms out in {demand['period_unit']} {_num(trough['period'])} at {_num(trough['units'])} units.",
            keywords=["peak", "busiest", "highest demand", "quietest", "lowest demand", "seasonality"],
            numbers=[peak["period"], peak["units"], trough["period"], trough["units"]],
        )
    shock = demand.get("shock_window")
    if shock:
        collector.add(
            "dataset.demand.shock_window",
            f"{src}.demand",
            "dataset",
            "Demand shock window",
            f"A demand shock runs from {demand['period_unit']} {_num(shock.get('from_period'))} to "
            f"{_num(shock.get('to_period'))} with a multiplier of {_num(shock.get('multiplier'), 2)}.",
            keywords=["shock", "surge", "spike", "window", "when"],
            numbers=[shock.get("from_period"), shock.get("to_period"), shock.get("multiplier")],
        )
    else:
        collector.add(
            "dataset.demand.shock_window",
            f"{src}.demand",
            "dataset",
            "Demand shock window",
            "There is no demand shock window in this scenario; any disruption here is on the shipping lanes, "
            "not on demand.",
            keywords=["shock", "surge", "spike", "window", "demand shock"],
        )
    for series in demand.get("top_series", [])[:MAX_ROW_FACTS_PER_SECTION]:
        # units_by_period is a bare list of per-period unit counts.
        units = [value for value in series.get("units_by_period", []) if isinstance(value, (int, float))]
        total = sum(float(value) for value in units) if units else None
        text = (
            f"Demand series {series['sku_id']} at {series['node_id']} is forecast with "
            f"{series['forecast_method']} and is {'intermittent' if series['is_lumpy'] else 'continuous'}"
        )
        numbers: list[float] = []
        if total is not None:
            text += f", totalling {_num(total)} units over the history"
            numbers.append(total)
        collector.add(
            f"dataset.demand.series.{series['node_id']}.{series['sku_id']}",
            f"{src}.demand",
            "dataset",
            f"Demand for {series['sku_id']} at {series['node_id']}",
            text + ".",
            keywords=["demand", "series", series["node_id"].lower(), series["sku_id"].lower()],
            numbers=numbers,
            entities=[series["node_id"], series["sku_id"]],
        )

    lanes = overview["lanes"]
    collector.add(
        "dataset.lanes.count",
        f"{src}.lanes",
        "dataset",
        "Shipping lanes",
        f"There are {_num(lanes['lane_count'])} shipping lanes: "
        + _join(
            [
                f"{_num(count)} {lanes['lane_type_labels'].get(lane_type, lane_type).lower()}"
                for lane_type, count in sorted(lanes["count_by_type"].items())
            ]
        )
        + f". Lane capacity is recorded for {_num(lanes['periods_covered'])} periods "
        f"({_num(lanes['lane_period_row_count'])} lane-period rows).",
        keywords=["how many", "lanes", "routes", "shipping", "legs", "connections"],
        numbers=[
            lanes["lane_count"],
            *lanes["count_by_type"].values(),
            lanes["periods_covered"],
            lanes["lane_period_row_count"],
        ],
    )
    collector.add(
        "dataset.lanes.ranges",
        f"{src}.lanes",
        "dataset",
        "Lead time and cost ranges",
        f"Lane lead times run from {_num(lanes['lead_time_days_range']['min'])} to "
        f"{_num(lanes['lead_time_days_range']['max'])} days, and lane cost per unit from "
        f"{_num(lanes['cost_per_unit_range']['min'], 4)} to {_num(lanes['cost_per_unit_range']['max'], 4)}.",
        keywords=["lead time", "range", "slowest", "fastest", "cost per unit", "cheapest", "most expensive"],
        numbers=[
            lanes["lead_time_days_range"]["min"],
            lanes["lead_time_days_range"]["max"],
            lanes["cost_per_unit_range"]["min"],
            lanes["cost_per_unit_range"]["max"],
        ],
    )
    for lane in lanes.get("table", [])[:MAX_ROW_FACTS_PER_SECTION]:
        collector.add(
            f"dataset.lanes.lane.{lane['lane_id']}",
            f"{src}.lanes",
            "dataset",
            f"Lane {lane['lane_id']}",
            f"Lane {lane['lane_id']} runs from {lane['from']} to {lane['to']} "
            f"({_label(lane, 'lane_type').lower()}), carries {lane['sku_scope']}, takes "
            f"{_num(lane['lead_time_days'])} days (standard deviation {_num(lane['lead_time_std_days'])}), "
            f"costs {_num(lane['cost_per_unit'], 4)} per unit, and can move "
            f"{_num(lane['capacity_units_per_period'])} units per period over {_num(lane['distance_km'])} km.",
            keywords=[
                "lane",
                "lead time",
                "cost",
                "capacity",
                "distance",
                "from",
                "to",
                lane["lane_id"].lower(),
                str(lane["from"]).lower(),
                str(lane["to"]).lower(),
                str(lane["sku_scope"]).lower(),
            ],
            numbers=[
                lane["lead_time_days"],
                lane["lead_time_std_days"],
                lane["cost_per_unit"],
                lane["capacity_units_per_period"],
                lane["distance_km"],
            ],
            entities=[lane["lane_id"], lane["from"], lane["to"], lane["sku_scope"]],
        )
    collector.add(
        "dataset.lanes.disrupted_count",
        f"{src}.lanes",
        "dataset",
        "Disrupted lanes",
        f"{_num(lanes['disrupted_lane_count'])} lanes are disrupted in this scenario."
        if lanes["disrupted_lane_count"]
        else "No lane is disrupted in this scenario.",
        keywords=["disrupted", "disruption", "broken", "outage", "shock", "how many lanes affected"],
        numbers=[lanes["disrupted_lane_count"]],
    )
    for entry in lanes.get("disruption_timeline", []):
        collector.add(
            f"dataset.lanes.disruption.{entry['lane_id']}",
            f"{src}.lanes",
            "dataset",
            f"Disruption on {entry['lane_id']}",
            f"Lane {entry['lane_id']} ({entry['from']} to {entry['to']}, carrying {entry['sku_scope']}) is "
            f"disrupted from period {_num(entry['from_period'])} to {_num(entry['to_period'])} — "
            f"{_num(entry['periods_affected'])} periods — with capacity falling to a multiplier of "
            f"{_num(entry['min_capacity_multiplier'], 2)} and lead time rising to a multiplier of "
            f"{_num(entry['max_lead_time_multiplier'], 2)}. The disruption code is {entry['disruption_code']}.",
            keywords=[
                "disruption",
                "disrupted",
                "shock",
                "outage",
                "shortage",
                "when",
                "how long",
                entry["lane_id"].lower(),
                str(entry["from"]).lower(),
                str(entry["to"]).lower(),
            ],
            numbers=[
                entry["from_period"],
                entry["to_period"],
                entry["periods_affected"],
                entry["min_capacity_multiplier"],
                entry["max_lead_time_multiplier"],
            ],
            entities=[entry["lane_id"], entry["from"], entry["to"], entry["sku_scope"]],
        )

    capacity = overview["capacity"]
    collector.add(
        "dataset.capacity.lines",
        f"{src}.capacity",
        "dataset",
        "Production lines",
        f"There are {_num(capacity['production_line_count'])} production lines "
        f"({_join([f'{_num(count)} at {plant}' for plant, count in sorted(capacity['lines_by_plant'].items())])}), "
        f"with a combined throughput of {_num(capacity['total_throughput_units_per_period'])} units per period.",
        keywords=["production", "lines", "throughput", "capacity", "how much can we make", "manufacturing"],
        numbers=[
            capacity["production_line_count"],
            *capacity["lines_by_plant"].values(),
            capacity["total_throughput_units_per_period"],
        ],
        entities=list(capacity["lines_by_plant"].keys()),
    )
    for line in capacity.get("lines", [])[:MAX_ROW_FACTS_PER_SECTION]:
        collector.add(
            f"dataset.capacity.line.{line['line_id']}",
            f"{src}.capacity",
            "dataset",
            f"Line {line['line_id']}",
            f"Line {line['line_id']} at {line['plant_id']} builds {line['sku_id']} at up to "
            f"{_num(line['max_throughput_units_per_period'])} units per period.",
            keywords=["line", "throughput", "builds", line["line_id"].lower(), str(line["plant_id"]).lower()],
            numbers=[line["max_throughput_units_per_period"]],
            entities=[line["line_id"], line["plant_id"], line["sku_id"]],
        )
    for row in capacity.get("storage_by_node_type", []):
        collector.add(
            f"dataset.capacity.storage.{row['node_type']}",
            f"{src}.capacity",
            "dataset",
            f"Storage at {_label(row).lower()}s",
            f"{_label(row)}s hold {_num(row['storage_capacity_units'])} units of storage capacity in total "
            f"and {_num(row['throughput_units_per_period'])} units per period of throughput.",
            keywords=["storage", "capacity", "space", *NODE_TYPE_WORDS.get(row["node_type"], ())],
            numbers=[row["storage_capacity_units"], row["throughput_units_per_period"]],
        )

    costs = overview["costs"]
    for group in costs.get("by_sku_type", []):
        for parameter in group.get("parameters", []):
            same = float(parameter["min"]) == float(parameter["max"])
            value_text = (
                _num(parameter["min"], 4)
                if same
                else f"{_num(parameter['min'], 4)} to {_num(parameter['max'], 4)}"
            )
            collector.add(
                f"dataset.costs.{group['sku_type']}.{parameter['parameter']}",
                f"{src}.costs",
                "dataset",
                f"{_label(parameter, 'parameter')} for {_label(group, 'sku_type').lower()}s",
                f"INPUT PARAMETER (not a measured result): {_label(parameter, 'parameter').lower()} for "
                f"{_label(group, 'sku_type').lower()}s is {value_text}.",
                keywords=[
                    "cost",
                    "input",
                    "parameter",
                    parameter["parameter"].replace("_", " "),
                    _label(parameter, "parameter").lower(),
                    _label(group, "sku_type").lower(),
                ],
                numbers=[parameter["min"], parameter["max"]],
            )
    collector.add(
        "dataset.costs.transport",
        f"{src}.costs",
        "dataset",
        "Transport cost inputs",
        f"INPUT PARAMETER (not a measured result): transport costs run "
        f"{_num(costs['transport']['cost_per_unit_min'], 4)} to {_num(costs['transport']['cost_per_unit_max'], 4)} "
        f"per unit and {_num(costs['transport']['cost_per_km_min'], 4)} to "
        f"{_num(costs['transport']['cost_per_km_max'], 4)} per km.",
        keywords=["transport", "shipping cost", "freight", "per km", "input", "cost"],
        numbers=list(costs["transport"].values()),
    )

    targets = overview["service_targets"]
    collector.add(
        "dataset.service_targets.summary",
        f"{src}.service_targets",
        "dataset",
        "Service promises",
        f"There are {_num(targets['row_count'])} service targets covering {_num(targets['customer_count'])} "
        f"customers and {_num(targets['sku_count'])} products. The fill-rate target is "
        f"{_pct(targets['fill_rate_target_range']['min'])}"
        + (
            ""
            if targets["fill_rate_target_range"]["min"] == targets["fill_rate_target_range"]["max"]
            else f" to {_pct(targets['fill_rate_target_range']['max'])}"
        )
        + f", and the days-of-inventory target is {_num(targets['days_inventory_target_range']['min'])} days. "
        f"Criticality tiers: {_join([f'{count} rows at {tier}' for tier, count in sorted(targets['criticality_tiers'].items())])}.",
        keywords=[
            "service",
            "target",
            "promise",
            "fill rate",
            "sla",
            "criticality",
            "days of inventory target",
            "how much do we promise",
        ],
        numbers=[
            targets["row_count"],
            targets["customer_count"],
            targets["sku_count"],
            targets["fill_rate_target_range"]["min"],
            targets["fill_rate_target_range"]["max"],
            targets["days_inventory_target_range"]["min"],
            *targets["criticality_tiers"].values(),
        ],
    )

    inventory = overview["initial_inventory"]
    held_at = inventory.get("held_at_node_types", [])
    collector.add(
        "dataset.initial_inventory.summary",
        f"{src}.initial_inventory",
        "dataset",
        "Starting inventory",
        f"Starting inventory is {_num(inventory['total_on_hand_units'])} units on hand, "
        f"{_num(inventory['total_in_transit_units'])} units in transit and "
        f"{_num(inventory['total_backlog_units'])} units of backlog, across "
        f"{_num(inventory['row_count'])} rows. It is held only at {_join(held_at)} locations — "
        f"there is no on-hand stock at factories or distribution centers in this dataset. "
        f"That is roughly {_num(inventory['days_of_cover_estimate'])} days of cover "
        f"({_num(inventory['periods_of_cover_estimate'])} periods).",
        keywords=[
            "inventory",
            "stock",
            "on hand",
            "in transit",
            "backlog",
            "starting",
            "days of cover",
            "where is the stock",
            "warehouse stock",
        ],
        numbers=[
            inventory["total_on_hand_units"],
            inventory["total_in_transit_units"],
            inventory["total_backlog_units"],
            inventory["row_count"],
            inventory["days_of_cover_estimate"],
            inventory["periods_of_cover_estimate"],
        ],
    )
    collector.add(
        "dataset.initial_inventory.basis",
        f"{src}.initial_inventory",
        "dataset",
        "How days of cover is derived",
        str(inventory["basis"]),
        keywords=["days of cover", "how is it calculated", "basis", "derived"],
    )
    for row in inventory.get("on_hand_by_node_type", []):
        collector.add(
            f"dataset.initial_inventory.on_hand.{row['node_type']}",
            f"{src}.initial_inventory",
            "dataset",
            f"On-hand stock at {_label(row).lower()}s",
            f"{_label(row)}s hold {_num(row['on_hand_units'])} units on hand.",
            keywords=["on hand", "stock", "inventory", *NODE_TYPE_WORDS.get(row["node_type"], ())],
            numbers=[row["on_hand_units"]],
        )

    diff = overview["scenario_diff"]
    collector.add(
        "dataset.scenario_diff.description",
        f"{src}.scenario_diff",
        "dataset",
        "What this scenario is",
        f"Scenario {scenario}: {diff.get('description') or 'no description recorded'}",
        keywords=["scenario", "what is this scenario", "description", "shock", "story"],
    )
    for index, change in enumerate(diff.get("changes", []), start=1):
        where = change.get("where", {}) or {}
        collector.add(
            f"dataset.scenario_diff.change.{index}",
            f"{src}.scenario_diff",
            "dataset",
            f"Scenario change {index} ({change.get('kind')})",
            f"{change.get('plain_english')} Evidence: {change.get('evidence')}.",
            keywords=[
                "scenario",
                "change",
                "difference",
                "disruption",
                str(change.get("kind", "")).replace("_", " "),
                *[str(value).lower() for value in where.values() if isinstance(value, str)],
            ],
            numbers=[
                value
                for group in ("when", "magnitude")
                for value in (change.get(group, {}) or {}).values()
                if isinstance(value, (int, float))
            ],
            entities=[value for value in where.values() if isinstance(value, str)],
        )
    if not diff.get("is_baseline", False):
        config_changes = diff.get("config_changes", [])
        groups: dict[str, int] = {}
        for change in config_changes:
            groups[change["group"]] = groups.get(change["group"], 0) + 1
        group_text = _join(
            [f"{group.replace('_', ' ')} ({count})" for group, count in sorted(groups.items())],
            limit=12,
        )
        total_config_changes = diff.get("config_changes_showing", {}).get("total", len(config_changes))
        collector.add(
            "dataset.scenario_diff.config_changes",
            f"{src}.scenario_diff",
            "dataset",
            "Other settings that differ from baseline",
            f"Beyond the headline disruption, {_num(total_config_changes)} configuration settings differ from "
            f"the {diff.get('vs')} scenario, across {group_text}.",
            keywords=["difference", "differs", "compared to baseline", "config", "settings", "what else changed"],
            numbers=[total_config_changes, *groups.values()],
        )

    pipeline = overview["pipeline_link"]
    collector.add(
        "dataset.pipeline.reads",
        f"{src}.pipeline_link",
        "dataset",
        "Which tables each stage reads",
        f"{pipeline['note']} Ingest reads {_join(pipeline['stage_inputs']['ingest'], limit=12)}; "
        f"the forecast reads {_join(pipeline['stage_inputs']['forecast'])}; "
        f"the optimizer reads {_join(pipeline['stage_inputs']['optimize'], limit=12)}.",
        keywords=[
            # This fact answers the "does the optimizer actually use X" family,
            # which is load-bearing: nodes, bom and production_lines are ingested
            # and validated but never read downstream, and an answer that implies
            # otherwise would be wrong.
            "pipeline",
            "read",
            "reads",
            "uses",
            "use",
            "inputs",
            "stage",
            "which tables",
            "does the optimizer read",
            "does the optimizer use",
            "read the nodes",
            "nodes",
            "nodes.csv",
            "bom",
            "production lines",
            "ignored",
            "not read",
        ],
    )

    return node_ids_by_type


# ---------------------------------------------------------------------------
# recorded benchmark run -> facts
# ---------------------------------------------------------------------------

APPROACH_LABELS = {
    "baseline": "the naive baseline (reorder point + shortest route)",
    "classical": "the tuned classical optimizer",
    "ppo": "the PPO reinforcement-learning candidate",
}

METRIC_KEYWORDS = (
    "objective",
    "cost",
    "total cost",
    "fill rate",
    "days of inventory",
    "cvar",
    "tail risk",
    "latency",
    "memory",
    "result",
    "how did it do",
    "improvement",
    "saving",
)


def _benchmark_facts(collector: _Collector, benchmark: dict[str, Any], generated_at: str | None) -> None:
    src = "benchmark.comparison"
    rows = {row["approach"]: row for row in benchmark["comparison"]}
    winner = benchmark["winner"]["approach"]
    # The horizon is not recorded in the artifact, but the winning plan's
    # per-period cost list has exactly one entry per period. Stating it matters:
    # a benchmark run with a different horizon is a different run, and an answer
    # should say which one it is quoting rather than implying there is only one.
    horizon = len(((benchmark.get("plans", {}).get(winner, {})).get("metrics", {}) or {}).get("period_costs") or [])

    collector.add(
        "benchmark.run",
        src,
        "benchmark",
        "The recorded run",
        f"These result numbers come from a recorded on-device run of the head-to-head benchmark for scenario "
        f"{benchmark['scenario']}"
        + (f" over a {_num(horizon)}-period horizon" if horizon else "")
        + (f", written at {generated_at}" if generated_at else "")
        + ". They were produced by the optimizer, not by a language model.",
        keywords=["run", "when", "recorded", "horizon", "where do the numbers come from", "who computed"],
        numbers=[horizon] if horizon else [],
    )
    collector.add(
        "benchmark.winner",
        src,
        "benchmark",
        "Which approach won",
        f"{APPROACH_LABELS.get(winner, winner).capitalize()} won this scenario with the lowest objective, "
        f"{_num(benchmark['winner']['objective'])}. PPO outcome: {benchmark['ppo_outcome'].replace('_', ' ')}.",
        keywords=["winner", "won", "which approach", "best", "chosen", "selected", *METRIC_KEYWORDS],
        numbers=[benchmark["winner"]["objective"]],
    )
    for approach, row in rows.items():
        collector.add(
            f"benchmark.metrics.{approach}",
            src,
            "benchmark",
            f"Measured result for {approach}",
            f"{APPROACH_LABELS.get(approach, approach).capitalize()} scored an objective of "
            f"{_num(row['objective'])}, total cost {_num(row['total_cost'])}, fill rate "
            f"{_num(row['fill_rate'], 4)} ({_pct(row['fill_rate'])}), days of inventory "
            f"{_num(row['days_of_inventory'])}, CVaR-75 tail cost {_num(row['cvar_75'])}, in "
            f"{_num(row['latency_seconds'], 3)} seconds using {_num(row['peak_process_rss_mb'])} MB of process memory.",
            keywords=[approach, *METRIC_KEYWORDS],
            numbers=[
                row["objective"],
                row["total_cost"],
                row["fill_rate"],
                row["days_of_inventory"],
                row["cvar_75"],
                row["latency_seconds"],
                row["peak_process_rss_mb"],
            ],
        )
    if "baseline" in rows and "classical" in rows:
        base = rows["baseline"]
        tuned = rows["classical"]
        obj_delta = base["objective"] - tuned["objective"]
        obj_pct = obj_delta / base["objective"] if base["objective"] else 0.0
        cost_delta = base["total_cost"] - tuned["total_cost"]
        cost_pct = cost_delta / base["total_cost"] if base["total_cost"] else 0.0
        fill_delta = tuned["fill_rate"] - base["fill_rate"]
        collector.add(
            "benchmark.improvement",
            src,
            "benchmark",
            "Improvement of the tuned optimizer over the naive baseline",
            f"The tuned classical optimizer improved the objective from {_num(base['objective'])} to "
            f"{_num(tuned['objective'])}, a reduction of {_num(obj_delta)} ({_pct(obj_pct)}), and total cost from "
            f"{_num(base['total_cost'])} to {_num(tuned['total_cost'])} ({_pct(cost_pct)}). Fill rate moved by "
            f"{_num(fill_delta, 4)} ({_pct(fill_delta)} points). These percentages compare the tuned optimizer "
            f"against the naive reorder-point + shortest-route baseline on this seeded synthetic scenario — not "
            f"against a customer's actual costs.",
            keywords=["improvement", "better", "saving", "percent", "how much", "reduction", "vs baseline", "gain"],
            numbers=[
                base["objective"],
                tuned["objective"],
                obj_delta,
                obj_pct,
                base["total_cost"],
                tuned["total_cost"],
                cost_pct,
                fill_delta,
            ],
        )
    if "ppo" in rows and winner != "ppo":
        ppo = rows["ppo"]
        win_row = rows[winner]
        gap = ppo["objective"] - win_row["objective"]
        gap_pct = gap / win_row["objective"] if win_row["objective"] else 0.0
        collector.add(
            "benchmark.ppo_outcome",
            src,
            "benchmark",
            "Why PPO is still shown",
            f"PPO lost this scenario: its objective of {_num(ppo['objective'])} is {_num(gap)} "
            f"({_pct(gap_pct)}) worse than {winner}'s {_num(win_row['objective'])}, and its CVaR-75 tail cost is "
            f"{_num(ppo['cvar_75'])} against {_num(win_row['cvar_75'])}. It stays visible in the comparison on "
            f"purpose: the learned candidate has to earn its place on evidence, and hiding a losing candidate "
            f"would make the benchmark less honest, not more.",
            keywords=[
                "ppo",
                "reinforcement learning",
                "rl",
                "why is ppo",
                "lost",
                "learned",
                "why show",
                "tail risk",
                "cvar",
            ],
            numbers=[ppo["objective"], gap, gap_pct, win_row["objective"], ppo["cvar_75"], win_row["cvar_75"]],
        )

    winner_plan = benchmark.get("plans", {}).get(winner, {})
    metrics = winner_plan.get("metrics", {})
    breakdown = metrics.get("cost_breakdown", {})
    if breakdown:
        collector.add(
            "benchmark.cost_breakdown",
            "benchmark.plans",
            "benchmark",
            "Where the winning plan's cost went",
            "The winning plan's measured cost breaks down as "
            + _join([f"{name} {_num(value)}" for name, value in sorted(breakdown.items())])
            + f", totalling {_num(metrics.get('total_cost'))}.",
            keywords=["cost breakdown", "holding", "ordering", "transport", "backorder", "lost sale", "where did"],
            numbers=[*breakdown.values(), metrics.get("total_cost")],
        )
    period_costs = metrics.get("period_costs") or []
    if period_costs:
        worst = max(range(len(period_costs)), key=lambda index: period_costs[index])
        collector.add(
            "benchmark.period_costs",
            "benchmark.plans",
            "benchmark",
            "Cost by period in the winning plan",
            f"The plan covers {_num(len(period_costs))} periods. Its most expensive period is period "
            f"{_num(worst + 1)} at {_num(period_costs[worst])}, and the CVaR-75 figure "
            f"({_num(metrics.get('cvar_75'))}) is the average cost of the worst quarter of periods.",
            keywords=["period", "horizon", "worst period", "cvar", "tail", "spike"],
            numbers=[len(period_costs), worst + 1, period_costs[worst], metrics.get("cvar_75")],
        )
    policy = winner_plan.get("policy", {})
    if policy:
        collector.add(
            "benchmark.policy",
            "benchmark.plans",
            "benchmark",
            "The winning policy settings",
            "The winning plan's policy multipliers are "
            + _join([f"{name.replace('_', ' ')} {_num(value, 4)}" for name, value in sorted(policy.items())])
            + ". The naive baseline leaves all three at 1.",
            keywords=["policy", "multiplier", "safety stock", "order up to", "batch", "tuning", "how did it win"],
            numbers=list(policy.values()),
        )
    lane_assignments = winner_plan.get("lane_assignments", [])
    if lane_assignments:
        collector.add(
            "benchmark.routing",
            "benchmark.plans",
            "benchmark",
            "How the plan routes flow",
            f"The plan assigns flow across {_num(len(lane_assignments))} lane groups using the "
            f"{lane_assignments[0].get('engine', 'unknown')} engine, splitting each required flow across the "
            f"available lanes rather than committing everything to one.",
            keywords=["routing", "lanes", "or-tools", "engine", "how does it ship", "split"],
            numbers=[len(lane_assignments)],
        )


def _advisory_facts(collector: _Collector, advisory: dict[str, Any]) -> None:
    collector.add(
        "advisory.boundary",
        "benchmark.advisory",
        "advisory",
        "What the language model is allowed to do",
        f"The advisory paragraph on the results screen is labelled {advisory.get('label')} and its text source is "
        f"{advisory.get('advisory_text_source')}. Every numeric metric comes from "
        f"{advisory.get('numeric_metrics_source')} — the model explains numbers, it never computes them.",
        keywords=["advisory", "llm", "language model", "who wrote", "does the ai", "boundary", "compute"],
    )
    collector.add(
        "advisory.text",
        "benchmark.advisory",
        "advisory",
        "The recorded advisory paragraph",
        str(advisory.get("advisory_rationale", "")),
        keywords=["advisory", "rationale", "explanation", "why this plan", "recommendation"],
    )
    profile = advisory.get("llm_profile", {}) or {}
    if profile:
        collector.add(
            "advisory.llm_profile",
            "benchmark.advisory",
            "advisory",
            "The local model that wrote it",
            f"The advisory was written on this device by {profile.get('model')} at "
            f"{_num(profile.get('tokens_per_second'))} tokens per second, using "
            f"{_num(profile.get('completion_tokens'))} completion tokens in "
            f"{_num(profile.get('wall_clock_seconds'), 2)} seconds. Nothing left the box.",
            keywords=["model", "llm", "tokens", "speed", "nemotron", "on device", "cloud", "gpu"],
            numbers=[
                profile.get("tokens_per_second"),
                profile.get("completion_tokens"),
                profile.get("wall_clock_seconds"),
            ],
        )


def _device_facts(collector: _Collector, scenario: str, suite: dict[str, Any]) -> None:
    entry = next(
        (item for item in suite.get("scenarios", []) if item.get("scenario") == scenario),
        None,
    )
    if entry is None:
        return
    memory = entry.get("device_memory", {}) or {}
    collector.add(
        "device.memory",
        "benchmark.suite_summary",
        "device",
        "On-device memory envelope",
        f"Running this scenario peaked at {_num(memory.get('peak_used_gib'))} GiB of the "
        f"{_num(memory.get('usable_envelope_gib'))} GiB usable unified memory pool, leaving "
        f"{_num(memory.get('headroom_gib'))} GiB of headroom "
        f"({_pct(memory.get('fraction_of_envelope'))} of the envelope). The 90% envelope flag was "
        f"{'raised' if memory.get('approaches_envelope') else 'not raised'}. Measured by {memory.get('method')}.",
        keywords=["memory", "gib", "envelope", "headroom", "fit", "device", "gb10", "hardware", "does it fit"],
        numbers=[
            memory.get("peak_used_gib"),
            memory.get("usable_envelope_gib"),
            memory.get("headroom_gib"),
            memory.get("fraction_of_envelope"),
        ],
    )


# ---------------------------------------------------------------------------
# corpus -> prose facts (untrusted evidence, injection-scanned)
# ---------------------------------------------------------------------------


def _corpus_facts(collector: _Collector, vertical: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for document in load_corpus_documents(vertical):
        sections = _split_sections(document["text"])
        for index, (heading, body) in enumerate(sections, start=1):
            chunk = CorpusDocument(
                source_id=f"{document['source_id']}#{index}",
                source_type=document["source_type"],
                title=f"{document['title']} — {heading}" if heading else document["title"],
                text=body,
            )
            chunk_findings = scan_prompt_injection([chunk])
            findings.extend(chunk_findings)
            collector.add(
                f"corpus.{document['source_id']}.{index}",
                f"corpus.{document['source_id']}",
                "corpus",
                chunk.title,
                body,
                keywords=_prose_keywords(f"{chunk.title} {body}"),
                injection_flagged=bool(chunk_findings),
            )
    return findings


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split a corpus document on Markdown headings, keeping each heading's body."""
    sections: list[tuple[str, str]] = []
    heading = ""
    buffer: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            if buffer and "".join(buffer).strip():
                sections.append((heading, "\n".join(buffer).strip()))
            heading = line.lstrip("#").strip()
            buffer = []
        else:
            buffer.append(line)
    if buffer and "".join(buffer).strip():
        sections.append((heading, "\n".join(buffer).strip()))
    return [(heading, body) for heading, body in sections if body]


_STOPWORDS = frozenset(
    """a an and are as at be but by for from has have how if in into is it its of on or our that the their
    then there these this to was were what when where which who why will with you your not no do does did
    can could should would may might must about over under between each per than very more most less
    """.split()
)


def _prose_keywords(text: str, limit: int = 40) -> tuple[str, ...]:
    words = [word for word in re.findall(r"[a-z][a-z-]{2,}", text.lower()) if word not in _STOPWORDS]
    ranked = sorted({word: words.count(word) for word in words}.items(), key=lambda item: (-item[1], item[0]))
    return tuple(word for word, _ in ranked[:limit])


# ---------------------------------------------------------------------------
# bundle assembly
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, None
    stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    return payload, stamp


def build_fact_bundle(
    scenario: str,
    data_root: Path | str = DEFAULT_DATA_ROOT,
    benchmark_root: Path | str = DEFAULT_BENCHMARK_ROOT,
    vertical: str = DEFAULT_VERTICAL,
    include_corpus: bool = True,
) -> FactBundle:
    """Assemble every fact available for one scenario, without running anything.

    Raises ``UnknownScenarioError`` / ``DatasetNotGeneratedError`` from the
    dataset layer, so the API can keep Iteration 4's 404 / 409 split.
    """
    overview = build_dataset_overview(scenario, data_root=data_root)
    collector = _Collector()
    bundle = FactBundle(scenario=scenario)
    bundle.node_ids_by_type = _dataset_facts(collector, overview)
    bundle.sources = {
        "dataset_overview": {
            "generated_at_utc": overview["provenance"]["generated_at_utc"],
            "data_location": overview["provenance"]["data_location"],
        }
    }

    benchmark_dir = Path(benchmark_root)
    benchmark, benchmark_stamp = _read_json(benchmark_dir / f"{scenario}-head-to-head-comparison.json")
    if benchmark and benchmark.get("comparison"):
        _benchmark_facts(collector, benchmark, benchmark_stamp)
        bundle.sources["benchmark_run"] = {
            "path": f"benchmark/{scenario}-head-to-head-comparison.json",
            "recorded_at_utc": benchmark_stamp,
            "winner": benchmark["winner"]["approach"],
        }
    else:
        bundle.notes.append(
            "No recorded optimizer run for this scenario yet, so questions about results cannot be answered. "
            "Run a scenario comparison first (make bench SCENARIO=" + scenario + ")."
        )

    advisory, advisory_stamp = _read_json(benchmark_dir / f"{scenario}-rag-advisory-rationale.json")
    if advisory and advisory.get("advisory_rationale"):
        _advisory_facts(collector, advisory)
        bundle.sources["advisory_run"] = {
            "path": f"benchmark/{scenario}-rag-advisory-rationale.json",
            "recorded_at_utc": advisory_stamp,
            "advisory_text_source": advisory.get("advisory_text_source"),
        }

    suite, suite_stamp = _read_json(benchmark_dir / "suite-summary.json")
    if suite:
        _device_facts(collector, scenario, suite)
        bundle.sources["suite_summary"] = {
            "path": "benchmark/suite-summary.json",
            "recorded_at_utc": suite_stamp,
        }

    if include_corpus:
        bundle.injection_flags = _corpus_facts(collector, vertical)
        bundle.sources["corpus"] = {"vertical": vertical, "injection_flags": len(bundle.injection_flags)}

    bundle.facts = collector.facts
    bundle.entities = _entity_index(bundle.facts)
    return bundle


def _entity_index(facts: list[Fact]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for fact in facts:
        for entity in fact.entities:
            if not ENTITY_PATTERN.fullmatch(entity):
                continue
            entry = index.setdefault(entity.upper(), {"fact_ids": []})
            entry["fact_ids"].append(fact.fact_id)
    return index


__all__ = [
    "DatasetNotGeneratedError",
    "Fact",
    "FactBundle",
    "UnknownScenarioError",
    "build_fact_bundle",
]
