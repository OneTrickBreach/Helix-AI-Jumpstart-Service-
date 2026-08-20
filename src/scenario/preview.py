"""Assemble the preview of a custom scenario. Writes nothing, runs nothing.

This is the Phase 1 product surface: a planner can see exactly what their edits
resolve to, what changed against ``baseline``, whether the disruption they built
can actually move the answer, and roughly what a run would cost — all before any
file is created and before any compute is spent.

The run estimate carries **its basis** per component, following Iteration 5's
confirm-card pattern (§1.8). ``_recorded_latencies`` returning ``{}`` rather than
inventing a figure is reused as-is: a scenario with no run on record borrows the
base scenario's recorded numbers and *says so*.
"""

from __future__ import annotations

import json
from typing import Any

from src.scenario.ledger import (
    CONDITIONAL,
    INERT,
    LABEL_ONLY,
    NON_SETTING_KEYS,
    REACH_LABELS,
    SETTINGS,
    SETTINGS_BY_KEY,
    UNCONDITIONAL,
    ledger_counts,
)
from src.scenario.synthesize import (
    BASE_SCENARIO,
    SIMPLE_CONTROLS,
    SIMPLE_CONTROLS_BY_NAME,
    complete_config,
    expand_simple,
    load_base_config,
)
from src.scenario.validate import (
    capacity_reachability,
    scenario_name_for,
    validate_custom_scenario,
)

#: Measured on this device on 2026-08-20 (plan §1.1). Every one of these is a real
#: figure from a real run, not a guess, and each is reported with that provenance.
MEASURED_GENERATE_SECONDS = 0.23
MEASURED_SECONDS_PER_SERIES = 0.025
MEASURED_PPO_SECONDS = 2.65
MEASURED_RATIONALE_SECONDS = 20.1
FALLBACK_OPTIMIZE_SECONDS = 0.19

#: Groups excluded from the config diff. Taken from the ledger's own list of keys
#: that are not editable settings, so this and ``_scenario_diff``'s equivalent
#: cannot disagree about what counts as a change.
DIFF_SKIP_GROUPS = frozenset(NON_SETTING_KEYS)


def series_count(config: dict[str, Any]) -> int:
    """Finished-good demand series: one per (customer, finished good)."""
    network = config.get("network") or {}
    return int(network.get("customers") or 0) * int(network.get("finished_goods") or 0)


