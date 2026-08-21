"""Iteration 6a Phase 1 — the settings ledger, mechanically enforced.

Guardrail 1 is *no no-op controls*: a control that cannot change the optimizer's
answer must not be presented as if it can. ``src/scenario/ledger.py`` declares a
``reach`` for each of the 67 settings, and this module refuses to take that on
trust. Two independent derivations reproduce it from the running system:

1. **What does the setting write?** Build the nine tables twice — once as-is, once
   with the setting moved — and diff. In memory, no disk.
2. **Does the optimizer read that column?** Perturb the column on a loaded state
   and re-run the optimizer. If an objective moves, it is read.

A setting is inert exactly when every column it writes is unread.
**If the optimizer's reads ever change, the derived reach stops matching the
declared reach and these tests fail — which is the signal that a label on the
screen has become a lie.**

The ablation lives here rather than in ``src/`` on purpose: it runs the optimizer,
and Phase 1 ships no execution path.
"""

from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

import pytest

from src.scenario.ledger import (
    CONDITIONAL,
    INERT,
    LABEL_ONLY,
    NETWORK_KEYS,
    NETWORK_SHAPE,
    PROBLEM_SIZE,
    SETTINGS,
    SETTINGS_BY_KEY,
    UNCONDITIONAL,
    classify,
    derive_setting_targets,
    ledger_counts,
)
from src.scenario.synthesize import complete_config
from src.scenario.tables import (
    PIPELINE_TABLES,
    TABLE_FIELDNAMES,
    build_tables,
    formatted_columns,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATED_ROOT = REPO_ROOT / "data" / "generated"
DATA_ROOT = "data/generated"

#: The tables the optimizer and forecast never read. Iteration 5 §1.3, re-proven
#: behaviourally by ``optimizer_reads`` below rather than restated.
NON_PIPELINE_TABLES = ("nodes", "bom", "production_lines")


# ---------------------------------------------------------------------------
# derivation 2: which columns does the optimizer actually read?
# ---------------------------------------------------------------------------


def _perturb_column(frame, column: str):
    import polars as pl

    dtype = frame.schema[column]
    if dtype.is_numeric():
        cast_to = dtype if dtype.is_float() else pl.Int64
        return frame.with_columns(
            (pl.col(column).cast(pl.Float64) * 1.7 + 3.0).cast(cast_to).alias(column)
        )
    return frame.with_columns(pl.lit("LEDGER_PROBE").alias(column))


def _objectives(state, forecast) -> tuple[float, float]:
    from src.optimize.baseline.policy import optimize_baseline
    from src.optimize.classical.tuned import optimize_classical

    return (
        float(optimize_baseline(state, forecast)["metrics"]["objective"]),
        float(optimize_classical(state, forecast)["metrics"]["objective"]),
    )


def derive_optimizer_reads(
    columns: tuple[tuple[str, str], ...],
    scenario: str = "baseline",
    horizon: int = 8,
) -> dict[tuple[str, str], bool]:
    """``(table, column) -> did perturbing it move an objective?``

    Behavioural, because a textual scan cannot work: ``capacity_units_per_period``
    is a column on both ``nodes`` (never read) and ``lanes`` (read), so a grep for
    the literal answers the wrong question.

    Only a ``demand`` perturbation forces a forecast refit — the forecast is what
    reads ``demand`` — so every other table reuses one warm forecast. That is what
    keeps this affordable inside ``make test``.
    """
    from src.forecast.statistical import forecast_finished_goods
    from src.ingest.state import load_scenario_state

    state = load_scenario_state(scenario, data_root=DATA_ROOT)
    forecast = forecast_finished_goods(state, horizon=horizon)
    reference = _objectives(state, forecast)

    verdict: dict[tuple[str, str], bool] = {}
    for table, column in columns:
        if column == "__rows__":
            # A row-count change to a table the pipeline reads necessarily changes
            # what it reads. Asserted end-to-end for horizon_periods in
            # test_history_length_moves_the_capacity_read_period rather than
            # simulated by deleting rows, which would break referential integrity.
            verdict[(table, column)] = table in PIPELINE_TABLES
            continue
        frame = getattr(state, table, None)
        if frame is None or column not in frame.columns:
            verdict[(table, column)] = False
            continue
        probed = replace(state, **{table: _perturb_column(frame, column)})
        try:
            probed_forecast = (
                forecast_finished_goods(probed, horizon=horizon) if table == "demand" else forecast
            )
            got = _objectives(probed, probed_forecast)
        except Exception:
            # Corrupting the column did not move the objective — it broke the run
            # outright. That is the *strongest* evidence the column is read: it was
            # looked up, and the lookup failed.
            #
            # Reachable since Iteration 6b: the network counts derive changes to
            # identifier columns (`demand.sku_id`, `demand.node_id`), where the
            # string probe replaces a foreign key with "LEDGER_PROBE" and breaks
            # referential integrity rather than merely moving a number. Before 6b
            # every probed string column was a free-text label, so this never fired.
            #
            # Treating a crash as "unread" would be the dangerous direction: it would
            # let a load-bearing column be labelled inert.
            verdict[(table, column)] = True
            continue
        verdict[(table, column)] = any(abs(a - b) > 1e-9 for a, b in zip(got, reference))
    return verdict


# ---------------------------------------------------------------------------
# fixtures — the derivations are the expensive part, so run them once
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def complete_base_config() -> dict:
    """Baseline plus BOTH optional blocks, so all 67 settings are present.

    Deriving against ``baseline`` alone would report every ``demand.shock.*`` and
    ``lane_disruption.*`` setting as writing nothing, because the blocks are
    ``null`` there.
    """
    return complete_config(
        "custom-ledger-probe",
        overrides={
            "demand.shock.multiplier": 1.5,
            "lane_disruption.capacity_multiplier": 0.0,
        },
    )


@pytest.fixture(scope="module")
def setting_targets(complete_base_config) -> dict[str, set[tuple[str, str]]]:
    return derive_setting_targets(complete_base_config)


@pytest.fixture(scope="module")
def optimizer_reads(setting_targets) -> dict[tuple[str, str], bool]:
    columns = sorted(
        {target for targets in setting_targets.values() for target in targets}
        | {write for setting in SETTINGS for write in setting.writes}
    )
    return derive_optimizer_reads(tuple(columns))


# ---------------------------------------------------------------------------
# the ledger's shape
# ---------------------------------------------------------------------------


def test_the_ledger_covers_67_settings_across_8_groups():
    """59 scenario settings (6a) plus the 8 network counts (6b)."""
    assert len(SETTINGS) == 67
    assert len({setting.key for setting in SETTINGS}) == 67, "duplicate setting keys"
    from collections import Counter

    by_group = Counter(setting.group for setting in SETTINGS)
    assert dict(by_group) == {
        "network": 8,
        "simulation": 1,
        "demand": 11,
        "capacity": 7,
        "lanes": 18,
        "lane_disruption": 7,
        "costs": 12,
        "service_targets": 3,
    }


def test_the_network_tier_is_exactly_the_eight_counts():
    """Iteration 6b: the network block is editable now, and it is closed.

    6a asserted the opposite (no network setting may exist). That assertion was
    correct for 6a and is what this replaces — the tier is deliberately capped at
    the eight counts the generator actually reads from ``config["network"]``.
    """
    network = [setting for setting in SETTINGS if setting.group == "network"]
    assert {setting.key for setting in network} == set(NETWORK_KEYS)
    assert all(setting.key.startswith("network.") for setting in network)
    assert all(setting.kind == "int" for setting in network), "every count is a whole number"
    # Guardrail 1 of 6b: nothing may crash. Every count carries a floor.
    assert all(setting.minimum is not None and setting.maximum is not None
               for setting in network), "a count with no bounds can reach the generator"


def test_the_ledger_counts_are_what_the_iteration_claims():
    counts = ledger_counts()
    assert counts["total"] == 67
    assert counts[UNCONDITIONAL] == 45  # 38 from 6a + the 7 live network counts
    assert counts[CONDITIONAL] == 6
    assert counts[INERT] == 15  # 14 from 6a + network.lines_per_plant
    assert counts[LABEL_ONLY] == 1
    # The number that matters for guardrail 1: how many controls cannot move the
    # answer. The plan predicted 13 from a hand trace; the derivation found 15 in
    # 6a, and `network.lines_per_plant` makes 16.
    assert counts["cannot_change_the_answer"] == 16


# ---------------------------------------------------------------------------
# the in-memory build has to be the real thing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", ["baseline", "component-shortage-shock"])
def test_in_memory_build_matches_the_generated_csvs(scenario):
    """Pins ``build_tables`` to ``generate()``.

    The whole ledger rests on the in-memory build being what the generator would
    have written. If ``generate()`` ever builds differently, this fails first and
    the derived reach labels cannot quietly drift with it.
    """
    directory = GENERATED_ROOT / scenario
    if not directory.exists():  # pragma: no cover - depends on `make demo-data`
        pytest.skip(f"{scenario} is not generated")
    import yaml

    config = yaml.safe_load((REPO_ROOT / "data" / "scenarios" / f"{scenario}.yaml").read_text())
    tables = build_tables(config, 12345)
    columns = formatted_columns(tables)

    for table, fieldnames in TABLE_FIELDNAMES.items():
        with (directory / f"{table}.csv").open(encoding="utf-8") as handle:
            on_disk = list(csv.DictReader(handle))
        assert len(on_disk) == len(tables[table]), f"{table} row count"
        for column in fieldnames:
            assert [row[column] for row in on_disk] == columns[(table, column)], (
                f"{scenario}: {table}.{column} differs from the generated CSV"
            )


# ---------------------------------------------------------------------------
# 🔴 the load-bearing test: declared reach == derived reach
# ---------------------------------------------------------------------------


def test_declared_reach_matches_what_the_derivations_prove(setting_targets, optimizer_reads):
    """**This failing means a label on the screen has become a lie.**"""
    derived = classify(setting_targets, optimizer_reads)
    mismatches = {
        key: (SETTINGS_BY_KEY[key].reach, value)
        for key, value in derived.items()
        if SETTINGS_BY_KEY[key].reach != value
    }
    assert not mismatches, (
        "the ledger's declared reach no longer matches what the optimizer does: "
        + "; ".join(f"{key}: declared {a}, derived {b}" for key, (a, b) in mismatches.items())
    )


def test_every_declared_write_is_a_column_the_setting_really_changes(setting_targets):
    """A ``writes`` entry that nothing observes is documentation nobody can trust."""
    unobserved = {
        setting.key: [f"{t}.{c}" for t, c in setting.writes if (t, c) not in setting_targets[setting.key]]
        for setting in SETTINGS
        if any((t, c) not in setting_targets[setting.key] for t, c in setting.writes)
    }
    assert not unobserved, f"declared writes that never change: {unobserved}"


def test_a_setting_that_reaches_the_optimizer_names_a_column_the_optimizer_reads(optimizer_reads):
    """Stops a lever being documented by a column that is not the lever.

    ``service_targets.days_inventory_target`` is the reason this exists: it reaches
    the optimizer by sizing ``initial_inventory.on_hand_units``, *not* through the
    ``service_targets`` column of the same name — which is never read.
    """
    wrong = [
        setting.key
        for setting in SETTINGS
        if setting.reaches_optimizer
        and not any(optimizer_reads.get(write, False) for write in setting.writes)
    ]
    assert not wrong, f"these declare no column the optimizer reads: {wrong}"


def test_settings_that_cannot_change_the_answer_declare_only_unread_columns(optimizer_reads):
    """The composition that makes the no-op labelling true end to end.

    A setting is safe to label "recorded in the dataset, not read by the optimizer"
    when (a) the only columns it writes are these — proven by
    ``test_every_declared_write_is_a_column_the_setting_really_changes`` plus
    ``test_declared_reach_matches_what_the_derivations_prove`` — and (b) none of
    those columns is read, which is what this asserts.
    """
    leaking = [
        setting.key
        for setting in SETTINGS
        if not setting.reaches_optimizer
        and any(optimizer_reads.get(write, False) for write in setting.writes)
    ]
    assert not leaking, f"labelled as unable to change the answer, but read: {leaking}"


def test_the_thirteen_inert_settings_the_plan_predicted_are_all_inert():
    """§1.4's hand-traced list, pinned by name so a rename cannot lose one."""
    predicted = {
        "capacity.plant_storage_periods",
        "capacity.supplier_capacity_units_per_period",
        "capacity.supplier_storage_units",
        "capacity.dc_throughput_units_per_period",
        "capacity.dc_storage_units",
        "capacity.customer_storage_units",
        "service_targets.criticality_tier",
        *(f"lanes.{family}.{column}"
          for family in ("inbound_raw", "plant_to_dc", "dc_to_customer")
          for column in ("lead_time_std_days", "co2_kg_per_unit")),
    }
    assert len(predicted) == 13
    for key in sorted(predicted):
        assert SETTINGS_BY_KEY[key].reach == INERT, key
        assert SETTINGS_BY_KEY[key].reaches_optimizer is False, key


def test_the_two_disruption_names_are_labels_not_levers():
    """The Phase 1 refinement of §1.4's ledger, found by the derivation.

    The plan counted ``lane_disruption.name`` among the 7 conditional settings and
    ``demand.shock.name`` among the 39 unconditional ones. Neither can move the
    answer: the generator reads only ``start_period``, ``duration_periods`` and
    ``multiplier`` from a shock block, so the shock's name reaches no table at all,
    and the disruption's name reaches only ``lane_periods.disruption_code``, which
    the optimizer never reads.
    """
    assert SETTINGS_BY_KEY["demand.shock.name"].reach == LABEL_ONLY
    assert SETTINGS_BY_KEY["lane_disruption.name"].reach == INERT
    assert SETTINGS_BY_KEY["lane_disruption.name"].writes == (("lane_periods", "disruption_code"),)
    for key in ("demand.shock.name", "lane_disruption.name"):
        assert SETTINGS_BY_KEY[key].reaches_optimizer is False


def test_demand_shock_name_reaches_no_table_at_all(setting_targets):
    assert setting_targets["demand.shock.name"] == set()


# ---------------------------------------------------------------------------
# the Iteration 5 §1.3 findings, re-proven rather than restated
# ---------------------------------------------------------------------------


def test_nodes_bom_and_production_lines_are_never_read_by_the_optimizer():
    """Iteration 5 §1.3, behaviourally. These three tables are the dataset layer.

    They are read 5x by ``src/dataset/`` — this is why the label has to be
    "recorded in the dataset, not read by the optimizer" and not "has no effect".
    """
    from src.ingest.state import load_scenario_state

    state = load_scenario_state("baseline", data_root=DATA_ROOT)
    columns = tuple(
        (table, column)
        for table in NON_PIPELINE_TABLES
        for column in getattr(state, table).columns
        if column not in ("scenario", "seed")
    )
    reads = derive_optimizer_reads(columns)
    assert not [target for target, was_read in reads.items() if was_read], (
        "a table the ledger treats as dataset-only is now load-bearing: "
        f"{[t for t, r in reads.items() if r]}"
    )


def test_capacity_read_period_equals_the_configured_history_length():
    """Pins the identity ``validate.capacity_read_period`` relies on.

    The optimizer reads lane capacity at ``ScenarioState.horizon()`` =
    ``max(demand.period)``. The validator has to answer that question for a config
    that has *not* been generated yet, so it uses ``simulation.horizon_periods``.
    This is what proves those two are the same number — and it is why the warning
    can never hardcode 52.
    """
    import yaml

    from src.ingest.state import load_scenario_state
    from src.scenario.validate import capacity_read_period

    for scenario in ("baseline", "component-shortage-shock", "demand-surge", "stress-large"):
        if not (GENERATED_ROOT / scenario).exists():  # pragma: no cover
            pytest.skip(f"{scenario} is not generated")
        config = yaml.safe_load(
            (REPO_ROOT / "data" / "scenarios" / f"{scenario}.yaml").read_text()
        )
        state = load_scenario_state(scenario, data_root=DATA_ROOT)
        assert capacity_read_period(config) == int(state.horizon()), scenario


def test_zeroing_a_whole_lane_family_lowers_the_objective_and_changes_only_transport():
    """🔴 Pins the measured fact behind the capacity-wipe warning.

    Zeroing every lane of a family at the capacity read period does **not** create
    a shortage. Service is untouched and only transport cost moves, so the
    objective *falls* by roughly the cost of the traffic that stopped running. A
    planner who builds "we lose every supplier lane" and reads a cheaper plan has
    been misled, which is why ``validate.capacity_wipe_warning`` says so up front.

    This started as a refusal on the assumption the objective would be garbage.
    It is not garbage — it is worse than garbage, because it looks like an
    improvement. If a future change makes a wipe cause real shortages, this test
    fails and that warning should be rewritten.
    """
    import polars as pl

    from src.forecast.statistical import forecast_finished_goods
    from src.ingest.state import load_scenario_state

    state = load_scenario_state("baseline", data_root=DATA_ROOT)
    forecast = forecast_finished_goods(state, horizon=8)
    read_period = int(state.horizon())
    base_metrics = _classical_metrics(state, forecast)

    lane_ids = state.lanes.filter(pl.col("lane_type") == "inbound_raw")["lane_id"].to_list()
    assert lane_ids, "baseline should have inbound lanes"
    wiped_periods = state.lane_periods.with_columns(
        pl.when(pl.col("lane_id").is_in(lane_ids) & (pl.col("period") == read_period))
        .then(pl.lit(0))
        .otherwise(pl.col("effective_capacity_units"))
        .alias("effective_capacity_units")
    )
    wiped = _classical_metrics(replace(state, lane_periods=wiped_periods), forecast)

    assert wiped["objective"] < base_metrics["objective"], (
        "zeroing every inbound lane no longer lowers the objective — the capacity-wipe "
        "warning describes a mechanism that has changed"
    )
    assert wiped["fill_rate"] == pytest.approx(base_metrics["fill_rate"]), (
        "a full capacity wipe now moves service, so it is no longer only a transport effect"
    )
    base_costs = base_metrics["cost_breakdown"]
    wiped_costs = wiped["cost_breakdown"]
    assert wiped_costs["transport"] < base_costs["transport"]
    for component in ("holding", "ordering", "backorder", "lost_sale"):
        assert wiped_costs[component] == pytest.approx(base_costs[component]), (
            f"{component} cost moved; the wipe is no longer transport-only"
        )


def _classical_metrics(state, forecast) -> dict:
    from src.optimize.classical.tuned import optimize_classical

    return optimize_classical(state, forecast)["metrics"]


def test_both_shipped_disruptions_miss_the_capacity_read_period():
    """§1.3 pinned as a test so nobody "fixes" it silently (risk register).

    Both ``component-shortage-shock`` (periods 18-27 against a read period of 52)
    and ``stress-large`` (38-53 against 104) carry a lane disruption the optimizer
    never sees. Decision 4 warns rather than widens; if someone widens the read,
    this test is where it surfaces.
    """
    import polars as pl

    from src.ingest.state import load_scenario_state

    for scenario in ("component-shortage-shock", "stress-large"):
        if not (GENERATED_ROOT / scenario).exists():  # pragma: no cover
            pytest.skip(f"{scenario} is not generated")
        state = load_scenario_state(scenario, data_root=DATA_ROOT)
        read_period = int(state.horizon())
        disrupted = state.lane_periods.filter(pl.col("capacity_multiplier") != 1.0)
        assert disrupted.height > 0, f"{scenario} should carry a disruption"
        at_read = disrupted.filter(pl.col("period") == read_period)
        assert at_read.height == 0, (
            f"{scenario}'s disruption now covers the capacity read period {read_period} — "
            "the optimizer's capacity read has changed and decision 4 needs revisiting"
        )
