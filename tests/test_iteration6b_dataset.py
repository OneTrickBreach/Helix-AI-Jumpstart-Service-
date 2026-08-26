"""Iteration 6b Phase 2 — a network-edited config saves, runs, reopens and deletes.

The point of this phase is **reuse**: a custom dataset is still just a config, so
`store.py`, the run path, the dataset view and the change list should all carry it
with no modification. That is a claim, so it is tested rather than asserted.

The other half is guardrail 4. A resized network returns a LOWER objective for a
SMALLER problem, and every surface that shows that number has to say so.
"""

from __future__ import annotations

import pytest

from src.scenario.preview import build_preview, estimate_run, series_count, topology_size
from src.scenario.run_card import build_run_card, comparability_warnings
from src.scenario.synthesize import CANONICAL_SCENARIOS, complete_config, load_base_config
from src.scenario.validate import network_comparability, validate_custom_scenario

# ---------------------------------------------------------------------------
# synthesis: a network key becomes a complete, generatable config
# ---------------------------------------------------------------------------


def test_a_network_key_flows_through_synthesis_into_a_complete_config():
    config = complete_config("custom-onedc", overrides={"network.distribution_centers": 1})
    assert config["network"]["distribution_centers"] == 1
    # Everything else is baseline, untouched — that is what makes the change list short.
    base = load_base_config()
    for key, value in base["network"].items():
        if key != "distribution_centers":
            assert config["network"][key] == value, key


def test_the_change_list_reports_a_network_edit_in_the_dataset_views_own_shape():
    """§1.6: the dataset view's "what makes this different" panel renders this as-is."""
    changes = build_preview(
        "onedc", overrides={"network.distribution_centers": 1}
    )["config_changes"]
    assert len(changes) == 1
    assert changes[0]["group"] == "network"
    assert changes[0]["parameter"] == "distribution_centers"
    assert changes[0]["baseline_value"] == 2
    assert changes[0]["scenario_value"] == 1


@pytest.mark.parametrize("name", CANONICAL_SCENARIOS)
def test_the_four_recorded_names_are_still_refused(name):
    """Guardrail 3 survives the new tier: a network edit cannot overwrite a benchmark."""
    result = validate_custom_scenario(
        name, complete_config(f"custom-{name}"), overrides={"network.plants": 3}
    )
    assert not result.ok
    assert "name_reserved" in [item.code for item in result.refusals]


# ---------------------------------------------------------------------------
# 🔴 guardrail 4: comparability, on every surface that shows the number
# ---------------------------------------------------------------------------


def test_a_node_count_edit_stays_comparable():
    verdict = network_comparability(
        complete_config("c", overrides={"network.distribution_centers": 1})
    )
    assert verdict["comparable_to_baseline"] is True
    assert verdict["resized_settings"] == []
    assert comparability_warnings(
        complete_config("c", overrides={"network.distribution_centers": 1})
    ) == []


def test_a_resized_network_is_not_comparable_and_says_which_setting_resized_it():
    config = complete_config("c", overrides={"network.customers": 7})
    verdict = network_comparability(config)
    assert verdict["comparable_to_baseline"] is False
    assert [item["key"] for item in verdict["resized_settings"]] == ["network.customers"]
    assert verdict["resized_settings"][0]["baseline_value"] == 8
    assert verdict["resized_settings"][0]["scenario_value"] == 7
    assert "different quantity" in verdict["why"]
    assert "81,789.36" in verdict["note"]


def test_the_not_comparable_warning_reaches_the_planner_before_any_compute():
    result = validate_custom_scenario(
        "resized", complete_config("c", overrides={"network.customers": 7}),
        overrides={"network.customers": 7},
    )
    assert result.ok, "a resized network is legitimate work, not a refusal"
    warning = next(
        item for item in result.warnings if item.code == "resized_network_not_comparable"
    )
    assert "81,789.36" in warning.message
    assert warning.detail["comparable_to_baseline"] is False


def test_the_same_warning_is_built_by_one_function_for_before_and_after_the_run():
    """The Iteration 5 lesson: one measured fact must not grow two vocabularies."""
    config = complete_config("c", overrides={"network.finished_goods": 3})
    card = build_run_card("baseline", include_ppo=False, include_rationale=False)
    assert card["network_comparability"]["comparable_to_baseline"] is True

    after = comparability_warnings(config)
    assert len(after) == 1
    assert after[0]["code"] == "resized_network_not_comparable"
    # The post-run wording names the specific misreading it prevents...
    assert "lower objective" in after[0]["do_not_read_as"]
    assert "less demand" in after[0]["do_not_read_as"]
    # ...and must NOT repeat the remedy the message already carries, or the amber
    # box shows the same sentence twice. Caught by looking at the rendered screen.
    assert "naive-vs-classical" in after[0]["message"]
    assert "naive-vs-classical" not in after[0]["do_not_read_as"]


def test_every_problem_size_count_triggers_it_and_no_node_count_does():
    for key, value in (
        ("network.customers", 7), ("network.finished_goods", 3),
        ("network.subassemblies_per_finished_good", 3),
        ("network.raw_components_per_subassembly", 3),
    ):
        config = complete_config("c", overrides={key: value})
        assert not network_comparability(config)["comparable_to_baseline"], key
    for key, value in (
        ("network.suppliers", 6), ("network.plants", 3), ("network.distribution_centers", 1),
    ):
        config = complete_config("c", overrides={key: value})
        assert network_comparability(config)["comparable_to_baseline"], key


