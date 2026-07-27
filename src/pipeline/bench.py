"""Phase 3 head-to-head benchmark harness."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable

from src.bench.profiler import profile_run, write_json
from src.forecast.statistical import forecast_finished_goods
from src.ingest.state import load_scenario_state
from src.optimize.baseline.policy import optimize_baseline
from src.optimize.classical.tuned import optimize_classical
from src.optimize.learned.ppo import optimize_ppo_candidate


def _row(approach: str, plan: dict, profile: dict) -> dict:
    metrics = plan["metrics"]
    return {
        "approach": approach,
        "total_cost": metrics["total_cost"],
        "objective": metrics["objective"],
        "fill_rate": metrics["fill_rate"],
        "days_of_inventory": metrics["days_of_inventory"],
        "cvar_75": metrics.get("cvar_75", 0.0),
        "latency_seconds": profile["wall_clock_seconds"],
        "peak_process_rss_mb": profile["peak_process_rss_mb"],
        "allocation_rate_gbps_proxy": profile["allocation_rate_gbps_proxy"],
        "gpu_utilization_percent": profile["gpu_utilization_percent"],
    }


def run_head_to_head(
    scenario: str,
    horizon: int = 8,
    ppo_timesteps: int = 128,
    progress_callback: Callable[[str, str], None] | None = None,
) -> dict:
    # progress_callback (optional) is invoked as (stage, status) at the REAL
    # boundaries of each stage so callers such as the SSE endpoint can stream
    # truthful progress. Default None keeps existing callers unchanged.
    def notify(stage: str, status: str) -> None:
        if progress_callback is not None:
            progress_callback(stage, status)

    notify("ingest", "running")
    state = load_scenario_state(scenario)
    notify("ingest", "complete")

    notify("forecast", "running")
    forecast = forecast_finished_goods(state, horizon=horizon)
    notify("forecast", "complete")

    notify("baseline", "running")
    with profile_run("baseline", scenario) as baseline_profile:
        baseline = optimize_baseline(state, forecast)
    notify("baseline", "complete")

    notify("classical", "running")
    with profile_run("classical", scenario) as classical_profile:
        classical = optimize_classical(state, forecast)
    notify("classical", "complete")

    notify("ppo", "running")
    with profile_run("ppo", scenario) as ppo_profile:
        ppo = optimize_ppo_candidate(state, forecast, total_timesteps=ppo_timesteps)
    notify("ppo", "complete")

    comparison = [
        _row("baseline", baseline, baseline_profile),
        _row("classical", classical, classical_profile),
        _row("ppo", ppo, ppo_profile),
    ]
    # Tie-break on latency (evidence from this run: prefer whichever approach
    # reaches the same objective faster) instead of a fixed name-based
    # preference order, which would silently decide the "winner" without any
    # basis in the actual run.
    winner = min(comparison, key=lambda row: (row["objective"], row["latency_seconds"]))
    objective_tie_across_approaches = len({round(row["objective"], 6) for row in comparison}) == 1
    result = {
        "scenario": scenario,
        "comparison": comparison,
        "winner": winner,
        "objective_tie_across_approaches": objective_tie_across_approaches,
        "plans": {
            "baseline": baseline,
            "classical": classical,
            "ppo": ppo,
        },
        "resource_profiles": {
            "baseline": baseline_profile,
            "classical": classical_profile,
            "ppo": ppo_profile,
        },
        "ppo_outcome": "won" if winner["approach"] == "ppo" else f"lost_to_{winner['approach']}",
    }
    result["artifacts"] = {
        "comparison_path": str(write_json(result, f"{scenario}-head-to-head-comparison.json")),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--ppo-timesteps", type=int, default=128)
    args = parser.parse_args()
    result = run_head_to_head(
        scenario=args.scenario,
        horizon=args.horizon,
        ppo_timesteps=args.ppo_timesteps,
    )
    print(json.dumps({"comparison": result["comparison"], "winner": result["winner"], "ppo_outcome": result["ppo_outcome"]}, indent=2, sort_keys=True))
    print(json.dumps(result["artifacts"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
