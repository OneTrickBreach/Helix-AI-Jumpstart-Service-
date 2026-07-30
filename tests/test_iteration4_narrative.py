"""Iteration 4, Phase 2 — plain-English narrative layer.

Two classes of test here. The unit tests pin the grammar edge cases that make prose
look machine-generated ("1 suppliers", "2 lanes each stops"). The integration tests
run against the real generated scenarios and assert the harder property: that the
sentences tell the truth about the data, and that no schema name leaks into prose.
"""

from __future__ import annotations

import re

import pytest

from src.dataset.narrative import (
    build_narrative,
    change_sentence,
    forecast_method_sentence,
    humanize,
    one_sentence_summary,
    plural,
    scenario_sentence,
)
from src.dataset.overview import build_dataset_overview
from src.ingest.state import DEFAULT_DATA_ROOT


ALL_SCENARIOS = ["baseline", "component-shortage-shock", "demand-surge", "stress-large"]


def _generated(scenario: str) -> bool:
    return (DEFAULT_DATA_ROOT / scenario).is_dir()


# ---------------------------------------------------------------------------
# Grammar edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "count,singular,plural_form,expected",
    [
        (1, "supplier", None, "1 supplier"),
        (0, "supplier", None, "0 suppliers"),
        (5, "supplier", None, "5 suppliers"),
        (1, "factory", "factories", "1 factory"),
        (2, "factory", "factories", "2 factories"),
        (15808, "lane", None, "15,808 lanes"),
        (1, "demand series", "demand series", "1 demand series"),
        (32, "demand series", "demand series", "32 demand series"),
    ],
)
def test_plural_handles_singular_plural_and_separators(
    count: int, singular: str, plural_form: str | None, expected: str
):
    assert plural(count, singular, plural_form) == expected


def test_one_sentence_summary_reads_correctly_for_a_single_of_everything():
    """The 1-of-each case is where naive templates produce '1 suppliers'."""
    sentence = one_sentence_summary(
        network={"nodes_by_type": {"supplier": 1, "plant": 1, "distribution_center": 1, "customer": 1}},
        products={"sku_count": 1},
        demand={"period_unit": "week", "history_periods": 1},
        capacity={"production_line_count": 1},
    )
    assert "1 supplier " in sentence
    assert "1 factory" in sentence
    assert "1 production line," in sentence
    assert "which sends" in sentence  # singular plant takes a singular verb
    assert "1 distribution center" in sentence
    assert "1 customer" in sentence
    assert "1 product" in sentence
    assert "1 week of demand history" in sentence
    assert "suppliers" not in sentence and "factories" not in sentence


def test_one_sentence_summary_omits_tiers_that_do_not_exist():
    sentence = one_sentence_summary(
        network={"nodes_by_type": {"supplier": 3, "customer": 4}},
        products={"sku_count": 9},
        demand={"period_unit": "week", "history_periods": 10},
        capacity={"production_line_count": 0},
    )
    assert "distribution center" not in sentence
    assert "factory" not in sentence and "factories" not in sentence
    assert "3 suppliers" in sentence and "4 customers" in sentence


def test_one_sentence_summary_survives_an_empty_network():
    sentence = one_sentence_summary(
        network={"nodes_by_type": {}},
        products={"sku_count": 0},
        demand={"period_unit": "week", "history_periods": 0},
        capacity={"production_line_count": 0},
    )
    assert sentence == "This dataset contains no network locations."


def test_multiple_identical_lane_disruptions_collapse_to_one_sentence():
    """Four identically-disrupted lanes must read as one fact, not four."""
    changes = [
        {
            "kind": "lane_disruption",
            "what": "stress_combined_inbound_disruption",
            "where": {
                "lane_id": f"LANE-000{index}",
                "from_node_id": "SUP-001",
                "to_node_id": f"PLANT-00{index}",
                "sku_scope": f"RC-00{index}",
                "lane_type": "inbound_raw",
            },
            "when": {"from_period": 38, "to_period": 53, "periods_affected": 16},
            "magnitude": {"capacity_multiplier": 0.15, "lead_time_multiplier": 2.4},
        }
        for index in (1, 2, 3, 4)
    ]
    sentence = scenario_sentence(
        {"is_baseline": False, "comparable": True, "changes": changes, "config_changes": []},
        {"period_unit": "week"},
    )
    assert sentence.count("From week 38") == 1
    assert "4 inbound lanes" in sentence
    # Plural subject takes a plural verb.
    assert "fall to 15%" in sentence
    assert "falls to 15%" not in sentence
    assert "their lead times stretch to 2.4x" in sentence


def test_single_lane_disruption_uses_singular_verbs():
    change = {
        "kind": "lane_disruption",
        "what": "zero_supply_component_shortage",
        "where": {
            "lane_id": "LANE-0001",
            "from_node_id": "SUP-001",
            "to_node_id": "PLANT-001",
            "sku_scope": "RC-001",
            "lane_type": "inbound_raw",
        },
        "when": {"from_period": 18, "to_period": 27, "periods_affected": 10},
        "magnitude": {"capacity_multiplier": 0.0, "lead_time_multiplier": 3.0},
    }
    sentence = change_sentence(change, "week")
    assert "stops completely" in sentence
    assert "its lead time stretches to 3x normal" in sentence
    assert "for 10 weeks" in sentence


