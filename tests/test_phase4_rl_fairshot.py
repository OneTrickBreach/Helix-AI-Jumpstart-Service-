"""Phase 4 — RL fair-shot tests.

Validates:
- Per-period MDP produces consistent results with build_plan (static multipliers)
- CVaR computation is correct
- PPO env state transitions are meaningful (not static)
- Episode plan extraction matches accumulated costs
- Benchmark harness includes CVaR in comparison rows
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from src.forecast.statistical import forecast_finished_goods
from src.ingest.state import load_scenario_state
from src.optimize.common import PolicyParams, build_plan, compute_cvar
from src.optimize.learned.env import MultiEchelonInventoryEnv

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "data" / "generator" / "generate.py"


@pytest.fixture(scope="session")
def generated_phase4(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("phase4-generated")
    for scenario in ["baseline", "component-shortage-shock"]:
        subprocess.run(
            [
                sys.executable,
                str(GENERATOR),
                "--seed", "42",
                "--scenario", scenario,
                "--output-dir", str(root / scenario),
            ],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
    return root


def test_cvar_trivial_cases():
    assert compute_cvar([], alpha=0.75) == 0.0
    assert compute_cvar([10.0], alpha=0.75) == 10.0
    assert compute_cvar([1.0, 2.0, 3.0, 4.0], alpha=0.75) == 4.0
    four = [1.0, 2.0, 3.0, 100.0]
    assert compute_cvar(four, alpha=0.75) == 100.0
    two_worst = compute_cvar(four, alpha=0.50)
    assert abs(two_worst - 51.5) < 0.01


def test_cvar_ordering_invariant():
    costs_a = [5.0, 1.0, 10.0, 3.0]
    costs_b = [10.0, 3.0, 5.0, 1.0]
    assert compute_cvar(costs_a, 0.75) == compute_cvar(costs_b, 0.75)


def test_build_plan_includes_period_costs_and_cvar(generated_phase4: Path):
    state = load_scenario_state("baseline", data_root=generated_phase4)
    forecast = forecast_finished_goods(state, horizon=4)
    plan = build_plan(state, forecast, PolicyParams(), "test", "ortools")
    metrics = plan["metrics"]
    assert "period_costs" in metrics
    assert "cvar_75" in metrics
    assert len(metrics["period_costs"]) == 4
    assert all(isinstance(c, float) for c in metrics["period_costs"])
    assert metrics["cvar_75"] >= 0
    assert abs(sum(metrics["period_costs"]) - metrics["total_cost"]) < 1.0


def test_env_static_multipliers_match_build_plan(generated_phase4: Path):
    """With constant multipliers every period, the env should produce the same
    objective as build_plan with those multipliers."""
    state = load_scenario_state("baseline", data_root=generated_phase4)
    horizon = 4
    forecast = forecast_finished_goods(state, horizon=horizon)
    params = PolicyParams(0.9, 1.0, 0.85)

    ref_plan = build_plan(state, forecast, params, "ref", "ortools")
    ref_obj = ref_plan["metrics"]["objective"]

    env = MultiEchelonInventoryEnv(state, horizon=horizon)
    obs, _ = env.reset()
    for _ in range(horizon):
        obs, _, terminated, _, _ = env.step(np.array([0.9, 1.0, 0.85]))
        if terminated:
            break
    mdp_plan = env.extract_plan()
    mdp_obj = mdp_plan["metrics"]["objective"]

    assert abs(mdp_obj - ref_obj) < 0.01, (
        f"MDP objective {mdp_obj} vs build_plan {ref_obj} differ by "
        f"{abs(mdp_obj - ref_obj):.4f} (should match with static multipliers)"
    )


def test_env_obs_changes_between_steps(generated_phase4: Path):
    """Observations must change between steps — demand is fulfilled,
    inventory depletes, pipeline grows."""
    state = load_scenario_state("component-shortage-shock", data_root=generated_phase4)
    env = MultiEchelonInventoryEnv(state, horizon=4)
    obs0, _ = env.reset()
    obs1, _, _, _, _ = env.step(np.array([1.0, 1.0, 1.0]))
    assert not np.allclose(obs0, obs1), "Observation should change after a step"


def test_env_episode_costs_sum_to_total(generated_phase4: Path):
    state = load_scenario_state("baseline", data_root=generated_phase4)
    horizon = 4
    env = MultiEchelonInventoryEnv(state, horizon=horizon)
    obs, _ = env.reset()
    total_reward = 0.0
    for _ in range(horizon):
        obs, reward, terminated, _, info = env.step(np.array([1.0, 1.0, 1.0]))
        total_reward += reward
        if terminated:
            break
    plan = env.extract_plan()
    assert abs(-total_reward - plan["metrics"]["total_cost"]) < 1.0


def test_env_plan_has_required_fields(generated_phase4: Path):
    state = load_scenario_state("baseline", data_root=generated_phase4)
    env = MultiEchelonInventoryEnv(state, horizon=4)
    obs, _ = env.reset()
    for _ in range(4):
        obs, _, terminated, _, _ = env.step(np.array([1.0, 1.0, 1.0]))
        if terminated:
            break
    plan = env.extract_plan()

    assert plan["method"] == "ppo_candidate"
    assert "policy" in plan
    assert plan["policy"]["adaptive"] is True
    assert "per_period_actions" in plan["policy"]
    assert len(plan["policy"]["per_period_actions"]) == 4

    metrics = plan["metrics"]
    for key in [
        "cost_breakdown", "total_cost", "fill_rate", "days_of_inventory",
        "total_order_units", "objective", "period_costs", "cvar_75",
    ]:
        assert key in metrics, f"Missing metric: {key}"
    assert 0 <= metrics["fill_rate"] <= 1
    assert metrics["total_cost"] >= 0
