"""The perturbation whitelist: schema, validation, and reachability analysis.

Three kinds ship at launch (Iteration 5 decision 5). Everything else is refused
rather than approximated.

    node_outage        a location cannot ship or receive
    lane_disruption    one lane's capacity is scaled
    demand_multiplier  demand is scaled for all / one customer / one product

🔴 **The measured fact that shapes this whole module.** Iteration 5 Phase 2
verified on-device how a capacity change actually reaches the optimizer, and it
is narrower than the plan of action assumed. ``select_ortools_lanes`` and
``select_greedy_lanes`` both do:

    latest_period = state.horizon()                       # = max(demand.period)
    periods = state.lane_periods.filter(pl.col("period") == latest_period)

so lane capacity is read at **exactly one period** — 52 on the three small
scenarios, 104 on ``stress-large``. Measured consequences, on a copy of the real
data (base objective 104,141.524105 on ``component-shortage-shock``):

    zero 7 lanes touching PLANT-001 at periods 3-6     -> 104,141.524105  NO-OP
    zero the same lanes at periods 18-27               -> 104,141.524105  NO-OP
    zero the same lanes at period 52                   -> 105,039.331144  MOVED
    zero DC-004's 28 lanes on stress-large at 3-6      -> unchanged       NO-OP
    ...the same at period 104                          -> moved           MOVED

A demand change, by contrast, reaches the optimizer from any period, because the
whole history feeds the forecast (x2 on periods 3-6 alone moved the objective).

This is a **third** silent no-op alongside the two Iteration 4 found (no stock at
DCs; ``nodes.csv`` never read downstream). So every parse carries a reachability
verdict, computed from the state rather than hardcoded, and a perturbation that
cannot move the plan says so **before** any GPU time is spent on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import polars as pl

from src.ingest.state import ScenarioState


WHITELIST = ("node_outage", "lane_disruption", "demand_multiplier")

# Deferred to a later phase / to Ryan's call on which earns its place first.
DEFERRED_KINDS = (
    "supplier_zeroing",
    "lead_time_inflation",
    "capacity_cut",
    "cost_shock",
    "service_target_change",
)

MAX_MULTIPLIER = 10.0

# Forecast cost per series, from the Iteration 3 Phase 5 scale study (~25 ms per
# series, measured across six scale levels). Used only to estimate runtime for
# the confirm card; Phase 3 will record real elapsed times.
FORECAST_MS_PER_SERIES = 25.0


class PerturbationError(ValueError):
    """The request is well-formed English but not a legal perturbation."""


@dataclass(frozen=True)
class Perturbation:
    """One validated, executable-shaped perturbation. Phase 2 does not run it."""

    kind: str
    scenario: str
    from_period: int
    to_period: int
    node_id: str | None = None
    lane_id: str | None = None
    capacity_multiplier: float | None = None
    demand_multiplier: float | None = None
    scope: str | None = None          # all | customer | sku
    scope_id: str | None = None
    seed: int = 12345

    def as_dict(self) -> dict[str, Any]:
        return {key: value for key, value in self.__dict__.items() if value is not None}

    def fingerprint(self) -> str:
        """Stable identity of this perturbation, for Phase 3's result cache."""
        parts = [
            self.kind,
            self.scenario,
            str(self.from_period),
            str(self.to_period),
            self.node_id or "-",
            self.lane_id or "-",
            f"{self.capacity_multiplier:.6f}" if self.capacity_multiplier is not None else "-",
            f"{self.demand_multiplier:.6f}" if self.demand_multiplier is not None else "-",
            self.scope or "-",
            self.scope_id or "-",
            str(self.seed),
        ]
        return "|".join(parts)


@dataclass
class Impact:
    """What the perturbation touches, and whether it can change the plan at all."""

    reaches_optimizer: bool
    why: str
    lanes_affected: list[str] = field(default_factory=list)
    lane_types_affected: dict[str, int] = field(default_factory=dict)
    series_affected: int = 0
    series_by_demand_type: dict[str, int] = field(default_factory=dict)
    demand_rows_affected: int = 0
    capacity_read_period: int | None = None
    removes_all_capacity_for: list[str] = field(default_factory=list)
    estimated_seconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "reaches_optimizer": self.reaches_optimizer,
            "why": self.why,
            "lanes_affected": self.lanes_affected,
            "lanes_affected_count": len(self.lanes_affected),
            "lane_types_affected": self.lane_types_affected,
            "series_affected": self.series_affected,
            "series_by_demand_type": self.series_by_demand_type,
            "demand_rows_affected": self.demand_rows_affected,
            "capacity_read_period": self.capacity_read_period,
            "removes_all_capacity_for": self.removes_all_capacity_for,
            "estimated_seconds": round(self.estimated_seconds, 1),
        }


