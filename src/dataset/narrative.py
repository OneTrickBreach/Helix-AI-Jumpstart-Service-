"""Plain-English sentences describing a dataset, composed from real values.

Iteration 4, Phase 2. Every string here is a deterministic template filled from
numbers the overview already derived from disk. There is **no LLM on this path**
(Iteration 4 decision 4): the dataset page must render instantly, identically on
every load, and it must never sit LLM prose next to raw input data. Iteration 5 is
where a model gets to interpret this data, clearly labelled as such.

Two rules:

1. **Say only what the data says.** If a scenario changes twenty-four settings, the
   sentence does not claim "nothing else changes" — it says how many else changed.
2. **Read naturally at zero clicks.** Singular/plural, thousands separators, and
   missing tiers are all handled, because "1 suppliers" or "0 distribution centers"
   in front of a stakeholder undoes the credibility the numbers earn.
"""

from __future__ import annotations

from typing import Any


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    """`5 suppliers` / `1 supplier`, with a thousands separator on the number."""
    word = singular if abs(count) == 1 else (plural_form or f"{singular}s")
    return f"{count:,} {word}"


# Schema names are precise but unreadable. Anything that reaches a sentence gets a
# human word; anything that stays a machine field keeps its snake_case name.
TABLE_WORDS = {
    "bom": "bill of materials",
    "demand": "demand history",
    "initial_inventory": "starting inventory",
    "lane_periods": "lane capacity period by period",
    "lanes": "shipping lanes",
    "nodes": "network locations",
    "production_lines": "production lines",
    "service_targets": "service targets",
    "skus": "product costs",
}
CONFIG_GROUP_WORDS = {
    "capacity": "capacity",
    "costs": "costs",
    "demand": "demand",
    "lane_disruption": "lane disruption",
    "lanes": "shipping lanes",
    "network": "network size",
    "service_targets": "service targets",
    "simulation": "simulation length",
}


def humanize(name: str, lookup: dict[str, str] | None = None) -> str:
    """Turn a schema name into something readable in a sentence."""
    if lookup and name in lookup:
        return lookup[name]
    return name.replace("_", " ")


def _id_list(ids: list[str], limit: int = 4) -> str:
    """Name a few identifiers without dumping a hundred of them into a sentence."""
    if not ids:
        return ""
    if len(ids) <= limit:
        return _join(ids)
    return f"{', '.join(ids[:limit])}, and {len(ids) - limit:,} more"


def _capacity_text(multiplier: float | None, many: bool) -> str | None:
    """Verb phrase for a capacity change, agreeing with a singular or plural subject."""
    if multiplier is None:
        return None
    if multiplier == 0:
        return "stop completely" if many else "stops completely"
    if multiplier < 1:
        possessive = "their" if many else "its"
        verb = "fall" if many else "falls"
        return f"{verb} to {multiplier:.0%} of {possessive} normal capacity"
    if multiplier > 1:
        possessive = "their" if many else "its"
        verb = "rise" if many else "rises"
        return f"{verb} to {multiplier:g}x {possessive} normal capacity"
    return None


def _lead_time_text(multiplier: float | None, many: bool) -> str | None:
    if multiplier is None or multiplier == 1:
        return None
    subject = "their lead times stretch" if many else "its lead time stretches"
    return f"{subject} to {multiplier:g}x normal"


def _join(items: list[str]) -> str:
    """Oxford-comma join: 'a', 'a and b', 'a, b, and c'."""
    items = [item for item in items if item]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def vertical_from_generator(generator: str | None) -> str:
    """`manufacturing-synthetic-data` -> `manufacturing`.

    Derived rather than hardcoded: if a retail generator is ever added, the opening
    sentence follows it instead of confidently calling a store network a factory.
    """
    if not generator:
        return ""
    return generator.split("-", 1)[0].replace("_", " ")


