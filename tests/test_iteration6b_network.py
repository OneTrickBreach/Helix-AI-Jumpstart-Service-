"""Iteration 6b Phase 1 — the network tier: floors, ceilings and honest labels.

Guardrail 1 of 6b is *nothing may crash*. Five ``network:`` values raise uncaught
exceptions today and one of them does it **two stages after** a full dataset has
been written. Guardrails 3 and 4 are about honesty: seven of the eight counts move
the objective, but they move it for two very different reasons and only one of
those is comparable to the recorded baseline.

This module is where both claims are enforced. Nothing here writes to disk and
nothing here runs the optimizer except the one derivation that has to.
"""

from __future__ import annotations

import pytest

from src.scenario.api import custom_settings_payload
from src.scenario.ledger import (
    ANSWER_CLASS_LABELS,
    INERT,
    NETWORK_KEYS,
    NETWORK_SHAPE,
    PROBLEM_SIZE,
    SETTINGS_BY_KEY,
    UNCONDITIONAL,
    derive_setting_targets,
)
from src.scenario.synthesize import complete_config, is_network_key
from src.scenario.tables import PIPELINE_TABLES, build_tables
from src.scenario.validate import (
    NETWORK_FLOOR_REFUSALS,
    REFUSAL_CODES,
    validate_overrides,
)

#: §1.3, measured 2026-08-21 by trying them. Four die in the generator; the fifth
#: passes generation, writes a complete dataset, and dies in the FORECAST.
CRASHES_THE_GENERATOR = (
    "network.plants",
    "network.finished_goods",
    "network.subassemblies_per_finished_good",
    "network.raw_components_per_subassembly",
)
CRASHES_THE_FORECAST = "network.customers"

#: §1.3, decision 4. These do not crash, which is what makes them worse.
CONFIDENTLY_WRONG_AT_ZERO = ("network.distribution_centers", "network.suppliers")


# ---------------------------------------------------------------------------
# guardrail 1: nothing may crash — and the floors are refused BEFORE the write
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", CRASHES_THE_GENERATOR + (CRASHES_THE_FORECAST,)
                         + CONFIDENTLY_WRONG_AT_ZERO)
def test_zero_is_refused_for_every_value_that_cannot_be_run(key):
    """All seven, refused with a sentence a planner can act on."""
    result = validate_overrides({key: 0})
    assert not result.ok, f"{key}=0 was accepted"
    assert len(result.refusals) == 1
    refusal = result.refusals[0]
    assert refusal.field == key
    assert refusal.code in REFUSAL_CODES
    # "a sentence a planner can act on" — not a bare bounds message.
    assert len(refusal.message) > 60, refusal.message
    assert refusal.message.rstrip().endswith("."), "refusals are sentences"


@pytest.mark.parametrize("key", CRASHES_THE_GENERATOR)
def test_the_generator_really_does_crash_at_the_refused_value(key):
    """The floors are not defensive decoration — this is what they prevent.

    Built in memory, so it proves the generator's own arithmetic fails without
    writing anything. If a future generator change makes one of these survivable,
    this test fails and the refusal wording should be revisited rather than left
    claiming a crash that no longer happens.
    """
    config = complete_config("custom-floor-probe")
    config["network"][key.split(".", 1)[1]] = 0
    with pytest.raises(ZeroDivisionError):
        build_tables(config, 12345)


def test_zero_customers_survives_generation_which_is_why_the_floor_is_early():
    """🔴 The case that proves floors belong *before* the write, not after.

    ``customers = 0`` does not crash the generator. It produces a complete,
    writable dataset and then fails two stages later in the forecast, on
    ``sum operation not supported for dtype str`` over an empty demand frame. A
    floor applied at generation time would have let a broken dataset onto disk.
    """
    config = complete_config("custom-floor-probe")
    config["network"]["customers"] = 0
    tables = build_tables(config, 12345)  # no exception
    assert tables["demand"] == [], "no customers means no demand rows"
    # ...and the refusal is what stops it, not the generator.
    assert not validate_overrides({"network.customers": 0}).ok


