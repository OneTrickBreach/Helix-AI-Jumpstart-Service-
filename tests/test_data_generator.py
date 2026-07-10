"""
Phase 1 — Seeded Manufacturing synthetic data generator tests.

These tests call the generator through its CLI so they exercise the same entry
point used by `make data`, while writing to temporary directories.
"""

from __future__ import annotations

import csv
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "data" / "generator" / "generate.py"
SCENARIOS = [
    "baseline",
    "component-shortage-shock",
    "demand-surge",
    "stress-large",
]
EXPECTED_FILES = {
    "metadata.json",
    "nodes.csv",
    "skus.csv",
    "bom.csv",
    "demand.csv",
    "production_lines.csv",
    "lanes.csv",
    "lane_periods.csv",
    "service_targets.csv",
    "initial_inventory.csv",
}

SCHEMAS = {
    "nodes.csv": {
        "str": ["node_id", "node_type", "name", "region", "scenario"],
        "int": ["capacity_units_per_period", "storage_capacity_units", "seed"],
        "float": [],
    },
    "skus.csv": {
        "str": ["sku_id", "sku_type", "description", "scenario"],
        "int": ["seed"],
        "float": [
            "unit_holding_cost",
            "ordering_cost",
            "backorder_penalty",
            "lost_sale_penalty",
            "production_cost",
            "unit_volume_cubic_m",
        ],
    },
    "bom.csv": {
        "str": ["parent_sku_id", "component_sku_id", "scenario"],
        "int": ["quantity_per_parent", "tier_depth", "seed"],
        "float": [],
    },
    "demand.csv": {
        "str": [
            "demand_type",
            "node_id",
            "sku_id",
            "parent_finished_good_id",
            "scenario",
        ],
        "int": ["period", "quantity_units", "seed"],
        "float": [
            "base_quantity_units",
            "seasonal_factor",
            "trend_factor",
            "noise_multiplier",
            "lump_multiplier",
            "shock_multiplier",
        ],
    },
    "production_lines.csv": {
        "str": ["line_id", "plant_id", "sku_id", "scenario"],
        "int": ["max_throughput_units_per_period", "seed"],
        "float": [],
    },
    "lanes.csv": {
        "str": [
            "lane_id",
            "from_node_id",
            "to_node_id",
            "lane_type",
            "sku_scope",
            "scenario",
        ],
        "int": ["capacity_units_per_period", "distance_km", "lane_ordinal", "seed"],
        "float": [
            "lead_time_mean_days",
            "lead_time_std_days",
            "lane_cost_per_unit",
            "transport_cost_per_km",
            "co2_kg_per_unit",
        ],
    },
    "lane_periods.csv": {
        "str": ["lane_id", "scenario"],
        "int": ["period", "effective_capacity_units", "seed"],
        "float": [
            "effective_lead_time_mean_days",
            "capacity_multiplier",
            "lead_time_multiplier",
        ],
    },
    "service_targets.csv": {
        "str": ["customer_id", "sku_id", "criticality_tier", "scenario"],
        "int": ["seed"],
        "float": ["fill_rate_target", "days_inventory_target"],
    },
    "initial_inventory.csv": {
        "str": ["node_id", "sku_id", "scenario"],
        "int": ["on_hand_units", "in_transit_units", "backlog_units", "seed"],
        "float": [],
    },
}


def run_generator(output_dir: Path, scenario: str = "baseline", seed: int = 42) -> Path:
    subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--seed",
            str(seed),
            "--scenario",
            scenario,
            "--output-dir",
            str(output_dir),
        ],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return output_dir


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def generated_scenario(tmp_path_factory: pytest.TempPathFactory, scenario: str, seed: int = 42) -> Path:
    output_dir = tmp_path_factory.mktemp(f"generated-{scenario}") / scenario
    return run_generator(output_dir, scenario=scenario, seed=seed)


def pearson(xs: list[float], ys: list[float]) -> float:
    assert len(xs) == len(ys)
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    x_den = math.sqrt(sum((x - x_mean) ** 2 for x in xs))
    y_den = math.sqrt(sum((y - y_mean) ** 2 for y in ys))
    return numerator / (x_den * y_den)


def test_same_seed_and_scenario_are_byte_identical(tmp_path: Path):
    first = run_generator(tmp_path / "first", scenario="baseline", seed=42)
    second = run_generator(tmp_path / "second", scenario="baseline", seed=42)

    first_files = sorted(path.name for path in first.iterdir() if path.is_file())
    second_files = sorted(path.name for path in second.iterdir() if path.is_file())
    assert first_files == second_files == sorted(EXPECTED_FILES)

    for filename in first_files:
        assert (first / filename).read_bytes() == (second / filename).read_bytes(), filename


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_schema_required_columns_types_and_no_required_nulls(
    tmp_path_factory: pytest.TempPathFactory,
    scenario: str,
):
    output_dir = generated_scenario(tmp_path_factory, scenario)
    assert {path.name for path in output_dir.iterdir() if path.is_file()} == EXPECTED_FILES

    for filename, schema in SCHEMAS.items():
        rows = read_csv(output_dir / filename)
        assert rows, f"{filename} is empty"
        columns = set(rows[0])
        required_columns = set(schema["str"] + schema["int"] + schema["float"])
        assert required_columns.issubset(columns), filename

        for row in rows:
            for column in schema["str"]:
                assert row[column] != "", f"{filename}.{column} has a blank required value"
            for column in schema["int"]:
                assert row[column] != "", f"{filename}.{column} has a blank required value"
                int(row[column])
            for column in schema["float"]:
                assert row[column] != "", f"{filename}.{column} has a blank required value"
                assert "." in row[column], (
                    f"{filename}.{column} is a float column but rendered as "
                    f"integer '{row[column]}'"
                )
                value = float(row[column])
                assert not math.isnan(value), f"{filename}.{column} is NaN"

    metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["scenario"] == scenario
    assert metadata["seed"] == 42
    assert metadata["requested_seed"] == 42
    assert sorted(metadata["outputs"]) == sorted(EXPECTED_FILES - {"metadata.json"})