DEMAND_TYPE_LABELS = {
    "finished_good_customer": "finished-good customer",
    "derived_component": "derived-component",
}


def _series_breakdown(by_type: dict[str, int]) -> str:
    if not by_type:
        return "no series"
    return " plus ".join(
        f"{count} {DEMAND_TYPE_LABELS.get(name, name.replace('_', ' '))}"
        for name, count in sorted(by_type.items())
    )


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def max_period(state: ScenarioState) -> int:
    return int(state.lane_periods.select(pl.max("period")).item())


def capacity_read_period(state: ScenarioState) -> int:
    """The single period at which the optimizer reads lane capacity.

    Deliberately calls ``state.horizon()`` — the same expression
    ``select_ortools_lanes`` uses — rather than restating 52 or 104, so this stays
    correct if the optimizer's period handling ever changes.
    """
    return int(state.horizon())


def validate(perturbation: Perturbation, state: ScenarioState) -> Perturbation:
    """Raise ``PerturbationError`` unless every field is legal for this scenario."""
    if perturbation.kind not in WHITELIST:
        raise PerturbationError(
            f"'{perturbation.kind}' is not one of the perturbations I can model "
            f"({', '.join(WHITELIST)})."
        )

    limit = max_period(state)
    for name, value in (("from_period", perturbation.from_period), ("to_period", perturbation.to_period)):
        if not isinstance(value, int) or isinstance(value, bool):
            raise PerturbationError(f"{name} must be a whole number of periods.")
        if value < 1 or value > limit:
            raise PerturbationError(
                f"{name} must be between 1 and {limit} — this scenario has {limit} periods of data."
            )
    if perturbation.from_period > perturbation.to_period:
        raise PerturbationError("The period range runs backwards: from_period is after to_period.")

    if perturbation.kind == "node_outage":
        if not perturbation.node_id:
            raise PerturbationError("A node outage needs a location.")
        known = set(state.nodes.select("node_id").to_series().to_list())
        if perturbation.node_id not in known:
            raise PerturbationError(f"There is no {perturbation.node_id} in the {perturbation.scenario} scenario.")

    elif perturbation.kind == "lane_disruption":
        if not perturbation.lane_id:
            raise PerturbationError("A lane disruption needs a lane.")
        known = set(state.lanes.select("lane_id").to_series().to_list())
        if perturbation.lane_id not in known:
            raise PerturbationError(f"There is no {perturbation.lane_id} in the {perturbation.scenario} scenario.")
        multiplier = perturbation.capacity_multiplier
        if multiplier is None:
            raise PerturbationError("A lane disruption needs a capacity multiplier.")
        if multiplier < 0.0 or multiplier > MAX_MULTIPLIER:
            raise PerturbationError(f"A capacity multiplier must be between 0 and {MAX_MULTIPLIER:g}.")

    elif perturbation.kind == "demand_multiplier":
        multiplier = perturbation.demand_multiplier
        if multiplier is None:
            raise PerturbationError("A demand change needs a multiplier.")
        if multiplier < 0.0 or multiplier > MAX_MULTIPLIER:
            raise PerturbationError(f"A demand multiplier must be between 0 and {MAX_MULTIPLIER:g}.")
        scope = perturbation.scope or "all"
        if scope not in {"all", "customer", "sku"}:
            raise PerturbationError("A demand change applies to all demand, one customer, or one product.")
        if scope != "all":
            if not perturbation.scope_id:
                raise PerturbationError(f"A {scope}-scoped demand change needs to say which {scope}.")
            column = "node_id" if scope == "customer" else "sku_id"
            known = set(state.demand.select(column).unique().to_series().to_list())
            if perturbation.scope_id not in known:
                raise PerturbationError(
                    f"There is no demand recorded for {perturbation.scope_id} in the "
                    f"{perturbation.scenario} scenario."
                )

    return perturbation


# ---------------------------------------------------------------------------
# reachability + impact
# ---------------------------------------------------------------------------


def lanes_touching(state: ScenarioState, node_id: str) -> pl.DataFrame:
    """Every lane with the node at either end.

    This is the whole mechanism behind ``node_outage``: the optimizer never reads
    ``nodes.csv`` (Iteration 4 §1.3) and there is no stock at a DC to zero
    (§1.2), so a node's only reachable footprint is the lanes into and out of it.
    """
    return state.lanes.filter((pl.col("from_node_id") == node_id) | (pl.col("to_node_id") == node_id))