@pytest.mark.parametrize("key", CONFIDENTLY_WRONG_AT_ZERO)
def test_the_confidently_wrong_values_quote_their_measured_numbers(key):
    """Decision 4: refuse, and say *why* with the measured figures.

    A crash is embarrassing; a confident wrong answer is worse. These two produce
    a cheaper, better-scoring plan for a network that cannot physically operate,
    so the refusal has to teach the modelling limit rather than just block.
    """
    refusal = validate_overrides({key: 0}).refusals[0]
    assert refusal.code == NETWORK_FLOOR_REFUSALS[key][0]
    assert refusal.code in ("network_zero_distribution_centers", "network_zero_suppliers")
    # The measured number is in the sentence, so the reason is checkable.
    assert "83.66%" in refusal.message or "92.01%" in refusal.message
    assert any(token in refusal.message for token in ("68,565.25", "77,390.94"))


def test_the_zero_dc_refusal_names_the_model_limit_not_the_network():
    """The wording matters: this is a limit of the model, not a fact about a network."""
    message = validate_overrides({"network.distribution_centers": 0}).refusals[0].message
    assert "limit of the model" in message
    assert "per-node capacity" in message


# ---------------------------------------------------------------------------
# decision 6: sanity ceilings, honest about being sanity ceilings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", NETWORK_KEYS)
def test_a_fat_fingered_count_is_capped(key):
    result = validate_overrides({key: 10_000})
    assert not result.ok
    assert result.refusals[0].code == "network_count_above_ceiling"


def test_the_ceiling_says_it_is_a_typo_guard_and_not_a_capability_limit():
    """§1.4: the upper end was probed and is sane. The cap must not imply otherwise."""
    message = validate_overrides({"network.customers": 10_000}).refusals[0].message
    assert "typo" in message
    assert "40 customers" in message, "the measured headroom is the honest justification"


@pytest.mark.parametrize("key", NETWORK_KEYS)
def test_the_shipped_baseline_value_is_inside_the_bounds(key):
    """A bound that refuses baseline itself would be a bug, not a guardrail."""
    baseline = complete_config("custom-bounds-probe")["network"][key.split(".", 1)[1]]
    setting = SETTINGS_BY_KEY[key]
    assert setting.minimum <= baseline <= setting.maximum, f"{key}={baseline} is out of bounds"
    assert validate_overrides({key: baseline}).ok


# ---------------------------------------------------------------------------
# the network block is a validated path now, not a refusal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", NETWORK_KEYS)
def test_every_network_count_is_accepted_at_a_sensible_value(key):
    """6a refused all of these outright. That is the refusal 6b replaces."""
    assert is_network_key(key)
    assert key in SETTINGS_BY_KEY
    assert validate_overrides({key: 2}).ok


def test_out_of_scope_is_gone_as_a_refusal_code():
    """The 6a code is retired, not left dangling in the enumeration."""
    assert "network_setting_out_of_scope" not in REFUSAL_CODES


def test_a_misspelt_network_key_gets_a_useful_sentence():
    """'there are 67 settings' does not help someone who typed network.warehouses."""
    result = validate_overrides({"network.warehouses": 2})
    assert not result.ok
    refusal = result.refusals[0]
    assert refusal.code == "unknown_network_setting"
    assert "distribution_centers" in refusal.message, "list the real ones"


def test_all_refusals_still_reported_together_with_network_ones_mixed_in():
    result = validate_overrides({
        "network.distribution_centers": 0,
        "network.customers": 10_000,
        "network.warehouses": 1,
        "capacity.capacity_tightness": 99.0,
    })
    assert {item.code for item in result.refusals} == {
        "network_zero_distribution_centers",
        "network_count_above_ceiling",
        "unknown_network_setting",
        "above_maximum",
    }


# ---------------------------------------------------------------------------
# 🔴 guardrails 3 and 4: the two honesty classes
# ---------------------------------------------------------------------------


