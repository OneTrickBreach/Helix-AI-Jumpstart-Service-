"""Run a validated perturbation through the real pipeline.

Three properties this module is built around, in order of how much they matter:

**1. It cannot mutate the dataset.** The perturbation is applied as an in-memory
overlay: a new ``ScenarioState`` whose frames are replacements, built with
``dataclasses.replace``. Nothing is copied to disk and nothing is written back, so
"the on-disk files are byte-identical after a what-if run" is true by
construction rather than by discipline. A test asserts it anyway.

**2. Base and what-if are computed the same way.** The base side is re-run here
rather than read from the recorded artifact, because that artifact may have been
produced at a different horizon or PPO budget, and comparing across settings
would be a dishonest before/after. Same seed, same objective, same CVaR-75, same
code path — the only difference is the overlay.

**3. It says when a perturbation could not have changed anything.** Verified in
Phase 2: lane capacity reaches the optimizer at exactly one period
(``state.horizon()``). A window that misses it is a measured no-op, so the result
reports *why* the numbers did not move instead of implying the network shrugged
off the disruption.

The period range is applied **faithfully** — exactly what the planner asked for,
never silently widened to make a demo look better. See ``PERIOD_SEMANTICS``.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable

import polars as pl

from src.chat.perturbation import (
    Impact,
    Perturbation,
    analyse,
    build_confirmation_card,
    capacity_read_period,
    lanes_touching,
    plain_english,
    validate,
)
from src.forecast.statistical import forecast_finished_goods
from src.ingest.state import ScenarioState, load_scenario_state
from src.pipeline.bench import run_head_to_head


# The decision recorded in the result payload and surfaced in the UI, so nobody
# has to reconstruct it from the code later.
PERIOD_SEMANTICS = (
    "The period range is applied exactly as asked. On this dataset the optimizer reads lane capacity at "
    "one period only, so a capacity window that excludes it genuinely changes nothing — reported as a "
    "no-op with the reason, never widened silently to manufacture a difference."
)

DEFAULT_HORIZON = 8
DEFAULT_PPO_TIMESTEPS = 128

# Compared with math.isclose-style tolerance rather than ==, because these are
# rounded floats coming back from two separate optimizer runs.
OBJECTIVE_EPSILON = 1e-6


@dataclass
class WhatIfResult:
    scenario: str
    perturbation: dict[str, Any]
    base: dict[str, Any]
    what_if: dict[str, Any]
    deltas: dict[str, Any]
    impact: dict[str, Any]
    diff: dict[str, Any]
    timing: dict[str, Any]
    seed: int
    horizon: int
    ppo_included: bool
    moved_the_plan: bool
    explanation: str
    reading: str
    fingerprint: str
    cached: bool = False
    is_what_if: bool = True
    beta: bool = True
    label: str = "BETA"
    numeric_values_source: str = "src.pipeline.bench.run_head_to_head on a perturbed in-memory copy"
    period_semantics: str = PERIOD_SEMANTICS
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "is_what_if": self.is_what_if,
            "scenario": self.scenario,
            "perturbation": self.perturbation,
            "reading": self.reading,
            "fingerprint": self.fingerprint,
            "seed": self.seed,
            "horizon": self.horizon,
            "ppo_included": self.ppo_included,
            "base": self.base,
            "what_if": self.what_if,
            "deltas": self.deltas,
            "impact": self.impact,
            "diff": self.diff,
            "moved_the_plan": self.moved_the_plan,
            "explanation": self.explanation,
            "warnings": self.warnings,
            "timing": self.timing,
            "cached": self.cached,
            "beta": self.beta,
            "label": self.label,
            "numeric_values_source": self.numeric_values_source,
            "period_semantics": self.period_semantics,
        }


# ---------------------------------------------------------------------------
# the overlay
# ---------------------------------------------------------------------------


def _scaled_int(column: str, multiplier: float) -> pl.Expr:
    """Scale an integer column and keep it an integer.

    Both perturbed columns (``effective_capacity_units``, ``quantity_units``) are
    Int64 in the generated data and represent whole units. Rounding back to Int64
    preserves the schema the optimizer reads, and makes a multiplier of exactly
    1.0 an exact identity — which is what the fairness invariant needs.
    """
    return (pl.col(column) * multiplier).round(0).cast(pl.Int64)


def apply_perturbation(state: ScenarioState, perturbation: Perturbation) -> tuple[ScenarioState, dict[str, Any]]:
    """A new state with the overlay applied, plus a diff of what changed.

    The returned state shares every untouched frame with the original; only the
    perturbed frame is replaced. Nothing is written to disk.
    """
    window = pl.col("period").is_between(perturbation.from_period, perturbation.to_period)

    if perturbation.kind in {"node_outage", "lane_disruption"}:
        if perturbation.kind == "node_outage":
            lane_ids = lanes_touching(state, str(perturbation.node_id)).select("lane_id").to_series().to_list()
            multiplier = 0.0
        else:
            lane_ids = [str(perturbation.lane_id)]
            multiplier = float(perturbation.capacity_multiplier or 0.0)

        target = pl.col("lane_id").is_in(lane_ids) & window
        before = state.lane_periods.filter(target)
        perturbed = state.lane_periods.with_columns(
            pl.when(target)
            .then(_scaled_int("effective_capacity_units", multiplier))
            .otherwise(pl.col("effective_capacity_units"))
            .alias("effective_capacity_units")
        )
        after = perturbed.filter(target)
        diff = {
            "table": "lane_periods",
            "column": "effective_capacity_units",
            "capacity_multiplier_applied": multiplier,
            "lane_ids": lane_ids,
            "rows_changed": int(
                before.join(after, on=["lane_id", "period"], how="inner", suffix="_after")
                .filter(pl.col("effective_capacity_units") != pl.col("effective_capacity_units_after"))
                .height
            ),
            "rows_in_window": before.height,
            "units_before": int(before.select(pl.sum("effective_capacity_units")).item() or 0),
            "units_after": int(after.select(pl.sum("effective_capacity_units")).item() or 0),
        }
        return replace(state, lane_periods=perturbed), diff

    # demand_multiplier
    multiplier = float(perturbation.demand_multiplier if perturbation.demand_multiplier is not None else 1.0)
    target = window
    if perturbation.scope == "customer":
        target = target & (pl.col("node_id") == perturbation.scope_id)
    elif perturbation.scope == "sku":
        target = target & (pl.col("sku_id") == perturbation.scope_id)

    before = state.demand.filter(target)
    perturbed = state.demand.with_columns(
        pl.when(target)
        .then(_scaled_int("quantity_units", multiplier))
        .otherwise(pl.col("quantity_units"))
        .alias("quantity_units")
    )
    after = perturbed.filter(target)
    diff = {
        "table": "demand",
        "column": "quantity_units",
        "demand_multiplier_applied": multiplier,
        "scope": perturbation.scope or "all",
        "scope_id": perturbation.scope_id,
        "rows_in_window": before.height,
        "rows_changed": int(
            before.join(
                after,
                on=["period", "demand_type", "node_id", "sku_id"],
                how="inner",
                suffix="_after",
            )
            .filter(pl.col("quantity_units") != pl.col("quantity_units_after"))
            .height
        ),
        "units_before": int(before.select(pl.sum("quantity_units")).item() or 0),
        "units_after": int(after.select(pl.sum("quantity_units")).item() or 0),
    }
    return replace(state, demand=perturbed), diff


# ---------------------------------------------------------------------------
# caches
# ---------------------------------------------------------------------------


def demand_fingerprint(state: ScenarioState) -> str:
    """Content hash of the demand a forecast would be fitted to.

    Only the columns the forecaster actually reads, so an unrelated change cannot
    invalidate the cache and a relevant one always does.
    """
    # Only the finished-good customer rows, because `forecast_finished_goods`
    # filters to exactly those. Including derived-component rows made an
    # RC-scoped demand change invalidate a forecast it could not affect, refitting
    # every series for nothing.
    frame = (
        state.demand.filter(pl.col("demand_type") == "finished_good_customer")
        .select("period", "node_id", "sku_id", "quantity_units")
        .sort(["node_id", "sku_id", "period"])
    )
    digest = hashlib.sha256()
    for value in frame.hash_rows().to_list():
        digest.update(int(value).to_bytes(8, "little", signed=False))
    return digest.hexdigest()[:32]


class _Cache:
    """Small process-local caches. Bounded so a long demo cannot grow unbounded."""

    def __init__(self, limit: int = 32) -> None:
        self.limit = limit
        self._store: dict[str, Any] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        value = self._store.get(key)
        if value is None:
            self.misses += 1
        else:
            self.hits += 1
        return value

    def put(self, key: str, value: Any) -> None:
        if len(self._store) >= self.limit:
            self._store.pop(next(iter(self._store)))
        self._store[key] = value

    def clear(self) -> None:
        self._store.clear()
        self.hits = 0
        self.misses = 0


FORECAST_CACHE = _Cache(limit=8)
RESULT_CACHE = _Cache(limit=32)


def cached_forecast(state: ScenarioState, horizon: int) -> tuple[dict, bool]:
    """The forecast for this state, reusing an identical earlier one.

    Keyed on (scenario, horizon, demand fingerprint), so a capacity perturbation —
    which leaves demand untouched — reuses the base forecast, and a demand
    perturbation cannot.
    """
    key = f"{state.scenario}|{horizon}|{demand_fingerprint(state)}"
    hit = FORECAST_CACHE.get(key)
    if hit is not None:
        return hit, True
    forecast = forecast_finished_goods(state, horizon=horizon)
    FORECAST_CACHE.put(key, forecast)
    return forecast, False


def clear_caches() -> None:
    FORECAST_CACHE.clear()
    RESULT_CACHE.clear()


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------


def _metrics_of(result: dict[str, Any]) -> dict[str, Any]:
    rows = {row["approach"]: row for row in result["comparison"]}
    winner = result["winner"]["approach"]
    return {
        "winner": winner,
        "ppo_outcome": result["ppo_outcome"],
        "objective": rows[winner]["objective"],
        "total_cost": rows[winner]["total_cost"],
        "fill_rate": rows[winner]["fill_rate"],
        "days_of_inventory": rows[winner]["days_of_inventory"],
        "cvar_75": rows[winner]["cvar_75"],
        "by_approach": {
            approach: {
                "objective": row["objective"],
                "total_cost": row["total_cost"],
                "fill_rate": row["fill_rate"],
                "days_of_inventory": row["days_of_inventory"],
                "cvar_75": row["cvar_75"],
                "latency_seconds": row["latency_seconds"],
            }
            for approach, row in rows.items()
        },
        "cost_breakdown": result["plans"][winner]["metrics"].get("cost_breakdown", {}),
        "policy": result["plans"][winner].get("policy", {}),
    }


def _delta(before: float | None, after: float | None) -> dict[str, Any]:
    if before is None or after is None:
        return {"before": before, "after": after, "absolute": None, "percent": None}
    absolute = after - before
    percent = (absolute / before) if before else None
    return {
        "before": round(float(before), 6),
        "after": round(float(after), 6),
        "absolute": round(float(absolute), 6),
        "percent": round(float(percent), 6) if percent is not None else None,
    }


def _explain(perturbation: Perturbation, impact: Impact, deltas: dict[str, Any], moved: bool, diff: dict) -> str:
    objective = deltas["objective"]
    if moved:
        direction = "worse" if (objective["absolute"] or 0) > 0 else "better"
        return (
            f"The plan changed: the objective moved from {objective['before']:,.2f} to "
            f"{objective['after']:,.2f}, {abs(objective['absolute']):,.2f} {direction} "
            f"({abs(objective['percent'] or 0) * 100:.2f}%). Tail risk (CVaR-75) went from "
            f"{deltas['cvar_75']['before']:,.2f} to {deltas['cvar_75']['after']:,.2f}."
        )
    if not impact.reaches_optimizer:
        return (
            "Nothing changed, and not because the network absorbed it: " + impact.why + " "
            "The perturbation was applied exactly as asked; it simply does not touch anything this "
            "optimizer reads."
        )
    if diff.get("rows_changed", 0) == 0:
        return (
            "Nothing changed because the perturbation altered no values — the multiplier left every "
            "affected row exactly as it was."
        )
    return (
        f"The perturbation changed {diff.get('rows_changed', 0):,} rows of "
        f"{diff.get('table')}, but the resulting plan and objective are identical. On this network the "
        "optimizer had enough alternative capacity to absorb it without changing its decisions."
    )


def run_what_if(
    perturbation: Perturbation,
    state: ScenarioState | None = None,
    horizon: int = DEFAULT_HORIZON,
    include_ppo: bool = False,
    ppo_timesteps: int = DEFAULT_PPO_TIMESTEPS,
    progress_callback: Callable[[str, str], None] | None = None,
    use_cache: bool = True,
    data_root: Any = None,
) -> WhatIfResult:
    """Run one validated perturbation and report before/after against the same code path."""
    if state is None:
        state = (
            load_scenario_state(perturbation.scenario)
            if data_root is None
            else load_scenario_state(perturbation.scenario, data_root=data_root)
        )
    perturbation = validate(perturbation, state)

    def notify(stage: str, status: str) -> None:
        if progress_callback is not None:
            progress_callback(stage, status)

    started = time.perf_counter()
    cache_key = f"{perturbation.fingerprint()}|{horizon}|{include_ppo}|{ppo_timesteps}"
    if use_cache:
        cached = RESULT_CACHE.get(cache_key)
        if cached is not None:
            notify("cache", "hit")
            # Report the cache-hit cost as what it is, and keep the originally
            # measured run time rather than presenting a cache read as the
            # latency of an optimizer run.
            return replace(
                cached,
                cached=True,
                timing={
                    **cached.timing,
                    "total_seconds": round(time.perf_counter() - started, 4),
                    "originally_measured_total_seconds": cached.timing.get("total_seconds"),
                    "served_from_cache": True,
                },
            )

    impact = analyse(perturbation, state)

    notify("base_forecast", "running")
    base_forecast, base_forecast_cached = cached_forecast(state, horizon)
    notify("base_forecast", "complete")

    notify("base_optimize", "running")
    base_started = time.perf_counter()
    base_result = run_head_to_head(
        perturbation.scenario,
        horizon=horizon,
        ppo_timesteps=ppo_timesteps,
        state=state,
        forecast=base_forecast,
        include_ppo=include_ppo,
        # Never overwrite the recorded base run: that file is what the demo and
        # the chat layer read as *the* result.
        write_artifact=False,
    )
    base_seconds = time.perf_counter() - base_started
    notify("base_optimize", "complete")

    notify("perturb", "running")
    perturbed_state, diff = apply_perturbation(state, perturbation)
    notify("perturb", "complete")

    notify("whatif_forecast", "running")
    what_if_forecast, what_if_forecast_cached = cached_forecast(perturbed_state, horizon)
    notify("whatif_forecast", "complete")

    notify("whatif_optimize", "running")
    what_if_started = time.perf_counter()
    what_if_result = run_head_to_head(
        perturbation.scenario,
        horizon=horizon,
        ppo_timesteps=ppo_timesteps,
        state=perturbed_state,
        forecast=what_if_forecast,
        include_ppo=include_ppo,
        write_artifact=False,
    )
    what_if_seconds = time.perf_counter() - what_if_started
    notify("whatif_optimize", "complete")

    base_metrics = _metrics_of(base_result)
    what_if_metrics = _metrics_of(what_if_result)
    deltas = {
        metric: _delta(base_metrics[metric], what_if_metrics[metric])
        for metric in ("objective", "total_cost", "fill_rate", "days_of_inventory", "cvar_75")
    }
    moved = abs(what_if_metrics["objective"] - base_metrics["objective"]) > OBJECTIVE_EPSILON

    warnings: list[str] = []
    if not impact.reaches_optimizer:
        warnings.append(impact.why)
    if impact.removes_all_capacity_for:
        warnings.append(
            "This removed every unit of capacity for "
            + ", ".join(impact.removes_all_capacity_for)
            + f" at period {impact.capacity_read_period}."
        )
    if not include_ppo:
        warnings.append(
            "PPO was not run for this what-if. It is evaluated-not-shipped and adds tens of seconds; "
            "both sides of this comparison exclude it, so they remain like-for-like."
        )
    warnings.append(
        "This is a synthetic perturbation of seeded demo data, not a forecast of a real network."
    )

    result = WhatIfResult(
        scenario=perturbation.scenario,
        perturbation=perturbation.as_dict(),
        base=base_metrics,
        what_if=what_if_metrics,
        deltas=deltas,
        impact=impact.as_dict(),
        diff=diff,
        timing={
            "total_seconds": round(time.perf_counter() - started, 3),
            "base_optimize_seconds": round(base_seconds, 3),
            "whatif_optimize_seconds": round(what_if_seconds, 3),
            "base_forecast_cached": base_forecast_cached,
            "whatif_forecast_cached": what_if_forecast_cached,
            "forecast_cache_hits": FORECAST_CACHE.hits,
            "forecast_cache_misses": FORECAST_CACHE.misses,
        },
        seed=perturbation.seed,
        horizon=horizon,
        ppo_included=include_ppo,
        moved_the_plan=moved,
        explanation=_explain(perturbation, impact, deltas, moved, diff),
        reading=plain_english(perturbation, state, impact),
        fingerprint=perturbation.fingerprint(),
        warnings=warnings,
    )
    if use_cache:
        RESULT_CACHE.put(cache_key, result)
    return result


def confirmation_for(
    perturbation: Perturbation,
    state: ScenarioState | None = None,
    recorded_latencies: dict[str, float] | None = None,
    data_root: Any = None,
) -> dict[str, Any]:
    """The card an unconfirmed run gets back instead of burning compute."""
    if state is None:
        state = (
            load_scenario_state(perturbation.scenario)
            if data_root is None
            else load_scenario_state(perturbation.scenario, data_root=data_root)
        )
    perturbation = validate(perturbation, state)
    impact = analyse(perturbation, state, recorded_latencies)
    return build_confirmation_card(perturbation, state, impact)


__all__ = [
    "PERIOD_SEMANTICS",
    "WhatIfResult",
    "apply_perturbation",
    "cached_forecast",
    "clear_caches",
    "confirmation_for",
    "demand_fingerprint",
    "run_what_if",
]