def test_component_demand_is_correlated_with_finished_goods_demand(
    tmp_path_factory: pytest.TempPathFactory,
):
    output_dir = generated_scenario(tmp_path_factory, "baseline")
    demand = read_csv(output_dir / "demand.csv")

    finished_by_period: dict[int, int] = {}
    component_by_period: dict[int, int] = {}
    for row in demand:
        period = int(row["period"])
        quantity = int(row["quantity_units"])
        if row["demand_type"] == "finished_good_customer":
            finished_by_period[period] = finished_by_period.get(period, 0) + quantity
        elif row["demand_type"] == "derived_component":
            component_by_period[period] = component_by_period.get(period, 0) + quantity

    periods = sorted(finished_by_period)
    assert periods == sorted(component_by_period)
    corr = pearson(
        [finished_by_period[period] for period in periods],
        [component_by_period[period] for period in periods],
    )
    assert corr >= 0.90


def test_baseline_demand_is_not_trivially_over_capacity(
    tmp_path_factory: pytest.TempPathFactory,
):
    output_dir = generated_scenario(tmp_path_factory, "baseline")
    demand = read_csv(output_dir / "demand.csv")
    nodes = read_csv(output_dir / "nodes.csv")

    total_plant_capacity = sum(
        int(row["capacity_units_per_period"])
        for row in nodes
        if row["node_type"] == "plant"
    )
    finished_by_period: dict[int, int] = {}
    for row in demand:
        if row["demand_type"] == "finished_good_customer":
            period = int(row["period"])
            finished_by_period[period] = finished_by_period.get(period, 0) + int(row["quantity_units"])

    avg_finished = sum(finished_by_period.values()) / len(finished_by_period)
    peak_finished = max(finished_by_period.values())
    assert avg_finished <= total_plant_capacity
    assert peak_finished <= total_plant_capacity * 1.75


def test_component_shortage_has_zero_supply_periods(
    tmp_path_factory: pytest.TempPathFactory,
):
    output_dir = generated_scenario(tmp_path_factory, "component-shortage-shock")
    lane_periods = read_csv(output_dir / "lane_periods.csv")

    zero_supply = [
        row
        for row in lane_periods
        if int(row["effective_capacity_units"]) == 0
        and row["disruption_code"] == "zero_supply_component_shortage"
    ]
    assert zero_supply
    assert all(float(row["lead_time_multiplier"]) > 1.0 for row in zero_supply)


def test_demand_surge_has_elevated_finished_goods_demand(
    tmp_path_factory: pytest.TempPathFactory,
):
    output_dir = generated_scenario(tmp_path_factory, "demand-surge")
    demand = read_csv(output_dir / "demand.csv")

    shocked = [
        int(row["quantity_units"])
        for row in demand
        if row["demand_type"] == "finished_good_customer"
        and float(row["shock_multiplier"]) > 1.0
    ]
    normal = [
        int(row["quantity_units"])
        for row in demand
        if row["demand_type"] == "finished_good_customer"
        and float(row["shock_multiplier"]) == 1.0
    ]
    assert shocked
    assert sum(shocked) / len(shocked) > (sum(normal) / len(normal)) * 1.35


def test_seed_and_scenario_metadata_are_in_outputs(tmp_path: Path):
    output_dir = run_generator(tmp_path / "metadata-check", scenario="baseline", seed=2026)
    metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["scenario"] == "baseline"
    assert metadata["seed"] == 2026
    assert metadata["requested_seed"] == 2026

    for filename in EXPECTED_FILES - {"metadata.json"}:
        rows = read_csv(output_dir / filename)
        assert {row["scenario"] for row in rows} == {"baseline"}
        assert {row["seed"] for row in rows} == {"2026"}


def test_generated_files_contain_no_pii_or_real_company_names(tmp_path_factory: pytest.TempPathFactory):
    output_dir = generated_scenario(tmp_path_factory, "stress-large")
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sorted(output_dir.iterdir()))

    forbidden_patterns = [
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"),
    ]
    for pattern in forbidden_patterns:
        assert not pattern.search(combined)

    real_names = [
        "Helix",
        "Connection",
        "Ryan",
        "Ishan",
        "Amazon",
        "Walmart",
        "Tesla",
        "Toyota",
        "Apple",
        "Microsoft",
        "NVIDIA",
    ]
    for name in real_names:
        assert name.lower() not in combined.lower()
