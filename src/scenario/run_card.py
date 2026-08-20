"""The pre-run card: what a run will do, before it does it.

Iteration 6a Phase 3, reusing Iteration 5's confirm-card pattern — the reading,
the estimate **with its basis**, the seed, what is excluded, and the
``reaches_optimizer`` warning when it applies. Iteration 5's card earned its place
by stopping a planner from waiting on a run that could not move the answer; the
same failure is easier to hit with a slider than with a sentence.

This describes a scenario **already on disk**, so it complements
:func:`src.scenario.preview.build_preview`, which describes edits that have not
been saved yet. Read-only: it runs nothing.
"""

from __future__ import annotations

from typing import Any

from src.scenario.preview import estimate_run, series_count
from src.scenario.store import config_path, data_dir, is_custom, read_config
from src.scenario.synthesize import CANONICAL_SCENARIOS, load_base_config
from src.scenario.validate import capacity_reachability

#: What a default custom run leaves out, in the planner's words rather than flags.
EXCLUSION_TEXT = {
    "ppo": "PPO is not evaluated. It is a candidate that lost all four recorded "
           "scenarios and is kept visible for transparency, not shipped.",
    "rationale": "No written rationale. That one step takes about 20 times as long as "
                 "the whole numeric comparison, so it is off unless you ask for it.",
}


class ScenarioMissing(Exception):
    """No config on disk for this scenario."""


def load_config_for(scenario: str) -> dict[str, Any]:
    """The config a run would use, for a custom *or* a canonical scenario."""
    if is_custom(scenario):
        return read_config(scenario)
    if scenario in CANONICAL_SCENARIOS:
        return load_base_config(scenario)
    if config_path(scenario).exists():
        return read_config(scenario)
    raise ScenarioMissing(f"No configuration on disk for scenario '{scenario}'.")


def reachability_warnings(
    config: dict[str, Any],
    reachability: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """The capacity-window warning, built once and used before *and* after a run.

    The DoD wants a narrowed window warned about before the run and explained
    after it. Sharing one builder is what stops the same measured fact acquiring
    two vocabularies — the Iteration 5 wording is reused deliberately.
    """
    verdict = reachability if reachability is not None else capacity_reachability(config)
    if not verdict["applicable"] or verdict["reaches_optimizer"]:
        return []
    return [{
        "code": "capacity_window_misses_read_period",
        "message": verdict["why"],
        "detail": {
            "reaches_optimizer": False,
            "capacity_read_period": verdict["capacity_read_period"],
            "window": verdict["window"],
            "suggested_duration_periods": verdict["suggested_duration_periods"],
        },
        "do_not_read_as": "Do not read an unchanged result as resilience. The lane capacity "
                          "the optimizer reads was never touched by this window.",
    }]


def build_run_card(
    scenario: str,
    include_ppo: bool,
    include_rationale: bool,
    horizon: int = 8,
) -> dict[str, Any]:
    """Everything a planner should see before spending the compute."""
    config = load_config_for(scenario)
    custom = is_custom(scenario)
    generated = data_dir(scenario).is_dir()
    reachability = capacity_reachability(config)

    will_run = ["load the generated data", "forecast demand", "naive baseline", "tuned classical"]
    if include_ppo:
        will_run.append("PPO candidate")
    if include_rationale:
        will_run.append("written advisory rationale")

    excluded = [
        {"stage": stage, "why": EXCLUSION_TEXT[stage]}
        for stage, included in (("ppo", include_ppo), ("rationale", include_rationale))
        if not included
    ]

    warnings = reachability_warnings(config, reachability=reachability)

    return {
        "scenario": scenario,
        "is_custom": custom,
        "generated": generated,
        "reading": (
            f"Run {scenario} on the real pipeline: "
            + ", ".join(will_run) + "."
        ),
        "will_run": will_run,
        "excluded": excluded,
        # Decision 7: the seed is part of the saved config, so the card states the
        # one that will actually be used rather than a default it hopes matches.
        "fixed_inputs": {
            "seed": config.get("random_seed_override"),
            "horizon": horizon,
            "history_periods": (config.get("simulation") or {}).get("horizon_periods"),
            "finished_good_series": series_count(config),
        },
        "estimate": estimate_run(
            scenario, config,
            include_ppo=include_ppo,
            include_rationale=include_rationale,
            # The data is already on disk for a saved scenario; charging the
            # estimate for a generation step that will not happen overstates it.
            include_generate=not generated,
        ),
        "capacity_reachability": reachability,
        "warnings": warnings,
        "writes_artifact": f"benchmark/{scenario}-head-to-head-comparison.json",
        "label": (
            "CUSTOM SCENARIO — not one of the four recorded benchmark results"
            if custom else "RECORDED BENCHMARK SCENARIO"
        ),
        "runs_nothing_yet": True,
    }