def _estimate_seconds(state: ScenarioState, includes_forecast: bool, recorded_latencies: dict[str, float] | None) -> float:
    """Rough runtime for the confirm card: forecast + baseline + classical.

    The forecast term is series count times the scale study's measured ~25 ms per
    series; the optimizer terms come from the recorded run's own latencies when
    available. It is labelled an estimate everywhere it is surfaced.
    """
    # Only finished-good customer series are fitted (`forecast_finished_goods`
    # filters on demand_type), so the derived-component rows cost nothing here.
    series = (
        state.demand.filter(pl.col("demand_type") == "finished_good_customer")
        .select("node_id", "sku_id")
        .unique()
        .height
    )
    forecast_seconds = (series * FORECAST_MS_PER_SERIES / 1000.0) if includes_forecast else 0.0
    latencies = recorded_latencies or {}
    optimizer_seconds = float(latencies.get("baseline", 0.05)) + float(latencies.get("classical", 0.25))
    return forecast_seconds + optimizer_seconds + 1.0  # +1s for ingest and overlay


def analyse(
    perturbation: Perturbation,
    state: ScenarioState,
    recorded_latencies: dict[str, float] | None = None,
) -> Impact:
    """What this perturbation touches, and whether it can move the plan.

    The reachability verdict is the load-bearing part. A perturbation that cannot
    change any input the optimizer reads must be reported as such at parse time —
    running it would produce a confident "no impact" that means nothing.
    """
    read_period = capacity_read_period(state)

    if perturbation.kind == "demand_multiplier":
        demand = state.demand
        mask = pl.col("period").is_between(perturbation.from_period, perturbation.to_period)
        if perturbation.scope == "customer":
            mask = mask & (pl.col("node_id") == perturbation.scope_id)
        elif perturbation.scope == "sku":
            mask = mask & (pl.col("sku_id") == perturbation.scope_id)
        touched = demand.filter(mask)
        rows = touched.height
        series = touched.select("node_id", "sku_id").unique().height
        # Split by demand type. "All demand" covers both the finished-good customer
        # series the forecaster fits and the derived-component rows that set inbound
        # flow, and reporting one total would contradict the dataset view's own
        # "32 demand series" (which counts finished goods only).
        by_type = {
            row["demand_type"]: row["series"]
            for row in (
                touched.group_by("demand_type")
                .agg(pl.struct("node_id", "sku_id").n_unique().alias("series"))
                .sort("demand_type")
                .to_dicts()
            )
        }
        return Impact(
            reaches_optimizer=rows > 0,
            why=(
                f"Demand feeds the forecast, which the optimizer reads for every period, so a change to any "
                f"period reaches the plan. This touches {rows:,} demand rows across {series} series "
                f"({_series_breakdown(by_type)})."
                if rows > 0
                else "No demand rows match that scope and period range, so nothing would change."
            ),
            series_affected=series,
            series_by_demand_type=by_type,
            demand_rows_affected=rows,
            capacity_read_period=read_period,
            estimated_seconds=_estimate_seconds(state, True, recorded_latencies),
        )

    # Both capacity kinds reach the optimizer only through the single period it reads.
    if perturbation.kind == "node_outage":
        lanes = lanes_touching(state, str(perturbation.node_id))
        multiplier = 0.0
    else:
        lanes = state.lanes.filter(pl.col("lane_id") == perturbation.lane_id)
        multiplier = _multiplier_of(perturbation.capacity_multiplier, 0.0)

    lane_ids = lanes.select("lane_id").to_series().to_list()
    by_type = {row["lane_type"]: row["len"] for row in lanes.group_by("lane_type").len().to_dicts()}
    in_range = perturbation.from_period <= read_period <= perturbation.to_period

    # Would this strip a whole lane type of capacity at the read period? The
    # optimizer skips a lane type with no capacity, which is a big structural
    # change worth stating up front rather than discovering in the output.
    stripped: list[str] = []
    if in_range and multiplier == 0.0:
        at_period = state.lane_periods.filter(pl.col("period") == read_period).select(
            "lane_id", "effective_capacity_units"
        )
        merged = state.lanes.join(at_period, on="lane_id", how="left").with_columns(
            pl.col("effective_capacity_units")
            .fill_null(pl.col("capacity_units_per_period"))
            .alias("capacity")
        )
        for lane_type in sorted(by_type):
            frame = merged.filter(pl.col("lane_type") == lane_type)
            total = float(frame.select(pl.sum("capacity")).item() or 0.0)
            remaining = float(
                frame.filter(~pl.col("lane_id").is_in(lane_ids)).select(pl.sum("capacity")).item() or 0.0
            )
            if total > 0 and remaining <= 0:
                stripped.append(lane_type)

    if in_range:
        why = (
            f"On this dataset the optimizer reads lane capacity at period {read_period} only, and your range "
            f"covers it, so this will change the plan. It scales capacity on {len(lane_ids)} lane"
            f"{'' if len(lane_ids) == 1 else 's'}."
        )
    else:
        why = (
            f"This would not change the plan. The optimizer reads lane capacity at period {read_period} only "
            f"(verified against the source), and periods {perturbation.from_period}-{perturbation.to_period} "
            f"do not include it — so the run would report no impact for a reason that has nothing to do with "
            f"your question."
        )

    return Impact(
        reaches_optimizer=in_range,
        why=why,
        lanes_affected=lane_ids,
        lane_types_affected=by_type,
        capacity_read_period=read_period,
        removes_all_capacity_for=stripped,
        estimated_seconds=_estimate_seconds(state, False, recorded_latencies),
    )