def one_sentence_summary(
    network: dict,
    products: dict,
    demand: dict,
    capacity: dict,
    vertical: str = "",
) -> str:
    """The 'ohh — that's my dataset' sentence, built from actual tier counts."""
    by_type = network.get("nodes_by_type", {})
    suppliers = by_type.get("supplier", 0)
    plants = by_type.get("plant", 0)
    centers = by_type.get("distribution_center", 0)
    customers = by_type.get("customer", 0)
    lines = capacity.get("production_line_count", 0)

    unit = demand.get("period_unit", "period")
    periods = demand.get("history_periods", 0)
    sku_count = products.get("sku_count", 0)

    # Built clause by clause so a network missing a tier still reads correctly.
    clauses: list[str] = []
    if suppliers:
        clauses.append(f"{plural(suppliers, 'supplier')} ship parts to")
    if plants:
        factory = plural(plants, "factory", "factories")
        if lines:
            factory += f" running {plural(lines, 'production line')}"
        clauses.append(factory)
    if centers:
        verb = "which sends" if plants == 1 else "which send"
        if not plants:
            verb = "goods move"
        # Leading comma: "...6 production lines, which send finished goods..."
        clauses.append(
            f", {verb} finished goods through {plural(centers, 'distribution center')}"
        )
    if customers:
        connector = "out to" if centers else "to"
        clauses.append(f"{connector} {plural(customers, 'customer')}")

    if not clauses:
        return "This dataset contains no network locations."

    chain = " ".join(clauses).replace(" , ", ", ")
    tail = _join(
        [
            plural(sku_count, "product") if sku_count else "",
            f"{plural(periods, unit)} of demand history" if periods else "",
        ]
    )
    kind = f"one {vertical} network" if vertical else "one supply-chain network"
    sentence = f"This is {kind}: {chain}"
    return f"{sentence} — {tail}." if tail else f"{sentence}."


def change_sentence(change: dict, unit: str) -> str:
    """One plain-English line for a single structured scenario change."""
    when = change.get("when", {})
    start, end = when.get("from_period"), when.get("to_period")
    span = when.get("periods_affected")

    if change.get("kind") == "demand_shock":
        multipliers = change.get("magnitude", {}).get("multipliers") or []
        level = (
            f"{multipliers[0]:g}x its normal level"
            if len(multipliers) == 1
            else f"between {min(multipliers):g}x and {max(multipliers):g}x normal"
        )
        skus = change.get("where", {}).get("sku_count")
        who = f" across {plural(skus, 'product')}" if skus else ""
        return (
            f"From {unit} {start} through {unit} {end}, customer demand for finished "
            f"goods runs at {level}{who}."
        )

    if change.get("kind") == "lane_disruption":
        where = change.get("where", {})
        magnitude = change.get("magnitude", {})
        capacity_text = _capacity_text(magnitude.get("capacity_multiplier"), many=False)
        lead_text = _lead_time_text(magnitude.get("lead_time_multiplier"), many=False)
        route = f"the lane from {where.get('from_node_id')} to {where.get('to_node_id')}"
        scope = where.get("sku_scope")
        carrying = f" carrying {scope}" if scope else ""
        duration = f" for {plural(span, unit)}" if span else ""
        effect = capacity_text or "is disrupted"
        tail = f", and {lead_text}" if lead_text else ""
        return (
            f"From {unit} {start}, {route}{carrying} ({where.get('lane_id')}) "
            f"{effect}{duration}{tail}."
        )

    return change.get("what", "An unrecognised change is present in this scenario.")


def _lane_group_sentence(group: list[dict], unit: str) -> str:
    """One sentence for several lanes disrupted identically over the same window.

    `stress-large` knocks out four lanes with the same magnitude and timing. Emitting
    four near-identical sentences reads like a machine; saying it once reads like a
    person who understands the scenario.
    """
    if len(group) == 1:
        return change_sentence(group[0], unit)

    first = group[0]
    when = first.get("when", {})
    magnitude = first.get("magnitude", {})
    capacity_text = _capacity_text(magnitude.get("capacity_multiplier"), many=True)
    lead_text = _lead_time_text(magnitude.get("lead_time_multiplier"), many=True)

    lane_ids = sorted(change["where"].get("lane_id") for change in group)
    scopes = sorted(
        {
            change["where"].get("sku_scope")
            for change in group
            if change["where"].get("sku_scope")
        }
    )
    sources = sorted(
        {
            change["where"].get("from_node_id")
            for change in group
            if change["where"].get("from_node_id")
        }
    )

    who = (
        f" from {plural(len(sources), 'supplier')}"
        if len(sources) > 1
        else f" from supplier {sources[0]}"
        if sources
        else ""
    )
    carrying = f" carrying {_id_list(scopes)}" if scopes else ""
    duration = (
        f" for {plural(when.get('periods_affected'), unit)}"
        if when.get("periods_affected")
        else ""
    )
    effect = capacity_text or "are disrupted"
    tail = f", and {lead_text}" if lead_text else ""

    return (
        f"From {unit} {when.get('from_period')}, {plural(len(group), 'inbound lane')}"
        f"{who}{carrying} ({_id_list(lane_ids)}) {effect}{duration}{tail}."
    )


