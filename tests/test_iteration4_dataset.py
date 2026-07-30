"""Iteration 4, Phase 1 — dataset overview API.

The load-bearing test here is `test_overview_counts_reconcile_with_ingest`: the
overview must agree with the row counts the pipeline itself ingests. If those two
ever drift, the dataset view is lying about the data the result ran on.

The anti-fabrication guarantee is proved twice — once by grepping the module for
the real topology counts, and once behaviourally, by mutating a copy of the data
and asserting the overview follows it.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

import pytest

from src.dataset import overview as overview_module
from src.dataset.overview import (
    DatasetNotGeneratedError,
    UnknownScenarioError,
    build_dataset_overview,
    read_table_csv,
)
from src.ingest.state import DEFAULT_DATA_ROOT, REQUIRED_TABLES, load_scenario_state


ALL_SCENARIOS = ["baseline", "component-shortage-shock", "demand-surge", "stress-large"]

# Budgets from the Iteration 4 plan. If `stress-large` breaches these, aggregate
# harder in the module — do not raise the numbers here.
STRESS_PAYLOAD_BUDGET_BYTES = 250_000
STRESS_LATENCY_BUDGET_SECONDS = 2.0


def _generated(scenario: str) -> bool:
    return (DEFAULT_DATA_ROOT / scenario).is_dir()


requires_baseline = pytest.mark.skipif(
    not _generated("baseline"), reason="baseline data not generated; run `make demo-data`"
)


@requires_baseline
def test_overview_counts_reconcile_with_ingest():
    """Every table count in the overview equals what `load_scenario_state` ingests."""
    scenario = "baseline"
    state = load_scenario_state(scenario)
    ingest_counts = state.row_counts()
    data = build_dataset_overview(scenario)

    # provenance.source_files is the direct per-table mirror of ingest.
    reported = {entry["table"]: entry["rows"] for entry in data["provenance"]["source_files"]}
    assert reported == ingest_counts, "provenance row counts drifted from ingest"

    # The aggregated sections must agree with the same source of truth.
    assert data["network"]["node_count"] == ingest_counts["nodes"]
    assert data["products"]["sku_count"] == ingest_counts["skus"]
    assert data["products"]["bom_row_count"] == ingest_counts["bom"]
    assert data["demand"]["total_rows"] == ingest_counts["demand"]
    assert data["capacity"]["production_line_count"] == ingest_counts["production_lines"]
    assert data["lanes"]["lane_count"] == ingest_counts["lanes"]
    assert data["lanes"]["lane_period_row_count"] == ingest_counts["lane_periods"]
    assert data["service_targets"]["row_count"] == ingest_counts["service_targets"]
    assert data["initial_inventory"]["row_count"] == ingest_counts["initial_inventory"]

    # Sub-counts must partition their totals rather than merely look plausible.
    assert sum(data["network"]["nodes_by_type"].values()) == ingest_counts["nodes"]
    assert sum(data["products"]["sku_count_by_type"].values()) == ingest_counts["skus"]
    assert sum(data["demand"]["rows_by_type"].values()) == ingest_counts["demand"]
    assert sum(data["lanes"]["count_by_type"].values()) == ingest_counts["lanes"]
    split = data["demand"]["forecast_method_split"]
    assert split["croston_sba"] + split["auto_ets"] == data["demand"]["series_count"]


@requires_baseline
def test_overview_is_deterministic():
    """Two builds over unchanged files serialize byte-identically."""
    first = json.dumps(build_dataset_overview("baseline"), sort_keys=False)
    second = json.dumps(build_dataset_overview("baseline"), sort_keys=False)
    assert first == second


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_every_scenario_builds(scenario: str):
    if not _generated(scenario):
        pytest.skip(f"{scenario} not generated; run `make demo-data`")
    data = build_dataset_overview(scenario)
    expected_sections = {
        "provenance",
        "at_a_glance",
        "network",
        "products",
        "demand",
        "lanes",
        "capacity",
        "costs",
        "service_targets",
        "initial_inventory",
        "scenario_diff",
        "pipeline_link",
    }
    assert expected_sections <= set(data)
    assert data["provenance"]["is_synthetic"] is True
    assert data["provenance"]["effective_seed"] is not None
    assert len(data["at_a_glance"]) == len(
        [tile for tile in data["at_a_glance"] if tile["label"]]
    )


@pytest.mark.skipif(
    not _generated("stress-large"), reason="stress-large not generated"
)
def test_stress_large_stays_within_payload_and_latency_budget():
    build_dataset_overview("stress-large")  # warm any lazy imports
    start = time.perf_counter()
    data = build_dataset_overview("stress-large")
    elapsed = time.perf_counter() - start

    payload_bytes = len(json.dumps(data).encode("utf-8"))
    assert payload_bytes < STRESS_PAYLOAD_BUDGET_BYTES, (
        f"stress-large overview is {payload_bytes} bytes; aggregate harder rather "
        f"than raising the {STRESS_PAYLOAD_BUDGET_BYTES}-byte budget"
    )
    assert elapsed < STRESS_LATENCY_BUDGET_SECONDS, (
        f"stress-large overview took {elapsed:.3f}s warm, budget is "
        f"{STRESS_LATENCY_BUDGET_SECONDS}s"
    )


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_no_section_exceeds_the_row_cap(scenario: str):
    """Aggregate, never dump: no list in the payload may exceed MAX_SECTION_ROWS."""
    if not _generated(scenario):
        pytest.skip(f"{scenario} not generated")
    data = build_dataset_overview(scenario)

    oversized: list[str] = []

    def walk(node, path: str):
        if isinstance(node, list):
            if len(node) > overview_module.MAX_SECTION_ROWS:
                oversized.append(f"{path} ({len(node)} rows)")
            for index, item in enumerate(node):
                walk(item, f"{path}[{index}]")
        elif isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}")

    walk(data, "dataset_overview")
    assert not oversized, f"sections over the row cap: {oversized}"


@requires_baseline
def test_truncated_sections_declare_what_was_withheld():
    """Any truncated list must say so, with a real total."""
    data = build_dataset_overview("stress-large" if _generated("stress-large") else "baseline")
    for section in data.values():
        if not isinstance(section, dict):
            continue
        for key, value in section.items():
            if not key.endswith("_showing"):
                continue
            assert value["shown"] <= value["total"]
            assert value["truncated"] == (value["shown"] < value["total"])
            assert value["ranked_by"]


# ---------------------------------------------------------------------------
# Anti-fabrication
# ---------------------------------------------------------------------------

# Real topology counts across the four scenarios. None may appear as a literal in
# the module: every one of them has to be computed from the files on disk.
FORBIDDEN_LITERALS = [
    17, 28, 24, 2912, 30, 1560, 32,  # baseline
    42, 156, 144, 44928, 152, 15808, 288,  # stress-large
]


def test_module_contains_no_hardcoded_topology_counts():
    source = Path(overview_module.__file__).read_text(encoding="utf-8")
    # Strip docstrings/comments is unnecessary — no topology count belongs anywhere,
    # including prose, since prose goes stale silently.
    found = [
        literal
        for literal in FORBIDDEN_LITERALS
        if re.search(rf"(?<![\d_.]){literal}(?![\d_.])", source)
    ]
    assert not found, f"hardcoded topology counts in overview.py: {found}"


@requires_baseline
def test_counts_follow_the_data_when_the_data_changes(tmp_path: Path):
    """Behavioural proof the numbers are derived: delete rows, watch them drop."""
    scenario = "baseline"
    src_dir = DEFAULT_DATA_ROOT / scenario
    dst_dir = tmp_path / scenario
    shutil.copytree(src_dir, dst_dir)

    before = build_dataset_overview(scenario, data_root=tmp_path)

    # Drop the last two customer nodes and one lane from the copy.
    nodes_path = dst_dir / "nodes.csv"
    lines = nodes_path.read_text(encoding="utf-8").splitlines()
    nodes_path.write_text("\n".join(lines[:-2]) + "\n", encoding="utf-8")

    lanes_path = dst_dir / "lanes.csv"
    lane_lines = lanes_path.read_text(encoding="utf-8").splitlines()
    lanes_path.write_text("\n".join(lane_lines[:-1]) + "\n", encoding="utf-8")

    after = build_dataset_overview(scenario, data_root=tmp_path)

    assert after["network"]["node_count"] == before["network"]["node_count"] - 2
    assert after["lanes"]["lane_count"] == before["lanes"]["lane_count"] - 1
    glance_before = {tile["key"]: tile["value"] for tile in before["at_a_glance"]}
    glance_after = {tile["key"]: tile["value"] for tile in after["at_a_glance"]}
    assert glance_after["places"] == glance_before["places"] - 2
    assert glance_after["lanes"] == glance_before["lanes"] - 1


# ---------------------------------------------------------------------------
# Scenario diff
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _generated("component-shortage-shock"), reason="shock scenario not generated"
)
def test_shortage_shock_diff_names_the_disrupted_lanes_and_periods():
    """The diff must match what is actually in lane_periods.csv, not the YAML alone."""
    data = build_dataset_overview("component-shortage-shock")
    diff = data["scenario_diff"]
    assert diff["is_baseline"] is False

    lane_changes = [c for c in diff["changes"] if c["kind"] == "lane_disruption"]
    assert lane_changes, "expected a lane disruption in component-shortage-shock"
    for change in lane_changes:
        assert change["where"]["lane_id"]
        assert change["where"]["from_node_id"]
        assert change["where"]["sku_scope"]
        assert change["when"]["from_period"] <= change["when"]["to_period"]
        assert change["magnitude"]["capacity_multiplier"] == 0.0


@requires_baseline
def test_baseline_has_no_scenario_changes():
    diff = build_dataset_overview("baseline")["scenario_diff"]
    assert diff["is_baseline"] is True
    assert diff["changes"] == []
    assert diff["config_changes"] == []


@pytest.mark.skipif(not _generated("demand-surge"), reason="demand-surge not generated")
def test_demand_surge_diff_reports_a_demand_shock_window():
    data = build_dataset_overview("demand-surge")
    shock = data["demand"]["shock_window"]
    assert shock is not None
    assert shock["from_period"] <= shock["to_period"]
    assert all(m > 1.0 for m in shock["multipliers"])
    kinds = {c["kind"] for c in data["scenario_diff"]["changes"]}
    assert "demand_shock" in kinds


# ---------------------------------------------------------------------------
# Errors, whitelisting, traversal
# ---------------------------------------------------------------------------


def test_unknown_scenario_raises_unknown_not_missing():
    with pytest.raises(UnknownScenarioError):
        build_dataset_overview("no-such-scenario-anywhere")


def test_known_but_ungenerated_scenario_raises_not_generated(tmp_path: Path):
    """A configured scenario with no data is a 409, not a 404 and not a 500."""
    with pytest.raises(DatasetNotGeneratedError) as excinfo:
        build_dataset_overview("baseline", data_root=tmp_path)
    assert "make demo-data" in str(excinfo.value)


def test_partially_generated_scenario_raises_not_generated(tmp_path: Path):
    """A directory that exists but is missing tables is a 409, not a 500."""
    (tmp_path / "baseline").mkdir()
    (tmp_path / "baseline" / "nodes.csv").write_text("node_id\n", encoding="utf-8")
    with pytest.raises(DatasetNotGeneratedError) as excinfo:
        build_dataset_overview("baseline", data_root=tmp_path)
    assert "make demo-data" in str(excinfo.value)


@requires_baseline
def test_table_download_is_whitelisted():
    filename, csv_text = read_table_csv("baseline", "nodes")
    assert filename == REQUIRED_TABLES["nodes"]
    assert csv_text.splitlines()[0].startswith("node_id,")

    with pytest.raises(UnknownScenarioError):
        read_table_csv("baseline", "metadata")
    with pytest.raises(UnknownScenarioError):
        read_table_csv("baseline", "passwd")


@pytest.mark.parametrize(
    "hostile",
    ["..", "../..", "../scenarios", "..%2f..", "....", "-", "._-"],
)
def test_no_path_traversal_via_scenario(hostile: str):
    """The API's scenario pattern permits '.' and '-', so '..' must be refused here."""
    with pytest.raises((UnknownScenarioError, DatasetNotGeneratedError)):
        build_dataset_overview(hostile)
    with pytest.raises((UnknownScenarioError, DatasetNotGeneratedError)):
        read_table_csv(hostile, "nodes")


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


