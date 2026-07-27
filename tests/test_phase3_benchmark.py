"""Phase 3 tuned-classical, PPO, and benchmark harness tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from src.forecast.statistical import forecast_finished_goods
from src.ingest.state import load_scenario_state
from src.optimize.baseline.policy import optimize_baseline
from src.optimize.classical.tuned import optimize_classical
from src.optimize.learned.env import MultiEchelonInventoryEnv
from src.optimize.learned.ppo import optimize_ppo_candidate
from src.pipeline.bench import run_head_to_head


REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "data" / "generator" / "generate.py"


@pytest.fixture(scope="session")
def generated_phase3(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("phase3-generated")
    for scenario in ["baseline", "component-shortage-shock"]:
        subprocess.run(
            [
                sys.executable,
                str(GENERATOR),
                "--seed",
                "42",
                "--scenario",
                scenario,
                "--output-dir",
                str(root / scenario),
            ],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
    return root


def test_classical_matches_or_beats_baseline(generated_phase3: Path):
    state = load_scenario_state("baseline", data_root=generated_phase3)
    forecast = forecast_finished_goods(state, horizon=4)
    baseline = optimize_baseline(state, forecast)
    classical = optimize_classical(state, forecast, n_trials=4)
    assert classical["tuning"]["matched_or_beat_baseline"] is True
    assert classical["metrics"]["objective"] <= baseline["metrics"]["objective"]


def test_ppo_env_steps_and_candidate_plan_valid(generated_phase3: Path):
    state = load_scenario_state("component-shortage-shock", data_root=generated_phase3)
    env = MultiEchelonInventoryEnv(state, horizon=2)
    obs, _ = env.reset(seed=7)
    next_obs, reward, terminated, truncated, info = env.step(np.array([0.9, 1.0, 0.8]))
    assert obs.shape == next_obs.shape
    assert np.isfinite(reward)
    assert not truncated
    assert "period_cost" in info
    assert np.isfinite(info["period_cost"])
    # Complete the episode and extract a plan
    obs2, reward2, terminated2, _, _ = env.step(np.array([0.9, 1.0, 0.8]))
    assert terminated2
    plan = env.extract_plan()
    assert plan["method"] == "ppo_candidate"
    assert plan["metrics"]["total_cost"] >= 0
    assert 0 <= plan["metrics"]["fill_rate"] <= 1
    assert "period_costs" in plan["metrics"]
    assert "cvar_75" in plan["metrics"]
    # Also test the full optimize path
    forecast = forecast_finished_goods(state, horizon=4)
    full_plan = optimize_ppo_candidate(state, forecast, total_timesteps=16)
    assert full_plan["method"] == "ppo_candidate"
    assert full_plan["metrics"]["total_cost"] >= 0


@pytest.mark.parametrize("scenario", ["baseline", "component-shortage-shock"])
def test_benchmark_harness_has_all_approaches(monkeypatch, generated_phase3: Path, scenario: str):
    import src.ingest.state as state_module

    original = state_module.DEFAULT_DATA_ROOT
    monkeypatch.setattr(state_module, "DEFAULT_DATA_ROOT", generated_phase3)
    monkeypatch.setattr("src.pipeline.bench.load_scenario_state", lambda name: load_scenario_state(name, data_root=generated_phase3))
    result = run_head_to_head(scenario, horizon=4, ppo_timesteps=16)
    approaches = {row["approach"] for row in result["comparison"]}
    assert approaches == {"baseline", "classical", "ppo"}
    for row in result["comparison"]:
        assert {
            "total_cost",
            "fill_rate",
            "days_of_inventory",
            "latency_seconds",
            "peak_process_rss_mb",
            "allocation_rate_gbps_proxy",
        }.issubset(row)
    assert result["winner"]["approach"] in approaches
    assert result["ppo_outcome"] in {"won", "lost_to_baseline", "lost_to_classical"}
