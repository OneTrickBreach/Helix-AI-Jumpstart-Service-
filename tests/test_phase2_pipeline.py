"""Phase 2 secure API, ingest, forecast, and baseline tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from src.forecast.statistical import forecast_finished_goods
from src.ingest.state import load_scenario_state, summarize_state
from src.optimize.baseline.policy import optimize_baseline


REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "data" / "generator" / "generate.py"
EXPECTED_BASELINE_ROWS = {
    "nodes": 17,
    "skus": 28,
    "bom": 24,
    "demand": 2912,
    "production_lines": 6,
    "lanes": 30,
    "lane_periods": 1560,
    "service_targets": 32,
    "initial_inventory": 32,
}


@pytest.fixture(scope="session")
def generated_baseline(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("phase2-generated")
    output = root / "baseline"
    subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--seed",
            "42",
            "--scenario",
            "baseline",
            "--output-dir",
            str(output),
        ],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return root


def test_api_auth_and_validation(api_client, api_headers):
    payload = {"scenario": "baseline", "horizon": 4}
    assert api_client.post("/ingest/scenario", json=payload).status_code in {401, 503}
    assert api_client.post("/ingest/scenario", json=payload, headers={"X-API-Key": "bad"}).status_code == 401
    invalid = api_client.post(
        "/ingest/scenario",
        json={"scenario": "../baseline", "horizon": 0},
        headers=api_headers,
    )
    assert invalid.status_code == 422


def test_ingest_normalized_state_counts(generated_baseline: Path):
    state = load_scenario_state("baseline", data_root=generated_baseline)
    summary = summarize_state(state)
    assert summary["row_counts"] == EXPECTED_BASELINE_ROWS
    assert summary["customers"] == 8
    assert summary["finished_goods"] == 4
    assert summary["horizon_periods"] == 52


def test_forecast_shape_no_nans_and_reasonable_magnitude(generated_baseline: Path):
    state = load_scenario_state("baseline", data_root=generated_baseline)
    forecast = forecast_finished_goods(state, horizon=6)
    assert forecast["summary"]["series_count"] == 32
    assert forecast["summary"]["row_count"] == 192
    assert forecast["summary"]["forecast_total_units"] > 0
    assert 0.25 <= forecast["summary"]["forecast_vs_recent_history_ratio"] <= 4.0
    assert all(row["forecast_quantity_units"] >= 0 for row in forecast["rows"])


def test_baseline_plan_consistency(generated_baseline: Path):
    state = load_scenario_state("baseline", data_root=generated_baseline)
    forecast = forecast_finished_goods(state, horizon=4)
    plan = optimize_baseline(state, forecast)
    lane_ids = set(state.lanes["lane_id"].to_list())
    assert len(plan["plan"]) == 32
    assert all(row["inventory_position_units"] >= 0 for row in plan["plan"])
    assert {lane["lane_id"] for lane in plan["lane_assignments"]}.issubset(lane_ids)
    metrics = plan["metrics"]
    assert set(metrics["cost_breakdown"]) == {
        "holding",
        "ordering",
        "backorder",
        "lost_sale",
        "transport",
    }
    assert metrics["total_cost"] >= 0
    assert 0 <= metrics["fill_rate"] <= 1
    assert metrics["days_of_inventory"] >= 0