def config_changes(config: dict[str, Any], base: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Config deltas in ``_scenario_diff``'s exact shape, plus a reach annotation.

    Same one-level-deep grouping the dataset view uses, so the existing "what did
    I change?" panel renders this without modification. The added ``reach`` field
    is what makes a no-op edit visible *in the diff itself* rather than only in a
    warning.
    """
    base_config = base if base is not None else load_base_config()
    changes: list[dict[str, Any]] = []
    for group in sorted(set(config) | set(base_config)):
        if group in DIFF_SKIP_GROUPS:
            continue
        mine, theirs = config.get(group), base_config.get(group)
        if isinstance(mine, dict) and isinstance(theirs, dict):
            for key in sorted(set(mine) | set(theirs)):
                if mine.get(key) != theirs.get(key):
                    changes.append(_change(group, key, theirs.get(key), mine.get(key)))
        elif mine != theirs:
            changes.append(_change(group, group, theirs, mine))
    return changes


def _change(group: str, parameter: str, baseline_value: Any, scenario_value: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "group": group,
        "parameter": parameter,
        "baseline_value": baseline_value,
        "scenario_value": scenario_value,
    }
    setting = SETTINGS_BY_KEY.get(f"{group}.{parameter}")
    if setting is not None:
        entry["reach"] = setting.reach
        entry["reach_label"] = REACH_LABELS[setting.reach]
        entry["reaches_optimizer"] = setting.reaches_optimizer
        return entry

    # A whole block turning on (``lane_disruption: null`` -> a dict) or a cost
    # family changing as a unit has no single setting behind it. Report the
    # strongest reach among the settings it contains, so a UI never has to
    # special-case a missing field — and so a block whose every member is inert
    # is still labelled as such.
    # ``parameter == group`` is a whole top-level block turning on — the
    # ``lane_disruption: null`` -> dict case, which is the commonest change of all
    # and was silently unlabelled until a review caught it.
    prefix = f"{group}." if parameter == group else f"{group}.{parameter}."
    nested = [item for item in SETTINGS if item.key.startswith(prefix)]
    if not nested:
        return entry
    for reach in (UNCONDITIONAL, CONDITIONAL, INERT, LABEL_ONLY):
        if any(item.reach == reach for item in nested):
            entry["reach"] = reach
            entry["reach_label"] = REACH_LABELS[reach]
            entry["reaches_optimizer"] = reach in (UNCONDITIONAL, CONDITIONAL)
            entry["contains_settings"] = len(nested)
            break
    return entry


def recorded_latencies(scenario: str) -> dict[str, float]:
    """Per-approach latencies from a recorded run, or ``{}`` if there is none.

    Mirrors ``src.api.pipeline._recorded_latencies`` deliberately rather than
    importing it: ``pipeline`` imports this module, so reaching back would be a
    circular import. The behaviour that matters is the same one — return nothing
    rather than invent a figure.
    """
    from src.bench.profiler import benchmark_dir

    path = benchmark_dir() / f"{scenario}-head-to-head-comparison.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {
        str(row["approach"]): float(row["latency_seconds"])
        for row in payload.get("comparison", [])
        if "approach" in row and "latency_seconds" in row
    }


def estimate_run(
    scenario_name: str,
    config: dict[str, Any],
    include_ppo: bool = False,
    include_rationale: bool = False,
    base_scenario: str = BASE_SCENARIO,
) -> dict[str, Any]:
    """What a run would cost, component by component, each with its basis."""
    recorded = recorded_latencies(scenario_name)
    basis_scenario = scenario_name
    if not recorded:
        recorded = recorded_latencies(base_scenario)
        basis_scenario = base_scenario

    components: list[dict[str, Any]] = [
        {
            "stage": "generate",
            "seconds": MEASURED_GENERATE_SECONDS,
            "basis": "measured on this device on 2026-08-20 for a baseline-sized network "
                     "(0.23 s; 0.55 s at stress-large's 42 locations)",
        }
    ]
    series = series_count(config)
    components.append({
        "stage": "forecast",
        "seconds": round(series * MEASURED_SECONDS_PER_SERIES, 2),
        "basis": f"{series} finished-good series x ~25 ms/series, the measured forecast "
                 f"ceiling from the Iteration 3 scale study",
    })

    if recorded:
        optimize_seconds = sum(
            value for key, value in recorded.items() if key in ("baseline", "classical")
        )
        basis = (
            f"recorded per-approach latencies from {basis_scenario}'s last run"
            if basis_scenario == scenario_name
            else f"no run on record for this scenario, so {basis_scenario}'s recorded "
                 f"latencies are used instead"
        )
    else:
        optimize_seconds = FALLBACK_OPTIMIZE_SECONDS
        basis = "no run on record for this scenario or for the base scenario, so this is the "\
                "measured 2026-08-20 figure for baseline + tuned classical"
    components.append({
        "stage": "optimize",
        "seconds": round(optimize_seconds, 2),
        "basis": basis,
    })

    if include_ppo:
        components.append({
            "stage": "ppo",
            "seconds": MEASURED_PPO_SECONDS,
            "basis": "measured 2026-08-20 at 128 timesteps; PPO is evaluated-not-shipped and "
                     "lost all four recorded scenarios",
        })
    if include_rationale:
        components.append({
            "stage": "rationale",
            "seconds": MEASURED_RATIONALE_SECONDS,
            "basis": "measured 2026-08-20 (llm_finalized, 5 citations). This one stage is "
                     "~20x the entire numeric comparison, which is why it is off by default",
        })

    total = round(sum(float(item["seconds"]) for item in components), 2)
    return {
        "total_seconds": total,
        "components": components,
        "excluded": [
            stage for stage, included in (("ppo", include_ppo), ("rationale", include_rationale))
            if not included
        ],
        "note": "An estimate from measured components, not a promise. The forecast is the "
                "known ceiling; the optimizer is the fast part.",
    }


def build_preview(
    slug: str,
    overrides: dict[str, Any] | None = None,
    simple: dict[str, Any] | None = None,
    seed: int = 12345,
    description: str | None = None,
    run_horizon: int = 8,
    include_ppo: bool = False,
    include_rationale: bool = False,
) -> dict[str, Any]:
    """The whole read-only preview. Nothing here touches the filesystem."""
    base = load_base_config()
    resolved_overrides: dict[str, Any] = {}
    simple_error: dict[str, Any] | None = None
    if simple:
        try:
            resolved_overrides.update(expand_simple(simple, base))
        except KeyError as exc:
            name = str(exc.args[0]) if exc.args else "?"
            simple_error = {
                "code": "unknown_simple_control",
                "field": name,
                "message": f"'{name}' is not one of the {len(SIMPLE_CONTROLS)} simple "
                           f"controls. The settings endpoint lists them.",
            }
        except (TypeError, ValueError) as exc:
            # A grouped control ("demand spike: 1.75x for 8 weeks from week 20") is
            # several fields, so it needs an object; a scale control needs a number.
            # Saying either "does not exist" would send the planner looking for the
            # wrong problem, and letting the ValueError out would be a 500.
            name = str(exc.args[0]) if exc.args else "?"
            control = SIMPLE_CONTROLS_BY_NAME.get(name)
            if control is not None and control.kind == "group":
                needs = f"an object with {', '.join(control.fields)}"
            else:
                needs = "a number"
            simple_error = {
                "code": "wrong_type",
                "field": name,
                "message": f"'{name}' needs {needs} — not the value given.",
            }
    if overrides:
        resolved_overrides.update(overrides)

    scenario_name = scenario_name_for(slug)
    config = complete_config(
        scenario_name,
        overrides=resolved_overrides,
        seed=seed,
        description=description,
    )
    validation = validate_custom_scenario(
        slug, config, overrides=resolved_overrides, run_horizon=run_horizon,
        description=description,
    )
    payload = validation.as_dict()
    if simple_error is not None:
        payload["ok"] = False
        payload["refusals"] = [simple_error, *payload["refusals"]]

    changes = config_changes(config, base)
    return {
        "scenario": scenario_name,
        "slug": slug,
        "is_custom": True,
        "base_scenario": BASE_SCENARIO,
        "seed": int(seed),
        "validation": payload,
        "resolved_config": config,
        "resolved_overrides": resolved_overrides,
        "config_changes": changes,
        "config_changes_count": len(changes),
        "capacity_reachability": capacity_reachability(config),
        "run_estimate": estimate_run(
            scenario_name, config,
            include_ppo=include_ppo, include_rationale=include_rationale,
        ),
        "ledger": ledger_counts(),
        "writes_nothing": True,
        "runs_nothing": True,
        "label": "CUSTOM SCENARIO — not one of the four recorded benchmark results",
    }
