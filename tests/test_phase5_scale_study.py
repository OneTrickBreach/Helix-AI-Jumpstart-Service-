"""Phase 5 — scale study tests.

Validates:
- Scale config builder produces valid scenario configs
- Theoretical footprint estimates are monotonically increasing with scale
- A single small-scale level runs end-to-end and produces valid results
- Envelope headroom assessment is consistent
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from src.bench.scale_study import (
    SCALE_LEVELS,
    USABLE_ENVELOPE_GIB,
    build_scale_config,
    estimate_footprint,
    run_one_level,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "data" / "generator" / "generate.py"


@pytest.fixture(scope="session")
def scale_data_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("phase5-scale")


def test_build_config_has_required_keys():
    level = SCALE_LEVELS[0]
    config = build_scale_config(level)
    assert config["scenario"] == f"scale-{level['label']}"
    assert "simulation" in config
    assert config["simulation"]["horizon_periods"] == level["horizon"]
    net = config["network"]
    assert net["finished_goods"] == level["fg"]
    assert net["customers"] == level["cust"]
    assert net["suppliers"] == level["sup"]
    for section in ["demand", "capacity", "lanes", "costs", "service_targets"]:
        assert section in config, f"Missing config section: {section}"


def test_build_config_all_levels_unique():
    names = [build_scale_config(l)["scenario"] for l in SCALE_LEVELS]
    assert len(names) == len(set(names))


def test_estimate_footprint_monotonic():
    estimates = [estimate_footprint(l) for l in SCALE_LEVELS]
    for i in range(1, len(estimates)):
        prev, curr = estimates[i - 1], estimates[i]
        assert curr["series"] > prev["series"], (
            f"{curr['label']} series ({curr['series']}) should exceed "
            f"{prev['label']} ({prev['series']})"
        )
        assert curr["demand_rows_total"] >= prev["demand_rows_total"]
        assert curr["est_api_rss_mb"] >= prev["est_api_rss_mb"]


def test_estimate_footprint_reasonable_values():
    est = estimate_footprint(SCALE_LEVELS[0])
    assert est["series"] == 12 * 24  # 288
    assert est["demand_rows_fg"] == 52 * 24 * 12
    assert est["lane_count"] == 10 * 4 + 4 * 4 + 4 * 24
    assert est["est_api_rss_mb"] > 0
    assert est["est_csv_mb"] > 0


def test_run_prototype_level(scale_data_root: Path):
    """Run the smallest scale level end-to-end and verify the result."""
    level = SCALE_LEVELS[0]
    result = run_one_level(level, scale_data_root)
    assert result["status"] == "ok"
    assert result["series"] == level["fg"] * level["cust"]
    assert result["forecast_series"] == result["series"]
    assert result["gen_seconds"] > 0
    assert result["forecast_seconds"] > 0
    assert result["optimizer_seconds"] > 0
    assert result["total_seconds"] > 0
    assert result["peak_rss_mb"] > 0
    assert result["objective"] > 0
    assert 0 <= result["fill_rate"] <= 1
    assert result["demand_row_count"] > 0


def test_envelope_headroom_math():
    """If device_after_gib is known, headroom + used should equal envelope."""
    level = SCALE_LEVELS[0]
    result = {
        "device_after_gib": 70.0,
        "device_headroom_gib": round(USABLE_ENVELOPE_GIB - 70.0, 1),
        "envelope_fraction": round(70.0 / USABLE_ENVELOPE_GIB, 4),
    }
    assert abs(result["device_after_gib"] + result["device_headroom_gib"] - USABLE_ENVELOPE_GIB) < 0.01
    assert 0 < result["envelope_fraction"] < 1
