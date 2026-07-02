"""One-command Phase 2 pipeline: ingest -> forecast -> baseline optimize."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.bench.profiler import profile_run, write_json
from src.forecast.statistical import forecast_finished_goods
from src.ingest.state import load_scenario_state, summarize_state
from src.optimize.baseline.policy import optimize_baseline


def run_baseline_pipeline(scenario: str, horizon: int = 8) -> dict:
    with profile_run("phase2_baseline_pipeline", scenario) as profile:
        state = load_scenario_state(scenario)
        forecast = forecast_finished_goods(state, horizon=horizon)
        plan = optimize_baseline(state, forecast)
        result = {
            "scenario": scenario,
            "ingest": summarize_state(state),
            "forecast": forecast,
            "baseline": plan,
        }
    result["resource_profile"] = profile
    result["artifacts"] = {
        "plan_metrics_path": str(write_json(result, f"{scenario}-baseline-plan-metrics.json")),
        "resource_profile_path": str(write_json(profile, f"{scenario}-baseline-resource-profile.json")),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--horizon", type=int, default=8)
    args = parser.parse_args()
    result = run_baseline_pipeline(args.scenario, horizon=args.horizon)
    print(json.dumps(result["baseline"]["metrics"], indent=2, sort_keys=True))
    print(json.dumps(result["artifacts"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
