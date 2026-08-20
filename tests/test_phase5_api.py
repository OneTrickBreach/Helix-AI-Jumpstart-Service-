"""Phase 5 scenario listing and comparison API tests."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from src.api.health import app


API_KEY = "phase5-test-key"


def _headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


def _benchmark_result() -> dict:
    baseline_metrics = {
        "total_cost": 100.0,
        "objective": 100.0,
        "fill_rate": 0.9,
        "days_of_inventory": 20.0,
        "cost_breakdown": {
            "holding": 20.0,
            "ordering": 10.0,
            "backorder": 5.0,
            "lost_sale": 3.0,
            "transport": 12.0,
        },
    }
    classical_metrics = {
        "total_cost": 90.0,
        "objective": 90.0,
        "fill_rate": 0.94,
        "days_of_inventory": 18.0,
        "cost_breakdown": {
            "holding": 18.0,
            "ordering": 9.0,
            "backorder": 3.0,
            "lost_sale": 1.0,
            "transport": 10.0,
        },
    }
    comparison = [
        {
            "approach": "baseline",
            **{key: baseline_metrics[key] for key in ["total_cost", "objective", "fill_rate", "days_of_inventory"]},
            "latency_seconds": 0.1,
            "peak_process_rss_mb": 100.0,
            "allocation_rate_gbps_proxy": 1.0,
            "gpu_utilization_percent": 0.0,
        },
        {
            "approach": "classical",
            **{key: classical_metrics[key] for key in ["total_cost", "objective", "fill_rate", "days_of_inventory"]},
            "latency_seconds": 0.2,
            "peak_process_rss_mb": 110.0,
            "allocation_rate_gbps_proxy": 2.0,
            "gpu_utilization_percent": 0.0,
        },
        {
            "approach": "ppo",
            "total_cost": 120.0,
            "objective": 120.0,
            "fill_rate": 0.88,
            "days_of_inventory": 22.0,
            "latency_seconds": 0.3,
            "peak_process_rss_mb": 115.0,
            "allocation_rate_gbps_proxy": 1.5,
            "gpu_utilization_percent": 0.0,
        },
    ]
    return {
        "scenario": "baseline",
        "comparison": comparison,
        "winner": comparison[1],
        "objective_tie_across_approaches": False,
        "plans": {
            "baseline": {"metrics": baseline_metrics, "plan": [], "policy": {}, "cost_breakdown": baseline_metrics["cost_breakdown"]},
            "classical": {"metrics": classical_metrics, "plan": [], "policy": {}, "cost_breakdown": classical_metrics["cost_breakdown"]},
            "ppo": {"metrics": comparison[2], "plan": [], "policy": {}, "cost_breakdown": {}},
        },
        "resource_profiles": {
            "baseline": {
                "wall_clock_seconds": 0.1,
                "peak_process_rss_mb": 100.0,
                "allocation_rate_gbps_proxy": 1.0,
                "cpu_utilization_percent": 10.0,
                "gpu_utilization_percent": 0.0,
                "gpu_memory_used_mb": None,
                "gpu_metrics_status": "unavailable: test stack",
            },
            "classical": {
                "wall_clock_seconds": 0.2,
                "peak_process_rss_mb": 110.0,
                "allocation_rate_gbps_proxy": 2.0,
                "cpu_utilization_percent": 20.0,
                "gpu_utilization_percent": 0.0,
                "gpu_memory_used_mb": None,
                "gpu_metrics_status": "unavailable: test stack",
            },
            "ppo": {
                "wall_clock_seconds": 0.3,
                "peak_process_rss_mb": 115.0,
                "allocation_rate_gbps_proxy": 1.5,
                "cpu_utilization_percent": 30.0,
                "gpu_utilization_percent": 0.0,
                "gpu_memory_used_mb": None,
                "gpu_metrics_status": "unavailable: test stack",
            },
        },
        "ppo_outcome": "lost_to_classical",
        "artifacts": {},
    }


def test_scenarios_requires_auth_and_lists_discovered_configs(monkeypatch):
    monkeypatch.setenv("HELIX_API_KEY", API_KEY)
    client = TestClient(app)

    assert client.get("/scenarios").status_code == 401
    response = client.get("/scenarios", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    scenarios = body["data"]["scenarios"]
    names = {item["scenario"] for item in scenarios}
    assert {"baseline", "component-shortage-shock", "demand-surge", "stress-large"}.issubset(names)
    baseline = next(item for item in scenarios if item["scenario"] == "baseline")
    assert baseline["config_path"] == "data/scenarios/baseline.yaml"
    assert "description" in baseline


def test_scenario_comparison_post_reuses_single_benchmark_result(monkeypatch):
    monkeypatch.setenv("HELIX_API_KEY", API_KEY)
    calls = {"benchmark": 0, "rationale": 0}

    def fake_benchmark(scenario: str, horizon: int, ppo_timesteps: int,
                       progress_callback=None, include_ppo: bool = True):
        calls["benchmark"] += 1
        assert (scenario, horizon, ppo_timesteps) == ("baseline", 4, 16)
        # Iteration 6a decision 8: a recorded scenario keeps its existing full
        # behaviour, so PPO is still evaluated unless the caller opts out.
        assert include_ppo is True
        return _benchmark_result()

    def fake_rationale(benchmark_result: dict, top_k: int, extra_documents: list[dict]):
        calls["rationale"] += 1
        assert benchmark_result["winner"]["approach"] == "classical"
        assert top_k == 3
        assert extra_documents == []
        return {
            "advisory": True,
            "label": "ADVISORY ONLY",
            "scenario": "baseline",
            "selected_approach": "classical",
            "advisory_rationale": "ADVISORY ONLY: Use the benchmark-selected plan.",
            "citations": [],
            "prompt_injection_flags": [],
        }

    monkeypatch.setattr("src.api.pipeline.run_head_to_head", fake_benchmark)
    monkeypatch.setattr("src.api.pipeline.generate_advisory_rationale", fake_rationale)
    client = TestClient(app)

    response = client.post(
        "/scenario-comparison",
        json={"scenario": "baseline", "horizon": 4, "ppo_timesteps": 16, "top_k": 3},
        headers=_headers(),
    )

    assert response.status_code == 200
    assert calls == {"benchmark": 1, "rationale": 1}
    payload = response.json()["data"]
    assert payload["benchmark"]["winner"]["approach"] == "classical"
    assert payload["rationale"]["label"] == "ADVISORY ONLY"


def test_scenario_comparison_sse_emits_stage_events_and_final_payload(monkeypatch):
    monkeypatch.setenv("HELIX_API_KEY", API_KEY)
    calls = {"benchmark": 0}

    def fake_benchmark(scenario: str, horizon: int, ppo_timesteps: int,
                       progress_callback=None, include_ppo: bool = True):
        calls["benchmark"] += 1
        assert include_ppo is True, "a recorded scenario still evaluates PPO by default"
        # The SSE endpoint must drive real per-stage progress through this
        # callback, not fake it up front, so exercise it here.
        if progress_callback is not None:
            for stage in ("ingest", "forecast", "baseline", "classical", "ppo"):
                progress_callback(stage, "running")
                progress_callback(stage, "complete")
        return _benchmark_result()

    def fake_rationale(benchmark_result: dict, top_k: int, extra_documents: list[dict]):
        return {
            "advisory": True,
            "label": "ADVISORY ONLY",
            "scenario": benchmark_result["scenario"],
            "selected_approach": benchmark_result["winner"]["approach"],
            "advisory_rationale": "ADVISORY ONLY: Evidence selects classical.",
            "citations": [],
            "prompt_injection_flags": [],
        }

    monkeypatch.setattr("src.api.pipeline.run_head_to_head", fake_benchmark)
    monkeypatch.setattr("src.api.pipeline.generate_advisory_rationale", fake_rationale)
    client = TestClient(app)

    with client.stream(
        "GET",
        "/scenario-comparison/stream?scenario=baseline&horizon=4&ppo_timesteps=16&top_k=3",
        headers=_headers(),
    ) as response:
        assert response.status_code == 200
        body = response.read().decode("utf-8")

    assert calls["benchmark"] == 1
    assert "event: stage" in body
    assert '"stage": "baseline"' in body
    # Progress must be truthful: real running/complete transitions per stage,
    # including the rag stage emitted around the rationale call.
    assert '"status": "running"' in body
    assert '"status": "complete"' in body
    assert '"stage": "rag"' in body
    assert body.index('"stage": "ingest"') < body.index('"stage": "ppo"')
    assert "event: done" in body
    done_line = [line for line in body.splitlines() if line.startswith("data: ")][-1]
    done_payload = json.loads(done_line.removeprefix("data: "))
    assert done_payload["data"]["benchmark"]["winner"]["approach"] == "classical"
    assert done_payload["data"]["rationale"]["label"] == "ADVISORY ONLY"