def test_overview_endpoint_requires_auth(api_client):
    assert api_client.get("/dataset/overview", params={"scenario": "baseline"}).status_code == 401
    assert api_client.get("/dataset/table", params={"scenario": "baseline", "table": "nodes"}).status_code == 401


@requires_baseline
def test_overview_endpoint_returns_payload(api_client, api_headers):
    response = api_client.get(
        "/dataset/overview", params={"scenario": "baseline"}, headers=api_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["scenario"] == "baseline"
    data = body["data"]["dataset_overview"]
    assert data["provenance"]["is_synthetic"] is True
    assert "not customer data" in data["provenance"]["badge_text"]


def test_overview_endpoint_unknown_scenario_is_404(api_client, api_headers):
    response = api_client.get(
        "/dataset/overview",
        params={"scenario": "definitely-not-a-scenario"},
        headers=api_headers,
    )
    assert response.status_code == 404


def test_table_endpoint_rejects_unknown_table(api_client, api_headers):
    response = api_client.get(
        "/dataset/table",
        params={"scenario": "baseline", "table": "metadata"},
        headers=api_headers,
    )
    assert response.status_code in (404, 422)


@requires_baseline
def test_table_endpoint_downloads_csv(api_client, api_headers):
    response = api_client.get(
        "/dataset/table",
        params={"scenario": "baseline", "table": "lanes"},
        headers=api_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert response.text.splitlines()[0].startswith("lane_id,")


@requires_baseline
def test_pipeline_link_names_only_real_tables():
    link = build_dataset_overview("baseline")["pipeline_link"]
    for stage, tables in link["stage_inputs"].items():
        for table in tables:
            assert table in REQUIRED_TABLES, f"{stage} names unknown table {table}"
    assert set(link["stage_inputs"]["ingest"]) == set(REQUIRED_TABLES)
