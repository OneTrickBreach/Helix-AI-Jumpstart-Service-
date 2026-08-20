"""Iteration 6a Phase 3 — running a custom scenario.

The load-bearing test here is the **fairness invariant**: a custom scenario whose
settings equal ``baseline``'s must reproduce ``81,789.359460`` exactly. §1.2 proved
that reachable before any code was written, which means a failure is not a
surprising property of the generator — it is 6a having broken something.

The rest guards decision 8. A custom run defaults to the fast path (no PPO, no
written rationale) because the lever loop has to be drag-run-read, and the
rationale alone is ~20x the numeric comparison. But **the four recorded scenarios
keep exactly their old behaviour**, and a skipped rationale comes back as a real
object with a "not generated" marker — never ``null``, because the results screen
dereferences it.

Artifact writes go to ``HELIX_BENCHMARK_DIR`` for the whole session (see
``conftest.isolate_benchmark_artifacts``), so these tests cannot touch the demo's
recorded runs. The property worth asserting is therefore that artifacts are
**name-keyed**: a custom run writes its own file and no canonical-named one.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.api.health import app
from src.api.pipeline import resolve_run_flags
from src.api.ratelimit import reset_limits
from src.bench.profiler import benchmark_dir
from src.rag.advisory import NOT_GENERATED_SOURCE, not_generated_rationale
from src.scenario import store
from src.scenario.run_card import build_run_card, load_config_for
from src.scenario.synthesize import CANONICAL_SCENARIOS, complete_config

API_KEY = "test-key-iteration6a-phase3"
TEST_MARKER = "pytest6a3"

#: The recorded value every document quotes. If this moves, stop.
BASELINE_CLASSICAL = "81789.359460"
BASELINE_NAIVE = "88022.760795"

#: Every field ``web/src/types.ts`` declares required on ``Rationale``. A skipped
#: rationale has to satisfy the same contract or the results screen breaks.
REQUIRED_RATIONALE_FIELDS = (
    "advisory", "label", "scenario", "selected_approach",
    "advisory_rationale", "citations", "prompt_injection_flags",
)


def _headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


def _slug(name: str) -> str:
    return f"{TEST_MARKER}-{name}"


def _purge() -> None:
    for entry in store.list_custom():
        if TEST_MARKER in entry["scenario"]:
            store._remove(entry["scenario"])


@pytest.fixture(autouse=True)
def clean_slate():
    reset_limits()
    _purge()
    yield
    _purge()
    reset_limits()


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("HELIX_API_KEY", API_KEY)
    return TestClient(app)


def _save(slug: str, **overrides) -> str:
    scenario = store.scenario_name_for(slug)
    store.save(slug, complete_config(scenario, overrides=overrides or None))
    return scenario


def _objective(payload: dict, approach: str = "classical") -> str:
    row = next(
        r for r in payload["benchmark"]["comparison"] if r["approach"] == approach
    )
    return f"{row['objective']:.6f}"


# ---------------------------------------------------------------------------
# the fairness invariant
# ---------------------------------------------------------------------------


def test_a_custom_scenario_equal_to_baseline_reproduces_the_recorded_objective(monkeypatch):
    """The invariant the whole iteration rests on.

    The generator seeds only from the numeric seed — the scenario *name* is not
    part of it (§1.2) — so a custom scenario that changes nothing has to land on
    the recorded number to the digit.
    """
    client = _client(monkeypatch)
    scenario = _save(_slug("fair"))
    response = client.post(
        "/scenario-comparison", headers=_headers(), json={"scenario": scenario, "horizon": 8}
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert _objective(data, "classical") == BASELINE_CLASSICAL
    assert _objective(data, "baseline") == BASELINE_NAIVE


def test_the_same_saved_scenario_run_twice_returns_the_identical_objective(monkeypatch):
    client = _client(monkeypatch)
    scenario = _save(_slug("determinism"), **{"demand.base_units_per_customer_period": 51})
    first, second = (
        client.post("/scenario-comparison", headers=_headers(),
                    json={"scenario": scenario}).json()["data"]
        for _ in range(2)
    )
    assert _objective(first) == _objective(second)
    assert _objective(first, "baseline") == _objective(second, "baseline")


def test_a_changed_setting_actually_moves_the_objective(monkeypatch):
    """The complement of the fairness invariant.

    Without this, a bug that ignored the custom config entirely would satisfy
    every reproducibility test in this file by always returning baseline's number.
    """
    client = _client(monkeypatch)
    scenario = _save(_slug("moves"), **{"costs.holding_cost.finished_good": 4.0})
    data = client.post("/scenario-comparison", headers=_headers(),
                       json={"scenario": scenario}).json()["data"]
    assert _objective(data) != BASELINE_CLASSICAL


# ---------------------------------------------------------------------------
# decision 8 — the defaults, and what a skipped rationale looks like
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", CANONICAL_SCENARIOS)
def test_a_recorded_scenario_defaults_to_its_existing_full_behaviour(scenario):
    """No recorded result may change shape because Phase 3 landed."""
    assert resolve_run_flags(scenario, None, None) == (True, True)


def test_a_custom_scenario_defaults_to_the_fast_path():
    assert resolve_run_flags("custom-anything", None, None) == (False, False)


@pytest.mark.parametrize("scenario", ["baseline", "custom-anything"])
@pytest.mark.parametrize("ppo,rationale", [(True, True), (False, False), (True, False)])
def test_explicit_flags_always_win_over_the_default(scenario, ppo, rationale):
    assert resolve_run_flags(scenario, ppo, rationale) == (ppo, rationale)


def test_a_custom_run_excludes_ppo_and_says_so_rather_than_omitting_it(monkeypatch):
    client = _client(monkeypatch)
    scenario = _save(_slug("noppo"))
    data = client.post("/scenario-comparison", headers=_headers(),
                       json={"scenario": scenario}).json()["data"]
    assert data["run_settings"] == {
        "include_ppo": False, "include_rationale": False, "is_custom": True,
        "horizon": 8, "excluded": ["ppo", "rationale"],
    }
    # "not_evaluated" rather than silence: a comparison that did not run PPO must
    # not read as one where PPO had nothing to say.
    assert data["benchmark"]["ppo_outcome"] == "not_evaluated"
    assert [r["approach"] for r in data["benchmark"]["comparison"]] == ["baseline", "classical"]


def test_a_skipped_rationale_is_a_real_object_never_null(monkeypatch):
    client = _client(monkeypatch)
    scenario = _save(_slug("norat"))
    data = client.post("/scenario-comparison", headers=_headers(),
                       json={"scenario": scenario}).json()["data"]
    rationale = data["rationale"]
    assert rationale is not None
    assert isinstance(rationale, dict)
    for field in REQUIRED_RATIONALE_FIELDS:
        assert field in rationale, f"the results screen dereferences {field}"
    assert rationale["generated"] is False
    assert rationale["advisory_text_source"] == NOT_GENERATED_SOURCE
    assert "NOT GENERATED" in rationale["label"]
    # The numbers are real and their provenance is unchanged; only prose was skipped.
    assert rationale["numeric_metrics_generated_by"] == "optimizer_benchmark_not_llm"
    assert rationale["selected_approach"] == data["benchmark"]["winner"]["approach"]


def test_the_placeholder_path_is_exercised_for_a_recorded_scenario_too(monkeypatch):
    """Decision 8's DoD: exercised by a test, not only by custom runs.

    A ``null`` rationale would break the results screen for the four shipped
    scenarios as well, so the opt-out has to be proven safe on one of them —
    without paying the ~20 s the real rationale costs.
    """
    client = _client(monkeypatch)
    data = client.post(
        "/scenario-comparison", headers=_headers(),
        json={"scenario": "baseline", "include_ppo": False, "include_rationale": False},
    ).json()["data"]
    assert data["rationale"]["generated"] is False
    for field in REQUIRED_RATIONALE_FIELDS:
        assert field in data["rationale"]
    # The opt-out must not disturb the recorded number.
    assert _objective(data) == BASELINE_CLASSICAL


def test_not_generated_rationale_survives_a_threadbare_benchmark_result():
    """It runs on the failure-adjacent paths, so it must not assume rich input."""
    rationale = not_generated_rationale({"scenario": "custom-x"})
    for field in REQUIRED_RATIONALE_FIELDS:
        assert field in rationale
    assert rationale["citations"] == []
    assert rationale["prompt_injection_flags"] == []
    assert rationale["generated"] is False


# ---------------------------------------------------------------------------
# artifacts — decision 10
# ---------------------------------------------------------------------------


def test_a_custom_run_writes_its_own_name_keyed_artifact_and_no_canonical_one(monkeypatch):
    """Artifact writes are redirected for the whole session, so what this proves
    is the *name-keying*: a custom run cannot land on a canonical filename."""
    client = _client(monkeypatch)
    scenario = _save(_slug("artifact"))
    for name in CANONICAL_SCENARIOS:
        (benchmark_dir() / f"{name}-head-to-head-comparison.json").unlink(missing_ok=True)

    client.post("/scenario-comparison", headers=_headers(), json={"scenario": scenario})

    written = benchmark_dir() / f"{scenario}-head-to-head-comparison.json"
    assert written.is_file()
    assert json.loads(written.read_text(encoding="utf-8"))["scenario"] == scenario
    for name in CANONICAL_SCENARIOS:
        assert not (benchmark_dir() / f"{name}-head-to-head-comparison.json").exists(), (
            f"a custom run wrote {name}'s artifact"
        )


# ---------------------------------------------------------------------------
# the no-op window: warned before, explained after
# ---------------------------------------------------------------------------


NOOP_WINDOW = {
    "lane_disruption.lane_type": "inbound_raw",
    "lane_disruption.affected_lane_count": 2,
    "lane_disruption.start_period": 18,
    "lane_disruption.duration_periods": 10,
    "lane_disruption.capacity_multiplier": 0.0,
    "lane_disruption.lead_time_multiplier": 2.0,
    "lane_disruption.name": "pytest_noop",
}


def test_a_window_that_misses_the_read_period_is_warned_about_before_the_run(monkeypatch):
    client = _client(monkeypatch)
    scenario = _save(_slug("noopwin"), **NOOP_WINDOW)
    card = client.get(
        "/scenario-comparison/card", headers=_headers(), params={"scenario": scenario}
    ).json()["data"]
    codes = [w["code"] for w in card["warnings"]]
    assert "capacity_window_misses_read_period" in codes
    warning = card["warnings"][0]
    assert warning["detail"]["capacity_read_period"] == 52
    assert warning["detail"]["reaches_optimizer"] is False
    # Extending to the end of the horizon: 18 + 35 - 1 == 52.
    assert warning["detail"]["suggested_duration_periods"] == 35
    assert "resilience" in warning["do_not_read_as"]


def test_the_same_window_is_explained_after_the_run_and_really_is_a_no_op(monkeypatch):
    client = _client(monkeypatch)
    scenario = _save(_slug("noopafter"), **NOOP_WINDOW)
    data = client.post("/scenario-comparison", headers=_headers(),
                       json={"scenario": scenario}).json()["data"]
    assert [w["code"] for w in data["warnings"]] == ["capacity_window_misses_read_period"]
    assert data["capacity_reachability"]["reaches_optimizer"] is False
    # The proof that the warning is telling the truth: zeroing two lanes for ten
    # periods leaves the objective exactly where baseline's is.
    assert _objective(data) == BASELINE_CLASSICAL


def test_a_window_covering_the_read_period_is_not_warned_about_and_does_move_it(monkeypatch):
    client = _client(monkeypatch)
    reaching = {**NOOP_WINDOW, "lane_disruption.start_period": 40,
                "lane_disruption.duration_periods": 13}
    scenario = _save(_slug("reaches"), **reaching)
    data = client.post("/scenario-comparison", headers=_headers(),
                       json={"scenario": scenario}).json()["data"]
    assert data["warnings"] == []
    assert data["capacity_reachability"]["reaches_optimizer"] is True
    assert _objective(data) != BASELINE_CLASSICAL


# ---------------------------------------------------------------------------
# the pre-run card
# ---------------------------------------------------------------------------


def test_the_card_does_not_charge_for_generation_a_saved_scenario_does_not_need():
    slug = _slug("card")
    scenario = _save(slug)
    card = build_run_card(scenario, include_ppo=False, include_rationale=False)
    stages = [component["stage"] for component in card["estimate"]["components"]]
    assert "generate" not in stages, "the data is already on disk"
    assert stages == ["forecast", "optimize"]
    assert card["fixed_inputs"]["seed"] == 12345
    assert card["fixed_inputs"]["history_periods"] == 52
    assert card["is_custom"] is True
    assert "CUSTOM SCENARIO" in card["label"]
    assert card["runs_nothing_yet"] is True


def test_every_estimate_component_states_its_basis():
    """An estimate without a basis is a guess with a decimal point."""
    card = build_run_card("baseline", include_ppo=True, include_rationale=True)
    for component in card["estimate"]["components"]:
        assert component["basis"].strip(), f"{component['stage']} has no basis"
        assert len(component["basis"]) > 25


def test_the_card_names_what_is_excluded_in_a_planners_words():
    slug = _slug("excl")
    scenario = _save(slug)
    card = build_run_card(scenario, include_ppo=False, include_rationale=False)
    excluded = {item["stage"]: item["why"] for item in card["excluded"]}
    assert set(excluded) == {"ppo", "rationale"}
    for why in excluded.values():
        assert why.endswith(".")


def test_the_card_works_for_a_canonical_scenario_without_a_saved_config():
    card = build_run_card("baseline", include_ppo=True, include_rationale=True)
    assert card["is_custom"] is False
    assert "RECORDED BENCHMARK" in card["label"]
    assert "written advisory rationale" in card["will_run"]


def test_the_card_endpoint_404s_for_a_scenario_that_does_not_exist(monkeypatch):
    client = _client(monkeypatch)
    response = client.get(
        "/scenario-comparison/card", headers=_headers(), params={"scenario": "custom-ghost-xyz"}
    )
    assert response.status_code == 404


def test_the_card_endpoint_requires_the_api_key(monkeypatch):
    monkeypatch.setenv("HELIX_API_KEY", API_KEY)
    client = TestClient(app)
    assert client.get(
        "/scenario-comparison/card", params={"scenario": "baseline"}
    ).status_code == 401


def test_load_config_for_reads_a_saved_custom_scenario_and_a_canonical_one():
    slug = _slug("cfg")
    scenario = _save(slug, **{"demand.base_units_per_customer_period": 47})
    assert load_config_for(scenario)["demand"]["base_units_per_customer_period"] == 47
    assert load_config_for("baseline")["scenario"] == "baseline"


# ---------------------------------------------------------------------------
# the stream
# ---------------------------------------------------------------------------


def test_the_stream_emits_truthful_stages_for_a_custom_run(monkeypatch):
    """A skipped rationale gets an explicit `rag/skipped`, not silence.

    A stream that simply stops mentioning a stage looks like a stall — the same
    reasoning behind Iteration 5's `cache/hit` event.
    """
    client = _client(monkeypatch)
    scenario = _save(_slug("stream"))
    with client.stream(
        "GET", "/scenario-comparison/stream", headers=_headers(),
        params={"scenario": scenario},
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    stages = [
        json.loads(line[5:])
        for line in body.splitlines()
        if line.startswith("data:") and '"stage"' in line
    ]
    seen = [f"{event['stage']}/{event['status']}" for event in stages]
    assert seen == [
        "ingest/running", "ingest/complete",
        "forecast/running", "forecast/complete",
        "baseline/running", "baseline/complete",
        "classical/running", "classical/complete",
        "rag/skipped",
    ]
    assert not any("ppo" in stage for stage in seen), "PPO did not run, so it must not be reported"
    assert "event: done" in body


def test_the_stream_honours_an_explicit_opt_in(monkeypatch):
    """An explicit opt-in beats the custom default, and the stages say so."""
    client = _client(monkeypatch)
    scenario = _save(_slug("streamppo"))
    with client.stream(
        "GET", "/scenario-comparison/stream", headers=_headers(),
        params={"scenario": scenario, "include_ppo": "true", "ppo_timesteps": 16},
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    stages = [
        json.loads(line[5:])
        for line in body.splitlines()
        if line.startswith("data:") and '"stage"' in line
    ]
    seen = [f"{event['stage']}/{event['status']}" for event in stages]
    assert "ppo/running" in seen and "ppo/complete" in seen
    assert "rag/skipped" in seen, "the rationale was not opted into, so it is still skipped"