def test_the_two_honesty_classes_are_assigned_exactly_as_measured():
    """§1.2. Node counts and problem-size counts are not one population.

    Node counts move the objective 0.12%-0.64% with **no** service change; the
    problem-size counts move it 1.3%-31.3% by changing total demand or BOM depth.
    Both are honest and neither is an improvement — but only the first may be
    compared to 81,789.36, and the split has to be explicit somewhere a test can
    read it.
    """
    by_class: dict[str, set[str]] = {NETWORK_SHAPE: set(), PROBLEM_SIZE: set()}
    for key in NETWORK_KEYS:
        answer_class = SETTINGS_BY_KEY[key].answer_class
        if answer_class:
            by_class[answer_class].add(key)

    assert by_class[NETWORK_SHAPE] == {
        "network.suppliers", "network.plants", "network.distribution_centers",
    }
    assert by_class[PROBLEM_SIZE] == {
        "network.customers", "network.finished_goods",
        "network.subassemblies_per_finished_good", "network.raw_components_per_subassembly",
    }
    # The inert one carries no class: it uses 6a's existing heading instead.
    assert SETTINGS_BY_KEY["network.lines_per_plant"].answer_class == ""


def test_a_resized_problem_is_never_marked_comparable_to_the_baseline():
    """Guardrail 4. A 25% objective drop from a product-count change is not a 25% win."""
    for key in NETWORK_KEYS:
        setting = SETTINGS_BY_KEY[key]
        payload = setting.as_dict()
        if setting.answer_class == PROBLEM_SIZE:
            assert payload["comparable_to_baseline"] is False, key
        elif setting.answer_class == NETWORK_SHAPE:
            assert payload["comparable_to_baseline"] is True, key


def test_the_network_shape_label_refuses_to_call_itself_a_resilience_test():
    """The single most dangerous misreading available on this panel."""
    label = ANSWER_CLASS_LABELS[NETWORK_SHAPE]
    assert "NOT a resilience test" in label
    assert "per-node capacity" in label


def test_the_problem_size_label_says_compare_within_the_run():
    label = ANSWER_CLASS_LABELS[PROBLEM_SIZE]
    assert "never against the recorded baseline" in label
    assert "naive-vs-classical" in label


# ---------------------------------------------------------------------------
# the payload carries the classes, so the UI cannot invent them
# ---------------------------------------------------------------------------


def test_the_payload_describes_the_network_tier():
    payload = custom_settings_payload()
    tier = payload["network_tier"]
    assert tier["group"] == "network"
    assert set(tier["keys"]) == set(NETWORK_KEYS)
    assert set(tier["classes"]) == {NETWORK_SHAPE, PROBLEM_SIZE}
    assert tier["answer_class_labels"] == ANSWER_CLASS_LABELS
    # Every problem-size count is flagged, and the note names the number nobody
    # may compare a resized run against.
    assert set(tier["not_comparable_keys"]) == {
        "network.customers", "network.finished_goods",
        "network.subassemblies_per_finished_good", "network.raw_components_per_subassembly",
    }
    assert "81,789.36" in tier["not_comparable_note"]
    assert "positional" in tier["reason"], "reducing a count deletes the LAST entity (§1.5)"
    assert "excluded_from_6a" not in payload, "6a's exclusion block is now a real tier"


def test_the_payload_lists_the_network_group_and_the_eight_settings():
    payload = custom_settings_payload()
    assert "network" in payload["groups"]
    network = [item for item in payload["settings"] if item["group"] == "network"]
    assert len(network) == 8
    assert payload["ledger"]["total"] == 67
    # Guardrail: lines_per_plant must be in the cannot-change block, with the other 15.
    assert "network.lines_per_plant" in payload["cannot_change_the_answer"]["settings"]
    assert payload["cannot_change_the_answer"]["count"] == 16


def test_the_inert_network_count_is_not_offered_as_a_live_control():
    setting = SETTINGS_BY_KEY["network.lines_per_plant"]
    assert setting.reach == INERT
    assert setting.reaches_optimizer is False
    assert "does nothing" in setting.note
    assert "identical to the digit" in setting.note


# ---------------------------------------------------------------------------
# 🔴 derived, not declared
# ---------------------------------------------------------------------------