# ---------------------------------------------------------------------------
# the confirm-before-run card (decision 6)
# ---------------------------------------------------------------------------


def _multiplier_of(value: float | None, default: float) -> float:
    """Read a multiplier that may legitimately be 0.0.

    ``value or default`` is wrong here: 0.0 is falsy, so "demand drops to zero"
    was displayed as "scaled to 1x" on the confirmation card — the one screen a
    planner approves before compute is spent.
    """
    return default if value is None else float(value)


def plain_english(perturbation: Perturbation, state: ScenarioState, impact: Impact) -> str:
    """The system stating its reading back, in the planner's words."""
    window = (
        f"in period {perturbation.from_period}"
        if perturbation.from_period == perturbation.to_period
        else f"from period {perturbation.from_period} to period {perturbation.to_period}"
    )
    if perturbation.kind == "node_outage":
        return (
            f"{perturbation.node_id} unable to ship or receive {window} — "
            f"{len(impact.lanes_affected)} lane{'' if len(impact.lanes_affected) == 1 else 's'} affected, "
            f"nothing else changed."
        )
    if perturbation.kind == "lane_disruption":
        multiplier = _multiplier_of(perturbation.capacity_multiplier, 0.0)
        change = "closed completely" if multiplier == 0.0 else f"capacity scaled to {multiplier:g}x"
        return f"Lane {perturbation.lane_id} {change} {window} — nothing else changed."
    scope = perturbation.scope or "all"
    where = {
        "all": "all demand",
        "customer": f"demand at {perturbation.scope_id}",
        "sku": f"demand for {perturbation.scope_id}",
    }[scope]
    return (
        f"{where} scaled to {_multiplier_of(perturbation.demand_multiplier, 1.0):g}x {window} — "
        f"{impact.demand_rows_affected:,} demand rows across {impact.series_affected} series "
        f"({_series_breakdown(impact.series_by_demand_type)}), nothing else changed."
    )


def _estimate_basis(perturbation: Perturbation) -> str:
    """State what the estimate actually includes.

    A capacity perturbation leaves demand untouched, so it can reuse a cached
    forecast (decision 8) and the estimate excludes forecasting entirely. Saying
    "forecast plus optimizer" for both kinds would have been wrong for one of
    them, on a figure the planner is asked to accept before spending compute.
    """
    optimizer = (
        "the recorded baseline and classical latencies for this scenario; PPO excluded"
    )
    if perturbation.kind == "demand_multiplier":
        return (
            "forecasting every finished-good series at the ~25 ms per series measured in the Iteration 3 "
            f"scale study, plus {optimizer}"
        )
    return (
        "no forecasting, because this perturbation does not touch demand and the cached forecast can be "
        f"reused (implemented in Phase 3); plus {optimizer}"
    )


def build_confirmation_card(
    perturbation: Perturbation,
    state: ScenarioState,
    impact: Impact,
) -> dict[str, Any]:
    """The card a planner confirms before any compute is spent.

    ``executable`` is deliberately False everywhere in Phase 2: the parser and the
    schema exist, and no execution path does.
    """
    warnings: list[str] = []
    if not impact.reaches_optimizer:
        warnings.append(impact.why)
    if impact.removes_all_capacity_for:
        warnings.append(
            "This removes every unit of capacity for "
            + ", ".join(impact.removes_all_capacity_for)
            + f" at period {impact.capacity_read_period}, so the optimizer would have no route of that kind "
            "at all. That is a bigger change than a single outage."
        )
    return {
        "reading": plain_english(perturbation, state, impact),
        "perturbation": perturbation.as_dict(),
        "impact": impact.as_dict(),
        "fingerprint": perturbation.fingerprint(),
        "estimated_seconds": round(impact.estimated_seconds, 1),
        "estimate_basis": _estimate_basis(perturbation),
        "warnings": warnings,
        "requires_confirmation": True,
        "executable": False,
        "not_executable_reason": (
            "Iteration 5 Phase 2 builds the parser and the schema only. Running a perturbation through the "
            "real pipeline is Phase 3; nothing here executes."
        ),
        "ppo_included": False,
        "beta": True,
    }