# ---------------------------------------------------------------------------
# 🔴 the estimate is recomputed, not inherited
# ---------------------------------------------------------------------------


def test_the_forecast_estimate_is_counted_from_this_network_not_baselines():
    """A 40-customer dataset is a multi-second run, and the estimate has to say so."""
    small = complete_config("c")
    big = complete_config("c", overrides={"network.customers": 40})
    assert series_count(small) == 32
    assert series_count(big) == 160

    def forecast_of(config):
        estimate = estimate_run("custom-unrun", config)
        return next(c for c in estimate["components"] if c["stage"] == "forecast")

    small_fc, big_fc = forecast_of(small), forecast_of(big)
    assert big_fc["seconds"] > small_fc["seconds"] * 4, "the estimate ignored the resize"
    assert big_fc["seconds"] == 4.0  # 160 series x 25 ms
    # And it says where the number came from, naming this network's own counts.
    assert "40 customers x 4 finished goods" in big_fc["basis"]
    assert "THIS network" in big_fc["basis"]


def test_a_borrowed_optimize_latency_admits_it_describes_another_topology():
    """🔴 The specific dishonesty the plan warned about.

    A scenario with no run on record borrows baseline's optimizer latency. That is
    the right thing to do — inventing a figure would be worse — but presenting it
    as if it described a 49-node network would not be.
    """
    big = complete_config("c", overrides={"network.customers": 40})
    optimize = next(
        c for c in estimate_run("custom-never-run", big)["components"]
        if c["stage"] == "optimize"
    )
    assert "no run on record" in optimize["basis"]
    assert "different shape" in optimize["basis"]
    assert "17 nodes / 30 lanes" in optimize["basis"], "baseline's real shape"
    assert "49 / 94" in optimize["basis"], "this network's real shape"
    assert "floor rather than an estimate" in optimize["basis"]


def test_an_unresized_custom_scenario_gets_no_spurious_topology_caveat():
    """Don't cry wolf: same shape as baseline means the borrowed latency is fine."""
    same = complete_config("c", overrides={"demand.base_units_per_customer_period": 52})
    optimize = next(
        c for c in estimate_run("custom-never-run", same)["components"]
        if c["stage"] == "optimize"
    )
    assert "no run on record" in optimize["basis"]
    assert "different shape" not in optimize["basis"]


def test_topology_size_matches_what_the_generator_really_builds():
    """The estimate's size proxy is only useful if it is true.

    Checked against real in-memory builds rather than against itself.
    """
    from src.scenario.tables import build_tables

    for overrides, expected_nodes, expected_lanes in (
        ({}, 17, 30),
        ({"network.customers": 40}, 49, 94),
        ({"network.distribution_centers": 1}, 16, 20),
    ):
        config = complete_config("c", overrides=overrides)
        proxy = topology_size(config)
        tables = build_tables(config, 12345)
        assert proxy["nodes"] == len(tables["nodes"]) == expected_nodes, overrides
        assert proxy["lanes"] == len(tables["lanes"]) == expected_lanes, overrides


# ---------------------------------------------------------------------------
# Ryan asked for two things; a config has to say which one it is
# ---------------------------------------------------------------------------


def test_a_network_edited_config_describes_itself_as_a_dataset():
    """The results screen shows this description directly above the banner.

    A network-edited config calling itself "a custom scenario" contradicts the
    CUSTOM DATASET banner two lines below it — which is exactly how it read the
    first time it was built.
    """
    dataset = complete_config("custom-d", overrides={"network.distribution_centers": 1})
    assert dataset["description"] == "Custom dataset built from baseline on this device."

    conditions = complete_config(
        "custom-s", overrides={"demand.base_units_per_customer_period": 52}
    )
    assert conditions["description"] == "Custom scenario built from baseline on this device."

    # An unedited config is a scenario, not a dataset.
    assert complete_config("custom-plain")["description"].startswith("Custom scenario")


def test_an_explicit_description_still_wins():
    config = complete_config(
        "custom-d", overrides={"network.plants": 3}, description="Two-plant network"
    )
    assert config["description"] == "Two-plant network"


def test_network_edited_is_reported_for_every_count_including_the_inert_one():
    """`network_edited` asks "is this a dataset?", not "does it change the answer?".

    `lines_per_plant` cannot move the objective, but changing it still means the
    planner edited the network — so the payload must say so, or the banner would
    call it a scenario while the network block differs from baseline.
    """
    for key, value in (
        ("network.suppliers", 6), ("network.plants", 3),
        ("network.distribution_centers", 1), ("network.customers", 7),
        ("network.finished_goods", 3), ("network.subassemblies_per_finished_good", 3),
        ("network.raw_components_per_subassembly", 3), ("network.lines_per_plant", 5),
    ):
        verdict = network_comparability(complete_config("c", overrides={key: value}))
        assert verdict["network_edited"] is True, key
        assert [item["key"] for item in verdict["edited_settings"]] == [key], key

    assert network_comparability(complete_config("c"))["network_edited"] is False