def test_lines_per_plant_is_derived_inert_not_asserted_inert():
    """The most manufacturing-sounding control on the panel, and it does nothing.

    Not taken on trust: this builds the tables twice and diffs, exactly as the 6a
    ledger does. ``lines_per_plant`` changes only ``production_lines`` rows plus two
    ``nodes`` columns — and none of those three tables is read by the forecast or
    the optimizer, so INERT falls out of the derivation on its own. **No second
    classifier was written for the network tier** (§1.6).

    If a generator change ever makes ``production_lines.csv`` load-bearing, this
    fails and the label stops being a lie the moment it stops being true.
    """
    config = complete_config("custom-lpp-probe")
    targets = derive_setting_targets(config, keys=("network.lines_per_plant",))
    written = targets["network.lines_per_plant"]

    assert written, "a setting that writes nothing would be LABEL_ONLY, not INERT"
    touched_tables = {table for table, _ in written}
    assert touched_tables == {"production_lines", "nodes"}
    assert not touched_tables & set(PIPELINE_TABLES), (
        f"lines_per_plant now touches a table the pipeline reads: {touched_tables}"
    )
    assert SETTINGS_BY_KEY["network.lines_per_plant"].reach == INERT


def test_the_seven_live_counts_change_a_table_the_pipeline_reads():
    """The other side of the same coin — these are not no-op controls.

    Each acts by changing ROW COUNTS in a table the pipeline reads, which is why
    6a's ``__rows__`` pseudo-column was the mechanism 6b needed and no new
    machinery was built.
    """
    live = tuple(key for key in NETWORK_KEYS if key != "network.lines_per_plant")
    targets = derive_setting_targets(complete_config("custom-live-probe"), keys=live)
    for key in live:
        read_rows = {
            table for table, column in targets[key]
            if column == "__rows__" and table in PIPELINE_TABLES
        }
        assert read_rows, f"{key} declares UNCONDITIONAL but changes no table the pipeline reads"
        assert SETTINGS_BY_KEY[key].reach == UNCONDITIONAL


# ---------------------------------------------------------------------------
# 🔴 the honesty classes, DERIVED rather than asserted
# ---------------------------------------------------------------------------


def _demand_totals(key: str, value: int) -> tuple[int, int, int]:
    """``(finished-good demand, total demand, demand rows)`` for one network value."""
    config = complete_config("custom-class-probe")
    config["network"][key.split(".", 1)[1]] = value
    demand = build_tables(config, 12345)["demand"]
    finished = sum(
        int(row["quantity_units"])
        for row in demand
        if row["demand_type"] == "finished_good_customer"
    )
    return finished, sum(int(row["quantity_units"]) for row in demand), len(demand)


def test_the_two_classes_are_separated_by_a_measurable_property_not_an_opinion():
    """🔴 What actually distinguishes the two honesty classes, measured.

    §1.2's split is not a stylistic choice, and this is what makes it checkable:

    * a **network-shape** count leaves **total demand bit-identical** — it moves the
      objective only by re-allocating lane capacity and re-drawing lane costs, which
      is why the move is under 1% and service never changes;
    * a **problem-size** count **changes total demand**, so the objective it produces
      is a different quantity and comparing it to 81,789.36 is meaningless.

    If someone later puts a count in the wrong class, this fails. That is the point:
    guardrail 4 is only as good as the classification behind it.
    """
    baseline_finished, baseline_total, baseline_rows = _demand_totals(
        "network.distribution_centers", 2
    )
    assert baseline_total > 0 and baseline_finished > 0, "the probe read nothing"

    for key in NETWORK_KEYS:
        setting = SETTINGS_BY_KEY[key]
        if not setting.answer_class:
            continue
        # A value that is in range for every count, and different from baseline's.
        finished, total, rows = _demand_totals(key, 3)

        if setting.answer_class == NETWORK_SHAPE:
            assert total == baseline_total, (
                f"{key} is labelled 'changes the shape of the network' but it moved total "
                f"demand {baseline_total} -> {total}. It resizes the problem, so it belongs "
                f"in the {PROBLEM_SIZE} class and its result is not comparable to baseline."
            )
            assert rows == baseline_rows, f"{key} changed the number of demand rows"
        else:
            assert total != baseline_total, (
                f"{key} is labelled 'changes the SIZE of the problem' but total demand did "
                f"not move. If it cannot resize the problem, the not-comparable caveat on "
                f"it is a false warning."
            )