def _group_lane_changes(changes: list[dict]) -> list[list[dict]]:
    """Bucket lane disruptions that share code, window and magnitude."""
    groups: dict[tuple, list[dict]] = {}
    order: list[tuple] = []
    for change in changes:
        when, magnitude = change.get("when", {}), change.get("magnitude", {})
        key = (
            change.get("what"),
            when.get("from_period"),
            when.get("to_period"),
            magnitude.get("capacity_multiplier"),
            magnitude.get("lead_time_multiplier"),
        )
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(change)
    return [groups[key] for key in order]


def scenario_sentence(scenario_diff: dict, demand: dict) -> str:
    """What makes this scenario different from baseline, in words.

    Deliberately does NOT say "nothing else changes" unless nothing else does —
    these scenarios also vary costs, capacities and service targets, and claiming
    otherwise in front of a stakeholder would be false.
    """
    unit = demand.get("period_unit", "period")

    if scenario_diff.get("is_baseline"):
        return (
            "This is the normal operating scenario: no disruption is applied. "
            "Every other scenario is a change from this one."
        )

    changes = scenario_diff.get("changes", [])
    demand_changes = [c for c in changes if c.get("kind") == "demand_shock"]
    lane_changes = [c for c in changes if c.get("kind") == "lane_disruption"]
    other_changes = [
        c for c in changes if c.get("kind") not in {"demand_shock", "lane_disruption"}
    ]

    sentences = [change_sentence(change, unit) for change in demand_changes]
    sentences += [
        _lane_group_sentence(group, unit) for group in _group_lane_changes(lane_changes)
    ]
    sentences += [change_sentence(change, unit) for change in other_changes]

    config_changes = scenario_diff.get("config_changes") or []
    if config_changes:
        groups = sorted(
            {humanize(entry["group"], CONFIG_GROUP_WORDS) for entry in config_changes}
        )
        sentences.append(
            f"Beyond that, {plural(len(config_changes), 'other setting')} "
            f"{'differs' if len(config_changes) == 1 else 'differ'} from the baseline "
            f"scenario, across {_join(groups)}."
        )
    elif not sentences and not scenario_diff.get("comparable"):
        return (
            "This scenario cannot be compared with the baseline because the baseline "
            "dataset has not been generated."
        )
    elif not sentences:
        return "This scenario is identical to the baseline dataset."

    return " ".join(sentences)


def forecast_method_sentence(demand: dict) -> str:
    """How each demand series gets forecast — reporting what is measured, not a story.

    On the current generated data every series is continuous, so this correctly reads
    "all ... AutoETS" rather than implying a method choice that never happens.
    """
    series = demand.get("series_count", 0)
    lumpy = demand.get("lumpy_series_count", 0)
    threshold = demand.get("lumpy_zero_fraction_threshold", 0)

    if not series:
        return "This dataset contains no demand history to forecast."

    if lumpy == 0:
        return (
            f"All {plural(series, 'demand series', 'demand series')} are continuous — "
            "every period has orders — so all are forecast with AutoETS. Croston-SBA "
            "is reserved for intermittent series, and this dataset has none."
        )

    smooth = series - lumpy
    return (
        f"{lumpy:,} of {series:,} demand series are intermittent — at least "
        f"{threshold:.0%} of periods have no orders at all — so those are forecast "
        f"with Croston-SBA. The other {smooth:,} use AutoETS."
    )


def pipeline_sentence(pipeline_link: dict) -> str:
    """Connects 'my data' to 'the result I just saw'."""
    stages = pipeline_link.get("stage_inputs", {})
    ingest = len(stages.get("ingest", []))
    optimize = stages.get("optimize", [])
    return (
        f"All {plural(ingest, 'table')} on this page are loaded and checked at ingest. "
        "The forecast reads the demand history; the optimizer then reads "
        f"{_join([humanize(name, TABLE_WORDS) for name in optimize])} to build the plan "
        "you see on the results screen."
    )


def build_narrative(overview: dict) -> dict[str, Any]:
    """Assemble every plain-English string the dataset view needs."""
    demand = overview["demand"]
    vertical = vertical_from_generator(overview["provenance"].get("generator"))
    return {
        "one_sentence_summary": one_sentence_summary(
            overview["network"],
            overview["products"],
            demand,
            overview["capacity"],
            vertical=vertical,
        ),
        "scenario_sentence": scenario_sentence(overview["scenario_diff"], demand),
        "forecast_method_sentence": forecast_method_sentence(demand),
        "pipeline_sentence": pipeline_sentence(overview["pipeline_link"]),
        "provenance_sentence": (
            "Every figure on this page is read from the generated files on this "
            "device. Nothing is estimated and nothing is sent off the box."
        ),
    }
