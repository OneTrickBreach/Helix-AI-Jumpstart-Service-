"""Iteration 5 Phase 3 — the what-if execution engine.

These tests run the real optimizer, so the file is slower than the rest of the
suite. That is the point: the invariants below are the ones that make a what-if
number trustworthy, and none of them can be checked with a stub.

The load-bearing four:

* **fairness** — a no-op perturbation reproduces the base benchmark objective
  *exactly*, so a reported difference is always the perturbation's doing;
* **must-move** — a perturbation that reaches the optimizer changes the plan, so
  the engine cannot quietly do nothing;
* **determinism** — the same question twice gives identical numbers;
* **read-only** — the generated data is byte-identical afterwards.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import polars as pl
import pytest

from src.chat.perturbation import Perturbation, PerturbationError, capacity_read_period
from src.chat.whatif import (
    FORECAST_CACHE,
    RESULT_CACHE,
    apply_perturbation,
    cached_forecast,
    clear_caches,
    confirmation_for,
    demand_fingerprint,
    run_what_if,
)
from src.ingest.state import DEFAULT_DATA_ROOT, load_scenario_state


SCENARIO = "component-shortage-shock"

# The canonical recorded objectives. A what-if's base side must reproduce these,
# because a before/after built on a different base is not a comparison.
RECORDED_CLASSICAL_OBJECTIVE = {
    "baseline": 81789.359460,
    "component-shortage-shock": 95445.445064,
    "demand-surge": 94165.363245,
    "stress-large": 2521615.068565,
}


@pytest.fixture(scope="module")
def state():
    return load_scenario_state(SCENARIO)


@pytest.fixture(autouse=True)
def _clean_caches():
    clear_caches()
    yield
    clear_caches()


def _outage(node_id: str, from_period: int, to_period: int, scenario: str = SCENARIO) -> Perturbation:
    return Perturbation(
        kind="node_outage", scenario=scenario, from_period=from_period, to_period=to_period, node_id=node_id
    )


def _demand(multiplier: float, scope: str = "all", scope_id: str | None = None, scenario: str = SCENARIO) -> Perturbation:
    loaded_limit = 52 if scenario != "stress-large" else 104
    return Perturbation(
        kind="demand_multiplier",
        scenario=scenario,
        from_period=1,
        to_period=loaded_limit,
        demand_multiplier=multiplier,
        scope=scope,
        scope_id=scope_id,
    )


# ------------------------------------------------------------ the overlay


def test_overlay_zeroes_only_the_lanes_and_periods_asked_for(state):
    perturbation = _outage("DC-001", 10, 12)
    perturbed, diff = apply_perturbation(state, perturbation)

    lane_ids = diff["lane_ids"]
    assert lane_ids
    inside = perturbed.lane_periods.filter(
        pl.col("lane_id").is_in(lane_ids) & pl.col("period").is_between(10, 12)
    )
    assert inside.select(pl.sum("effective_capacity_units")).item() == 0

    # Everything else is untouched, including the same lanes outside the window.
    outside = perturbed.lane_periods.filter(
        ~(pl.col("lane_id").is_in(lane_ids) & pl.col("period").is_between(10, 12))
    )
    original_outside = state.lane_periods.filter(
        ~(pl.col("lane_id").is_in(lane_ids) & pl.col("period").is_between(10, 12))
    )
    assert outside.equals(original_outside)


def test_overlay_preserves_the_schema_the_optimizer_reads(state):
    perturbed, _ = apply_perturbation(state, _outage("DC-001", 1, 52))
    assert perturbed.lane_periods.schema == state.lane_periods.schema
    perturbed_demand, _ = apply_perturbation(state, _demand(1.3))
    assert perturbed_demand.demand.schema == state.demand.schema


def test_overlay_shares_untouched_frames(state):
    """A capacity overlay must not disturb demand, and vice versa."""
    perturbed, _ = apply_perturbation(state, _outage("DC-001", 1, 52))
    assert perturbed.demand.equals(state.demand)
    assert perturbed.lanes.equals(state.lanes)
    perturbed_demand, _ = apply_perturbation(state, _demand(2.0))
    assert perturbed_demand.lane_periods.equals(state.lane_periods)


def test_demand_overlay_scopes_to_one_product(state):
    perturbed, diff = apply_perturbation(state, _demand(2.0, scope="sku", scope_id="FG-001"))
    assert diff["scope"] == "sku"
    others = perturbed.demand.filter(pl.col("sku_id") != "FG-001")
    assert others.equals(state.demand.filter(pl.col("sku_id") != "FG-001"))
    assert diff["units_after"] == 2 * diff["units_before"]


def test_multiplier_of_one_is_an_exact_identity(state):
    perturbed, diff = apply_perturbation(state, _demand(1.0))
    assert perturbed.demand.equals(state.demand)
    assert diff["rows_changed"] == 0


# ------------------------------------------------------- the four invariants


@pytest.mark.parametrize("scenario", ["baseline", SCENARIO])
def test_fairness_the_base_side_reproduces_the_recorded_objective(scenario):
    """The base half of a what-if must be the same number the benchmark reports."""
    result = run_what_if(_demand(1.0, scenario=scenario), use_cache=False)
    assert result.base["winner"] == "classical"
    assert result.base["objective"] == pytest.approx(RECORDED_CLASSICAL_OBJECTIVE[scenario], abs=1e-6)


def test_fairness_a_no_op_perturbation_reproduces_the_base_exactly(state):
    """Two different kinds of no-op, both of which must change nothing at all."""
    identity = run_what_if(_demand(1.0), state=state, use_cache=False)
    assert identity.what_if["objective"] == identity.base["objective"]
    assert identity.what_if["cvar_75"] == identity.base["cvar_75"]
    assert identity.moved_the_plan is False

    # A capacity change outside the one period the optimizer reads: real rows are
    # rewritten, and the plan still cannot change.
    unreachable = run_what_if(_outage("DC-001", 3, 6), state=state, use_cache=False)
    assert unreachable.diff["rows_changed"] > 0
    assert unreachable.what_if["objective"] == unreachable.base["objective"]
    assert unreachable.moved_the_plan is False
    assert unreachable.impact["reaches_optimizer"] is False
    assert "does not touch anything this optimizer reads" in unreachable.explanation


def test_must_move_a_reachable_perturbation_changes_the_plan(state):
    """The inverse of the fairness invariant: the engine cannot silently do nothing."""
    read_period = capacity_read_period(state)
    result = run_what_if(_outage("DC-001", 1, read_period), state=state, use_cache=False)
    assert result.impact["reaches_optimizer"] is True
    assert result.moved_the_plan is True
    assert result.what_if["objective"] != result.base["objective"]
    assert result.deltas["objective"]["absolute"] != 0


def _decision_numbers(result) -> dict:
    """Everything a planner would act on, with measured latency excluded.

    Latency is real and varies between runs; it is reported, not asserted.
    """
    def strip(side: dict) -> dict:
        return {
            **{key: value for key, value in side.items() if key != "by_approach"},
            "by_approach": {
                approach: {k: v for k, v in row.items() if k != "latency_seconds"}
                for approach, row in side["by_approach"].items()
            },
        }

    payload = result.as_dict()
    return {"base": strip(payload["base"]), "what_if": strip(payload["what_if"]), "deltas": payload["deltas"]}


def test_determinism_the_same_perturbation_twice_is_identical(state):
    first = run_what_if(_outage("DC-001", 1, 52), state=state, use_cache=False)
    second = run_what_if(_outage("DC-001", 1, 52), state=state, use_cache=False)
    assert _decision_numbers(first) == _decision_numbers(second)
    assert first.fingerprint == second.fingerprint


def test_read_only_the_generated_files_are_byte_identical_afterwards(state):
    directory = Path(DEFAULT_DATA_ROOT) / SCENARIO

    def digest() -> dict[str, str]:
        return {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.glob("*"))
            if path.is_file()
        }

    before = digest()
    run_what_if(_outage("DC-001", 1, 52), state=state, use_cache=False)
    run_what_if(_demand(2.0), state=state, use_cache=False)
    assert digest() == before


def test_a_what_if_never_overwrites_the_recorded_benchmark_artifact(state, tmp_path, monkeypatch):
    """The Phase 1 lesson, re-checked here: the engine writes no run artifact."""
    monkeypatch.setenv("HELIX_BENCHMARK_DIR", str(tmp_path))
    run_what_if(_outage("DC-001", 1, 52), state=state, use_cache=False)
    assert not list(tmp_path.glob("*head-to-head-comparison.json"))


# ------------------------------------------------------------------ caching


def test_capacity_perturbation_reuses_the_cached_forecast(state):
    clear_caches()
    first = run_what_if(_outage("DC-001", 1, 52), state=state, use_cache=False)
    # Base forecast computed once; the perturbed state has identical demand, so
    # the what-if side must hit the cache rather than refit every series.
    assert first.timing["base_forecast_cached"] is False
    assert first.timing["whatif_forecast_cached"] is True


def test_demand_perturbation_invalidates_the_forecast_cache(state):
    clear_caches()
    result = run_what_if(_demand(2.0), state=state, use_cache=False)
    assert result.timing["whatif_forecast_cached"] is False


def test_demand_fingerprint_tracks_only_what_the_forecaster_reads(state):
    baseline = demand_fingerprint(state)
    assert demand_fingerprint(state) == baseline

    scaled, _ = apply_perturbation(state, _demand(2.0))
    assert demand_fingerprint(scaled) != baseline

    # A column the forecaster does not read must not invalidate the cache.
    noise = replace(state, demand=state.demand.with_columns(pl.col("noise_multiplier") * 1.5))
    assert demand_fingerprint(noise) == baseline

    # Nor may rows it does not read: the forecaster fits finished-good customer
    # series only, so scaling a raw component's derived demand must reuse the
    # cached forecast (it still reaches the optimizer, via inbound flow).
    component_only = Perturbation(
        kind="demand_multiplier",
        scenario=SCENARIO,
        from_period=1,
        to_period=52,
        demand_multiplier=2.0,
        scope="sku",
        scope_id="RC-001",
    )
    scaled_component, diff = apply_perturbation(state, component_only)
    assert diff["rows_changed"] > 0
    assert demand_fingerprint(scaled_component) == baseline

    capacity_only, _ = apply_perturbation(state, _outage("DC-001", 1, 52))
    assert demand_fingerprint(capacity_only) == baseline


def test_cached_what_if_is_served_fast_and_says_so(state):
    clear_caches()
    perturbation = _outage("DC-001", 1, 52)
    first = run_what_if(perturbation, state=state, use_cache=True)
    second = run_what_if(perturbation, state=state, use_cache=True)

    assert first.cached is False
    assert second.cached is True
    assert second.timing["served_from_cache"] is True
    # The DoD's budget for a cached what-if.
    assert second.timing["total_seconds"] < 1.0
    # The numbers themselves must be the same, and the original measurement kept.
    assert second.base == first.base
    assert second.what_if == first.what_if
    assert second.timing["originally_measured_total_seconds"] == first.timing["total_seconds"]


def test_stripping_a_whole_lane_type_is_warned_about(state):
    """Exercised on a crafted state: no shipped scenario can trigger it.

    Checked explicitly — on all four scenarios there is no single node whose
    outage removes every unit of capacity for a lane type, so this branch is
    tested here rather than demonstrable on the demo data.
    """
    from src.chat.perturbation import analyse

    # Leave DC-001's inbound plant_to_dc lanes as the only ones with capacity at
    # the read period, so zeroing DC-001 removes the lot.
    read_period = capacity_read_period(state)
    dc1_lanes = set(
        state.lanes.filter(
            (pl.col("lane_type") == "plant_to_dc")
            & ((pl.col("from_node_id") == "DC-001") | (pl.col("to_node_id") == "DC-001"))
        )
        .select("lane_id")
        .to_series()
        .to_list()
    )
    other_plant_lanes = set(
        state.lanes.filter(pl.col("lane_type") == "plant_to_dc").select("lane_id").to_series().to_list()
    ) - dc1_lanes
    crafted = replace(
        state,
        lane_periods=state.lane_periods.with_columns(
            pl.when(pl.col("lane_id").is_in(list(other_plant_lanes)))
            .then(pl.lit(0))
            .otherwise(pl.col("effective_capacity_units"))
            .alias("effective_capacity_units")
        ),
    )
    impact = analyse(_outage("DC-001", 1, read_period), crafted)
    assert "plant_to_dc" in impact.removes_all_capacity_for

    result = run_what_if(_outage("DC-001", 1, read_period), state=crafted, use_cache=False)
    assert any("every unit of capacity" in warning for warning in result.warnings)


def test_cache_distinguishes_different_perturbations(state):
    clear_caches()
    near = run_what_if(_outage("DC-001", 1, 52), state=state)
    far = run_what_if(_outage("DC-002", 1, 52), state=state)
    assert near.fingerprint != far.fingerprint
    assert far.cached is False


def test_cache_is_bounded(state):
    clear_caches()
    for period in range(1, 40):
        run_what_if(_outage("DC-001", period, 52), state=state, use_cache=True)
    assert len(RESULT_CACHE._store) <= RESULT_CACHE.limit
    assert len(FORECAST_CACHE._store) <= FORECAST_CACHE.limit


# --------------------------------------------------------------- the payload


def test_payload_carries_everything_a_reader_needs(state):
    result = run_what_if(_outage("DC-001", 1, 52), state=state, use_cache=False).as_dict()
    assert result["is_what_if"] is True
    assert result["label"] == "BETA" and result["beta"] is True
    assert result["seed"] == 12345
    assert result["horizon"] == 8
    assert result["ppo_included"] is False
    for metric in ("objective", "total_cost", "fill_rate", "days_of_inventory", "cvar_75"):
        delta = result["deltas"][metric]
        assert {"before", "after", "absolute", "percent"} <= set(delta)
    assert result["what_if"]["cvar_75"] is not None and result["base"]["cvar_75"] is not None
    assert result["diff"]["table"] == "lane_periods"
    assert result["perturbation"]["node_id"] == "DC-001"
    assert result["timing"]["total_seconds"] > 0
    assert "synthetic perturbation" in " ".join(result["warnings"])
    assert "applied exactly as asked" in result["period_semantics"]
    assert "run_head_to_head" in result["numeric_values_source"]


def test_ppo_exclusion_is_stated_and_symmetric(state):
    result = run_what_if(_outage("DC-001", 1, 52), state=state, include_ppo=False, use_cache=False)
    assert result.ppo_included is False
    assert result.base["ppo_outcome"] == "not_evaluated"
    assert result.what_if["ppo_outcome"] == "not_evaluated"
    assert "ppo" not in result.base["by_approach"]
    assert "ppo" not in result.what_if["by_approach"]
    assert any("PPO was not run" in warning for warning in result.warnings)


def test_ppo_can_be_opted_in(state):
    result = run_what_if(
        _outage("DC-001", 1, 52), state=state, include_ppo=True, ppo_timesteps=16, use_cache=False
    )
    assert result.ppo_included is True
    assert "ppo" in result.base["by_approach"]
    assert "ppo" in result.what_if["by_approach"]
    assert result.base["ppo_outcome"] != "not_evaluated"


def test_invalid_perturbation_is_refused_before_any_run(state):
    with pytest.raises(PerturbationError):
        run_what_if(_outage("DC-404", 1, 52), state=state, use_cache=False)
    with pytest.raises(PerturbationError):
        run_what_if(_outage("DC-001", 1, 999), state=state, use_cache=False)


def test_confirmation_card_describes_a_runnable_perturbation(state):
    card = confirmation_for(_outage("DC-001", 1, 52), state=state)
    assert card["requires_confirmation"] is True
    assert card["runnable"] is True
    assert "confirmed=true" in card["how_to_run"]


# --------------------------------------------- run_head_to_head compatibility


def test_run_head_to_head_defaults_are_unchanged():
    """Every new keyword is additive: the default path still writes 3 approaches."""
    from src.pipeline.bench import run_head_to_head

    result = run_head_to_head(SCENARIO, horizon=8, ppo_timesteps=16)
    assert {row["approach"] for row in result["comparison"]} == {"baseline", "classical", "ppo"}
    assert set(result["plans"]) == {"baseline", "classical", "ppo"}
    assert result["ppo_outcome"].startswith(("lost_to_", "won"))
    assert result["artifacts"]["comparison_path"]
    # The classical objective is independent of the PPO budget, so it must still
    # be the recorded one even with a tiny PPO run.
    classical = next(row for row in result["comparison"] if row["approach"] == "classical")
    assert classical["objective"] == pytest.approx(RECORDED_CLASSICAL_OBJECTIVE[SCENARIO], abs=1e-6)


def test_preloaded_state_and_forecast_give_the_same_answer(state):
    from src.forecast.statistical import forecast_finished_goods
    from src.pipeline.bench import run_head_to_head

    forecast = forecast_finished_goods(state, horizon=8)
    injected = run_head_to_head(
        SCENARIO, horizon=8, state=state, forecast=forecast, include_ppo=False, write_artifact=False
    )
    loaded = run_head_to_head(SCENARIO, horizon=8, include_ppo=False, write_artifact=False)
    assert injected["winner"]["objective"] == loaded["winner"]["objective"]


# ----------------------------------------------------------------- API surface


def test_whatif_endpoint_requires_the_api_key(api_client):
    response = api_client.post(
        "/chat/whatif",
        json={
            "scenario": SCENARIO,
            "perturbation": {"kind": "node_outage", "node_id": "DC-001", "from_period": 1, "to_period": 52},
        },
    )
    assert response.status_code == 401


def test_whatif_endpoint_will_not_run_without_confirmation(api_client, api_headers):
    response = api_client.post(
        "/chat/whatif",
        json={
            "scenario": SCENARIO,
            "perturbation": {"kind": "node_outage", "node_id": "DC-001", "from_period": 1, "to_period": 52},
            "confirmed": False,
        },
        headers=api_headers,
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["executed"] is False
    assert payload["reason"] == "confirmation_required"
    assert payload["confirmation"]["requires_confirmation"] is True
    assert "base" not in payload and "deltas" not in payload


def test_whatif_endpoint_runs_when_confirmed(api_client, api_headers):
    response = api_client.post(
        "/chat/whatif",
        json={
            "scenario": SCENARIO,
            "perturbation": {"kind": "node_outage", "node_id": "DC-001", "from_period": 1, "to_period": 52},
            "confirmed": True,
        },
        headers=api_headers,
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["executed"] is True
    assert payload["is_what_if"] is True
    assert payload["base"]["objective"] == pytest.approx(RECORDED_CLASSICAL_OBJECTIVE[SCENARIO], abs=1e-6)
    assert payload["moved_the_plan"] is True


def test_whatif_endpoint_revalidates_the_client_payload(api_client, api_headers):
    """A client-supplied perturbation is never trusted."""
    response = api_client.post(
        "/chat/whatif",
        json={
            "scenario": SCENARIO,
            "perturbation": {"kind": "node_outage", "node_id": "DC-404", "from_period": 1, "to_period": 52},
            "confirmed": True,
        },
        headers=api_headers,
    )
    assert response.status_code == 422
    assert "DC-404" in response.json()["detail"]


def test_whatif_endpoint_rejects_an_out_of_whitelist_kind(api_client, api_headers):
    response = api_client.post(
        "/chat/whatif",
        json={
            "scenario": SCENARIO,
            "perturbation": {"kind": "lead_time_inflation", "from_period": 1, "to_period": 5},
            "confirmed": True,
        },
        headers=api_headers,
    )
    assert response.status_code == 422


def test_whatif_stream_emits_truthful_stages_then_the_result(api_client, api_headers):
    with api_client.stream(
        "GET",
        "/chat/whatif/stream",
        params={
            # A perturbation no other test uses, so this exercises a fresh run
            # rather than the api process's result cache.
            "scenario": SCENARIO,
            "kind": "lane_disruption",
            "lane_id": "LANE-0007",
            "capacity_multiplier": 0.25,
            "from_period": 1,
            "to_period": 52,
            "confirmed": True,
            # The api process outlives any single pytest run, so this test asks
            # for a fresh computation rather than depending on a cold cache.
            "fresh": True,
        },
        headers=api_headers,
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    events = [line.split(": ", 1)[1] for line in body.splitlines() if line.startswith("event: ")]
    assert events[-1] == "done"
    # Every stage must appear as running before complete, in order.
    stages = [line for line in body.splitlines() if line.startswith("data: ") and '"stage"' in line]
    assert any('"base_optimize"' in line and '"running"' in line for line in stages)
    assert any('"whatif_optimize"' in line and '"complete"' in line for line in stages)
    running = next(i for i, line in enumerate(stages) if '"whatif_optimize"' in line and '"running"' in line)
    complete = next(i for i, line in enumerate(stages) if '"whatif_optimize"' in line and '"complete"' in line)
    assert running < complete


def test_whatif_stream_reports_a_cache_hit_instead_of_going_silent(api_client, api_headers):
    """A cached result must still tell the client why it was instant."""
    params = {
        "scenario": SCENARIO,
        "kind": "lane_disruption",
        "lane_id": "LANE-0009",
        "capacity_multiplier": 0.5,
        "from_period": 1,
        "to_period": 52,
        "confirmed": True,
    }
    for _ in range(2):
        with api_client.stream("GET", "/chat/whatif/stream", params=params, headers=api_headers) as response:
            body = "".join(response.iter_text())
    assert '"stage": "cache"' in body and '"status": "hit"' in body
    assert "event: done" in body


def test_whatif_stream_asks_for_confirmation_when_not_given(api_client, api_headers):
    with api_client.stream(
        "GET",
        "/chat/whatif/stream",
        params={
            "scenario": SCENARIO,
            "kind": "node_outage",
            "node_id": "DC-001",
            "from_period": 1,
            "to_period": 52,
        },
        headers=api_headers,
    ) as response:
        body = "".join(response.iter_text())
    assert "event: confirm" in body
    assert "event: done" not in body


# ------------------------------------------------------------------ the CLIs

# These exist because a Phase 3 field rename silently broke `make chat-parse`
# (KeyError on every successful parse) and nothing caught it: the CLIs had no
# coverage at all. A smoke test per entry point is cheap and would have.


@pytest.mark.parametrize(
    "module,args",
    [
        ("src.chat.ask", ["--scenario", SCENARIO, "--question", "How many suppliers are there?", "--no-llm"]),
        ("src.chat.parse", ["--scenario", SCENARIO, "--question", "What if DC-001 goes down?", "--no-llm"]),
        ("src.chat.parse", ["--scenario", SCENARIO, "--question", "What if demand spikes?", "--no-llm"]),
        ("src.chat.parse", ["--scenario", SCENARIO, "--question", "What if warehouse 9 fails?", "--no-llm"]),
        ("src.chat.run_whatif", ["--scenario", SCENARIO, "--question", "What if DC-001 goes down?", "--no-llm"]),
        (
            "src.chat.run_whatif",
            ["--scenario", SCENARIO, "--question", "What if DC-001 goes down?", "--no-llm", "--confirm"],
        ),
    ],
)
def test_cli_entry_points_run_cleanly(module, args):
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", module, *args],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        timeout=300,
    )
    assert result.returncode == 0, f"{module} {args} failed:\n{result.stderr[-1500:]}"
    assert result.stdout.strip()
    assert "Traceback" not in result.stderr