def test_reducing_the_customer_count_shrinks_demand_rather_than_improving_the_plan():
    """The specific number that must never be read as a 25% saving.

    Measured 2026-08-21: 7 customers scores 66,548.24 against baseline's 81,789.36 —
    an apparent 18.6% "improvement" that is really 12% less demand to serve.
    """
    _, baseline_total, _ = _demand_totals("network.customers", 8)
    _, fewer_total, _ = _demand_totals("network.customers", 7)
    assert fewer_total < baseline_total, "fewer customers must mean less demand"
    assert SETTINGS_BY_KEY["network.customers"].answer_class == PROBLEM_SIZE
    assert SETTINGS_BY_KEY["network.customers"].as_dict()["comparable_to_baseline"] is False


# ---------------------------------------------------------------------------
# guardrail 4: the caveat travels with the change, not just the schema
# ---------------------------------------------------------------------------


def test_a_resized_change_carries_its_not_comparable_caveat_in_the_change_list():
    """🔴 "WHAT YOU CHANGED" is what a planner reads before running.

    A caveat that lives only in the settings schema is a caveat nobody sees at the
    moment it matters. Reducing the customer count produces a *lower* objective
    (66,548.24 vs 81,789.36 at 7 customers), and that number must never reach a
    screen without the sentence explaining it is a smaller problem, not a better
    plan.
    """
    from src.scenario.preview import build_preview

    preview = build_preview("smaller-base", overrides={"network.customers": 7})
    assert preview["validation"]["ok"]
    changes = preview["config_changes"]
    assert len(changes) == 1
    change = changes[0]
    assert change["group"] == "network" and change["parameter"] == "customers"
    assert change["baseline_value"] == 8 and change["scenario_value"] == 7
    # It moves the answer...
    assert change["reaches_optimizer"] is True
    # ...but the answer it moves to is not comparable, and says so.
    assert change["answer_class"] == PROBLEM_SIZE
    assert change["comparable_to_baseline"] is False
    assert "81,789.36" in change["not_comparable_note"]


def test_a_node_count_change_is_marked_comparable_and_carries_no_false_caveat():
    """The other half: don't cry wolf on a change that IS comparable."""
    from src.scenario.preview import build_preview

    change = build_preview(
        "reduce-a-warehouse", overrides={"network.distribution_centers": 1}
    )["config_changes"][0]
    assert change["answer_class"] == NETWORK_SHAPE
    assert change["comparable_to_baseline"] is True
    assert "not_comparable_note" not in change


def test_a_scenario_tier_change_gets_no_answer_class_at_all():
    """The classes are a network-tier concept. Nothing else should sprout one."""
    from src.scenario.preview import build_preview

    change = build_preview(
        "just-demand", overrides={"demand.base_units_per_customer_period": 52}
    )["config_changes"][0]
    assert "answer_class" not in change
    assert "comparable_to_baseline" not in change


def test_a_fractional_count_is_a_typing_mistake_not_a_plant_less_network():
    """0.5 plants should be told it needs a whole number, not lectured about zero.

    The floor check is deliberately gated on `_is_int`: a fractional value below the
    floor would otherwise collect the measured "zero plants crashes the generator"
    sentence, which is true about the floor but not about what the planner typed.
    """
    for value in (0.5, 2.5):
        result = validate_overrides({"network.plants": value})
        assert not result.ok
        assert result.refusals[0].code == "wrong_type", value
        assert "whole number" in result.refusals[0].message

    # ...while a genuine zero still gets the measured explanation.
    assert validate_overrides({"network.plants": 0}).refusals[0].code == (
        "network_count_below_floor"
    )


def test_a_boolean_is_not_a_count():
    """`True` is an int in Python. It is not two plants, and it is not one either."""
    result = validate_overrides({"network.plants": True})
    assert not result.ok
    assert result.refusals[0].code == "wrong_type"