def test_scenario_sentence_never_claims_nothing_else_changed():
    """The plan's example says 'Nothing else changes'. On this data that is false."""
    sentence = scenario_sentence(
        {
            "is_baseline": False,
            "comparable": True,
            "changes": [],
            "config_changes": [
                {"group": "costs", "parameter": "holding_cost"},
                {"group": "capacity", "parameter": "capacity_tightness"},
            ],
        },
        {"period_unit": "week"},
    )
    assert "nothing else" not in sentence.lower()
    assert "2 other settings differ" in sentence
    assert "costs" in sentence and "capacity" in sentence


def test_scenario_sentence_uses_singular_verb_for_one_config_change():
    sentence = scenario_sentence(
        {
            "is_baseline": False,
            "comparable": True,
            "changes": [],
            "config_changes": [{"group": "costs", "parameter": "holding_cost"}],
        },
        {"period_unit": "week"},
    )
    assert "1 other setting differs" in sentence


def test_scenario_sentence_explains_an_ungeneratable_baseline():
    sentence = scenario_sentence(
        {"is_baseline": False, "comparable": False, "changes": [], "config_changes": []},
        {"period_unit": "week"},
    )
    assert "baseline dataset has not been generated" in sentence


def test_forecast_sentence_states_the_measured_fact_when_nothing_is_intermittent():
    sentence = forecast_method_sentence(
        {"series_count": 32, "lumpy_series_count": 0, "lumpy_zero_fraction_threshold": 0.35}
    )
    assert "All 32 demand series" in sentence
    assert "seriess" not in sentence
    assert "AutoETS" in sentence
    assert "this dataset has none" in sentence


def test_forecast_sentence_reports_a_real_split_when_one_exists():
    sentence = forecast_method_sentence(
        {"series_count": 40, "lumpy_series_count": 12, "lumpy_zero_fraction_threshold": 0.35}
    )
    assert "12 of 40" in sentence
    assert "Croston-SBA" in sentence
    assert "The other 28 use AutoETS" in sentence


def test_humanize_turns_schema_names_into_words():
    assert humanize("lane_disruption") == "lane disruption"
    assert humanize("skus", {"skus": "product costs"}) == "product costs"


# ---------------------------------------------------------------------------
# Against the real generated data
# ---------------------------------------------------------------------------

NARRATIVE_KEYS = [
    "one_sentence_summary",
    "scenario_sentence",
    "forecast_method_sentence",
    "pipeline_sentence",
    "provenance_sentence",
]


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_narrative_is_present_and_well_formed(scenario: str):
    if not _generated(scenario):
        pytest.skip(f"{scenario} not generated")
    narrative = build_dataset_overview(scenario)["narrative"]
    for key in NARRATIVE_KEYS:
        text = narrative[key]
        assert text and text[0].isupper(), f"{key} should start with a capital"
        assert text.rstrip().endswith("."), f"{key} should end with a full stop"


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_no_schema_names_leak_into_prose(scenario: str):
    """snake_case on screen is the tell that a machine wrote it."""
    if not _generated(scenario):
        pytest.skip(f"{scenario} not generated")
    overview = build_dataset_overview(scenario)
    texts = list(overview["narrative"].values()) + [
        change["plain_english"] for change in overview["scenario_diff"]["changes"]
    ]
    for text in texts:
        leaked = re.findall(r"\b[a-z]+_[a-z_]+\b", text)
        assert not leaked, f"schema names leaked into prose: {leaked} in {text!r}"


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_summary_matches_the_actual_counts(scenario: str):
    """The sentence must agree with the numbers in the same payload."""
    if not _generated(scenario):
        pytest.skip(f"{scenario} not generated")
    overview = build_dataset_overview(scenario)
    sentence = overview["narrative"]["one_sentence_summary"]
    by_type = overview["network"]["nodes_by_type"]

    assert f"{by_type['supplier']:,} suppliers" in sentence
    assert f"{by_type['customer']:,} customers" in sentence
    assert f"{overview['products']['sku_count']:,} products" in sentence
    assert (
        f"{overview['capacity']['production_line_count']:,} production lines" in sentence
    )
    assert f"{overview['demand']['history_periods']:,} weeks" in sentence


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_every_structured_change_carries_plain_english(scenario: str):
    if not _generated(scenario):
        pytest.skip(f"{scenario} not generated")
    for change in build_dataset_overview(scenario)["scenario_diff"]["changes"]:
        assert change["plain_english"].endswith(".")
        # The period range in prose must match the structured record.
        assert str(change["when"]["from_period"]) in change["plain_english"]


@pytest.mark.skipif(
    not _generated("component-shortage-shock"), reason="shock scenario not generated"
)
def test_shortage_scenario_sentence_names_the_real_disruption():
    overview = build_dataset_overview("component-shortage-shock")
    sentence = overview["narrative"]["scenario_sentence"]
    timeline = overview["lanes"]["disruption_timeline"]
    assert f"From week {timeline[0]['from_period']}" in sentence
    assert "stop completely" in sentence or "stops completely" in sentence
    assert "other settings differ" in sentence  # honest about the rest


@pytest.mark.skipif(not _generated("baseline"), reason="baseline not generated")
def test_baseline_narrative_says_it_is_the_normal_case():
    sentence = build_dataset_overview("baseline")["narrative"]["scenario_sentence"]
    assert "normal operating scenario" in sentence
    assert "no disruption" in sentence


@pytest.mark.skipif(not _generated("baseline"), reason="baseline not generated")
def test_narrative_does_not_break_determinism():
    first = build_dataset_overview("baseline")["narrative"]
    second = build_dataset_overview("baseline")["narrative"]
    assert first == second
