"""Phase 6 benchmark-suite honesty and output-shape tests."""

from __future__ import annotations

import json
from copy import deepcopy
from math import ceil

from src.bench.suite import (
    DEVICE_MEMORY_METHOD,
    build_suite_summary,
    envelope_assessment,
    render_markdown,
    summarize_scenario,
)


def _benchmark() -> dict:
    rows = [
        {
            "approach": "baseline",
            "objective": 110.0,
            "total_cost": 100.0,
            "fill_rate": 0.90,
            "days_of_inventory": 20.0,
        },
        {
            "approach": "classical",
            "objective": 90.0,
            "total_cost": 85.0,
            "fill_rate": 0.95,
            "days_of_inventory": 18.0,
        },
        {
            "approach": "ppo",
            "objective": 105.0,
            "total_cost": 97.0,
            "fill_rate": 0.92,
            "days_of_inventory": 19.0,
        },
    ]
    profiles = {
        row["approach"]: {
            "wall_clock_seconds": index / 10,
            "peak_process_rss_mb": 100.0 + index,
            "allocation_rate_gbps_proxy": index / 100,
            "gpu_utilization_percent": None,
            "gpu_metrics_status": "unavailable: test stack",
        }
        for index, row in enumerate(rows, start=1)
    }
    return {
        "scenario": "stress-large",
        "comparison": rows,
        "winner": rows[1],
        "objective_tie_across_approaches": False,
        "resource_profiles": profiles,
        "ppo_outcome": "lost_to_classical",
    }


def _scenario_summary() -> dict:
    return summarize_scenario(
        _benchmark(),
        {
            "llm_profile": {
                "tokens_per_second": 42.5,
                "peak_process_rss_mb": 512.0,
            },
            "artifacts": {},
        },
        {
            "method": DEVICE_MEMORY_METHOD,
            "sample_interval_seconds": 0.25,
            "sample_count": 4,
            "total_bytes_observed": 121 * 1024**3,
            "peak_used_bytes": 60 * 1024**3,
            "error": None,
        },
    )


def test_envelope_flag_trips_at_threshold_and_not_below():
    at_threshold = ceil(121 * 1024**3 * 0.90)
    just_below = at_threshold - 1

    assert envelope_assessment(just_below)["approaches_envelope"] is False
    assert envelope_assessment(at_threshold)["approaches_envelope"] is True
    assert envelope_assessment(None)["approaches_envelope"] is None


def test_summary_has_required_fields_and_keeps_losing_ppo():
    scenario = _scenario_summary()
    assert {row["approach"] for row in scenario["rows"]} == {
        "baseline",
        "classical",
        "ppo",
    }
    ppo = next(row for row in scenario["rows"] if row["approach"] == "ppo")
    assert ppo["ppo_outcome"] == "lost_to_classical"
    assert ppo["winner"] == "classical"
    assert ppo["gpu_utilization_percent"] is None
    assert {
        "objective",
        "total_cost",
        "fill_rate",
        "days_of_inventory",
        "latency_seconds",
        "peak_process_rss_mb",
        "device_level_peak_memory_gib",
        "allocation_rate_gbps_proxy",
        "gpu_metrics_status",
    }.issubset(ppo)


def test_summary_numbers_are_derived_from_run_outputs_not_constants():
    benchmark = _benchmark()
    benchmark["comparison"][2]["objective"] = 12345.678
    benchmark["resource_profiles"]["ppo"]["peak_process_rss_mb"] = 987.6

    scenario = summarize_scenario(
        benchmark,
        {"llm_profile": {"tokens_per_second": 1.0}, "artifacts": {}},
        {"peak_used_bytes": 2 * 1024**3},
    )
    ppo = next(row for row in scenario["rows"] if row["approach"] == "ppo")
    assert ppo["objective"] == 12345.678
    assert ppo["peak_process_rss_mb"] == 987.6
    assert ppo["device_level_peak_memory_gib"] == 2.0


def test_json_and_markdown_outputs_cover_all_scenarios():
    base = _scenario_summary()
    scenarios = [{**deepcopy(base), "scenario": name} for name in (
        "baseline",
        "component-shortage-shock",
        "demand-surge",
        "stress-large",
    )]
    for item in scenarios:
        for row in item["rows"]:
            row["scenario"] = item["scenario"]

    summary = build_suite_summary(scenarios)
    encoded = json.dumps(summary)
    markdown = render_markdown(summary)

    assert len(summary["rows"]) == 12
    assert summary["stress_large_decision"]["two_node_path_needed_for_prototype"] is False
    assert "allocation_rate_gbps_proxy" in encoded
    assert "not DRAM bandwidth" in encoded
    assert "GPU utilization is reported as unavailable" in markdown
    assert all(name in markdown for name in (
        "baseline",
        "component-shortage-shock",
        "demand-surge",
        "stress-large",
    ))
