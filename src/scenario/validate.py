"""Validate a custom scenario **before** anything is written or any compute is spent.

Guardrail 5 and decision 11: validate -> refuse in plain English -> only then write.
A slider that produces a 500 is worse than a slider that says why it refused, so
every refusal here is a sentence a planner can act on, and refusals are returned
as a *list* — someone who got three things wrong should be told all three.

Two things in here are load-bearing for honesty rather than for correctness:

* :func:`capacity_read_period` derives the period the optimizer reads from the
  configuration **being edited**. §1.3: ``simulation.horizon_periods`` is itself a
  control and it *moves* that period, so a hardcoded 52 would be wrong for any
  custom scenario with a different history length. This is called out in the plan
  as the easiest thing in the iteration to get quietly wrong.
* :func:`capacity_reachability` reuses Iteration 5's ``reaches_optimizer`` /
  ``capacity_read_period`` field names deliberately (§1.8), so the chat layer's
  vocabulary and this one cannot drift.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from typing import Any

from src.scenario.ledger import (
    INERT,
    INERT_LABEL,
    LABEL_ONLY,
    LABEL_ONLY_LABEL,
    NETWORK_KEYS,
    NOT_COMPARABLE_TAIL,
    PROBLEM_SIZE,
    SETTINGS_BY_KEY,
    get_value,
)
from src.scenario.synthesize import CANONICAL_SCENARIOS, is_network_key, load_base_config

#: Decision 3. The stored name is ``custom-<slug>``; the prefix does four jobs —
#: a .gitignore pattern, collision protection for the name-keyed artifact, a
#: visible marker in the dropdown and the URL, and a safe clear-all selector.
CUSTOM_PREFIX = "custom-"
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
SLUG_MAX_LENGTH = 40

#: Every way this module can refuse a configuration. The committed eval set has to
#: exercise all of them: an untested refusal is a guardrail claim with no evidence
#: (the Iteration 5 red-team PATTERN_COVERAGE lesson, applied to a slider).
REFUSAL_CODES = (
    "name_empty",
    "name_path_traversal",
    "name_too_long",
    "name_reserved",
    "name_bad_characters",
    "unknown_setting",
    "unknown_network_setting",
    "network_count_below_floor",
    "network_zero_distribution_centers",
    "network_zero_suppliers",
    "network_count_above_ceiling",
    "wrong_type",
    "not_a_choice",
    "range_inverted",
    "below_minimum",
    "above_maximum",
    "horizon_shorter_than_run",
    "affected_lane_count_exceeds_network",
    "window_starts_after_horizon",
    "window_exceeds_horizon",
    "unknown_simple_control",
)

#: Accepted, but the planner is told before any compute is spent.
WARNING_CODES = (
    "capacity_window_misses_read_period",
    "description_prompt_injection",
    "capacity_wipe_does_not_create_shortage",
    "settings_recorded_not_read",
    "settings_label_only",
    "resized_network_not_comparable",
)


@dataclass(frozen=True)
class Refusal:
    """One reason the configuration was not accepted."""

    code: str
    message: str
    field: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "field": self.field, "message": self.message}


@dataclass(frozen=True)
class Warning_:
    """Accepted, but the planner needs to know something before spending compute."""

    code: str
    message: str
    field: str | None = None
    detail: dict[str, Any] = dc_field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = {"code": self.code, "field": self.field, "message": self.message}
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass
class ValidationResult:
    refusals: list[Refusal] = dc_field(default_factory=list)
    warnings: list[Warning_] = dc_field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.refusals

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "refusals": [item.as_dict() for item in self.refusals],
            "warnings": [item.as_dict() for item in self.warnings],
        }


# ---------------------------------------------------------------------------
# the network tier's floors and ceilings (Iteration 6b, decisions 4, 5, 6)
# ---------------------------------------------------------------------------
#
# Guardrail 1 of 6b: *nothing may crash*. Five network values raise an uncaught
# exception today — four inside the generator and one, the nastiest, two stages
# later in the forecast after a full dataset has already been written. A stack
# trace in front of a sponsor is worse than a missing feature, so every one is
# refused BEFORE anything is written.
#
# Two more values do not crash, and are worse for it. ``distribution_centers = 0``
# and ``suppliers = 0`` both produce a confident, cheaper, better-scoring answer
# for a network that cannot physically operate. Decision 4 floors both at 1 and
# quotes the measured numbers in the refusal, so the message teaches the modelling
# limit rather than merely blocking the value.

#: ``setting key -> (refusal code, the sentence)``. The measured figures are from
#: on-device runs on 2026-08-21, re-verified the same day.
NETWORK_FLOOR_REFUSALS: dict[str, tuple[str, str]] = {
    "network.distribution_centers": (
        "network_zero_distribution_centers",
        "A network with no distribution centers has no lane by which a finished good can "
        "reach a customer \u2014 and this prototype does not notice. Measured: it scores "
        "68,565.25 at 92.01% fill, which is better than baseline on BOTH counts "
        "(81,789.36 at 83.66%), because the optimizer has no per-node capacity and the "
        "fill-rate calculation never asks whether a delivery route exists. "
        "That is a limit of the model, not a fact about your network. Keep at least 1.",
    ),
    "network.suppliers": (
        "network_zero_suppliers",
        "A network with no suppliers still reports 83.66% fill \u2014 unchanged from "
        "baseline to the digit \u2014 because nothing downstream checks that components "
        "can actually be sourced. Measured objective 77,390.94, so removing every supplier "
        "reads as a saving. Keep at least 1.",
    ),
    "network.plants": (
        "network_count_below_floor",
        "A network needs at least 1 plant. Zero plants raises a ZeroDivisionError inside "
        "the generator, before any data is written.",
    ),
    "network.finished_goods": (
        "network_count_below_floor",
        "A network needs at least 1 finished good. Zero raises a ZeroDivisionError inside "
        "the generator \u2014 there is nothing to build a bill of materials from.",
    ),
    "network.subassemblies_per_finished_good": (
        "network_count_below_floor",
        "Each finished good needs at least 1 subassembly. Zero raises a ZeroDivisionError "
        "inside the generator.",
    ),
    "network.raw_components_per_subassembly": (
        "network_count_below_floor",
        "Each subassembly needs at least 1 raw component. Zero raises a ZeroDivisionError "
        "inside the generator.",
    ),
    "network.customers": (
        "network_count_below_floor",
        "A network needs at least 1 customer. Zero is the worst of the crashing values: it "
        "passes generation and writes a complete dataset, then fails two stages later in the "
        "FORECAST, because there is no demand history to sum. Refused before anything is "
        "written.",
    ),
}

#: Decision 6. These exist to stop a fat-fingered 10,000 reaching the generator,
#: **not** to model a limit \u2014 the upper end was probed and is sane (40 customers
#: and 12 DCs both run fine and fast). Said plainly in the refusal so nobody reads
#: a sanity cap as a capability statement.
NETWORK_CEILING_NOTE = (
    "This cap exists to stop a typo reaching the generator, not because the network cannot "
    "be bigger \u2014 40 customers and 12 distribution centers were both measured running "
    "fine. If you genuinely need more, the cap is a judgement call and can be raised."
)


# ---------------------------------------------------------------------------
# names (decision 3)
# ---------------------------------------------------------------------------


def validate_slug(slug: str) -> ValidationResult:
    """Check the user-supplied half of a custom scenario name.

    Modelled on ``_resolve_scenario_dir``'s containment check and
    ``test_no_path_traversal_via_scenario``: the API's existing scenario pattern
    is ``^[a-zA-Z0-9._-]+$``, which a literal ``..`` satisfies. This pattern
    excludes ``.`` outright, and the traversal case is refused by name anyway so
    the reason is explicit rather than incidental.
    """
    result = ValidationResult()
    raw = slug if isinstance(slug, str) else ""
    if not raw.strip():
        result.refusals.append(Refusal(
            "name_empty", "Give the scenario a name — for example 'q3-surge'.", "name"))
        return result
    if ".." in raw or "/" in raw or "\\" in raw:
        result.refusals.append(Refusal(
            "name_path_traversal",
            "A scenario name cannot contain '..', '/' or '\\'. Use letters, numbers and "
            "hyphens — for example 'q3-surge'.",
            "name"))
        return result
    if len(raw) > SLUG_MAX_LENGTH:
        result.refusals.append(Refusal(
            "name_too_long",
            f"That name is {len(raw)} characters; keep it to {SLUG_MAX_LENGTH} or fewer.",
            "name"))
        return result
    if raw.lower() in CANONICAL_SCENARIOS or f"{CUSTOM_PREFIX}{raw.lower()}" in CANONICAL_SCENARIOS:
        result.refusals.append(Refusal(
            "name_reserved",
            f"'{raw}' is one of the four recorded benchmark scenarios and cannot be reused. "
            "Pick a different name.",
            "name"))
        return result
    if not SLUG_PATTERN.match(raw):
        result.refusals.append(Refusal(
            "name_bad_characters",
            "Use lower-case letters, numbers and hyphens only, starting with a letter or "
            "number — for example 'q3-surge'.",
            "name"))
    return result


def scenario_name_for(slug: str) -> str:
    """``'q3-surge' -> 'custom-q3-surge'``, idempotent if already prefixed."""
    clean = slug.strip().lower()
    if clean.startswith(CUSTOM_PREFIX):
        return clean
    return f"{CUSTOM_PREFIX}{clean}"


# ---------------------------------------------------------------------------
# per-setting types and ranges
# ---------------------------------------------------------------------------


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_overrides(overrides: dict[str, Any]) -> ValidationResult:
    """Type- and range-check raw setting overrides, and refuse out-of-scope keys."""
    result = ValidationResult()
    for key, value in sorted(overrides.items()):
        setting = SETTINGS_BY_KEY.get(key)
        if setting is None:
            # Iteration 6b: ``network.*`` is no longer refused as out-of-scope — the
            # eight real counts are settings now. But a *misspelt* network key gets a
            # more useful sentence than the generic one, because "there are 67
            # settings" does not help someone who typed ``network.warehouses``.
            if is_network_key(key):
                result.refusals.append(Refusal(
                    "unknown_network_setting",
                    f"'{key}' is not one of the network counts. There are eight: "
                    + ", ".join(k.split(".", 1)[1] for k in NETWORK_KEYS)
                    + ".",
                    key))
                continue
            result.refusals.append(Refusal(
                "unknown_setting",
                f"'{key}' is not a scenario setting. There are {len(SETTINGS_BY_KEY)}, and the "
                "preview endpoint lists them all with their ranges.",
                key))
            continue

        # Decisions 4, 5 and 6: a network count out of bounds gets the measured
        # reason, not the generic "below the minimum of 1". This runs before the
        # generic range check below so the specific sentence wins.
        #
        # Gated on `_is_int` rather than `_is_number` deliberately: every network
        # count is a whole number, and 0.5 plants is a *typing* mistake, not an
        # attempt to run a plant-less network. Letting it fall through to the type
        # check below says "has to be a whole number", which is the useful sentence
        # — where the floor message would have talked about zero plants.
        if setting.group == "network" and _is_int(value):
            number = float(value)
            if setting.minimum is not None and number < setting.minimum:
                code, reason = NETWORK_FLOOR_REFUSALS.get(
                    key, ("network_count_below_floor",
                          f"'{setting.label}' has to be at least {setting.minimum:g}."))
                result.refusals.append(Refusal(code, reason, key))
                continue
            if setting.maximum is not None and number > setting.maximum:
                result.refusals.append(Refusal(
                    "network_count_above_ceiling",
                    f"'{setting.label}' is {number:g}; this build caps it at "
                    f"{setting.maximum:g}. {NETWORK_CEILING_NOTE}",
                    key))
                continue

        if setting.kind == "str":
            if not isinstance(value, str) or not value.strip():
                result.refusals.append(Refusal(
                    "wrong_type", f"'{setting.label}' needs to be a short piece of text.", key))
                continue
            if setting.choices and value not in setting.choices:
                result.refusals.append(Refusal(
                    "not_a_choice",
                    f"'{setting.label}' has to be one of: {', '.join(setting.choices)}.",
                    key))
            continue

        if setting.kind == "range2":
            if (not isinstance(value, (list, tuple)) or len(value) != 2
                    or not all(_is_number(item) for item in value)):
                result.refusals.append(Refusal(
                    "wrong_type",
                    f"'{setting.label}' needs two numbers — a low and a high value.", key))
                continue
            low, high = float(value[0]), float(value[1])
            if low > high:
                result.refusals.append(Refusal(
                    "range_inverted",
                    f"'{setting.label}': the low value ({low:g}) is above the high value "
                    f"({high:g}). Swap them.",
                    key))
                continue
            for bound in (low, high):
                if setting.minimum is not None and bound < setting.minimum:
                    result.refusals.append(Refusal(
                        "below_minimum",
                        f"'{setting.label}' has to stay at or above {setting.minimum:g}.", key))
                    break
                if setting.maximum is not None and bound > setting.maximum:
                    result.refusals.append(Refusal(
                        "above_maximum",
                        f"'{setting.label}' has to stay at or below {setting.maximum:g}.", key))
                    break
            continue

        if setting.kind == "int" and not _is_int(value):
            result.refusals.append(Refusal(
                "wrong_type", f"'{setting.label}' has to be a whole number.", key))
            continue
        if setting.kind == "float" and not _is_number(value):
            result.refusals.append(Refusal(
                "wrong_type", f"'{setting.label}' has to be a number.", key))
            continue
        number = float(value)
        if setting.minimum is not None and number < setting.minimum:
            result.refusals.append(Refusal(
                "below_minimum",
                f"'{setting.label}' is {number:g}, below the minimum of {setting.minimum:g}.",
                key))
        elif setting.maximum is not None and number > setting.maximum:
            result.refusals.append(Refusal(
                "above_maximum",
                f"'{setting.label}' is {number:g}, above the maximum of {setting.maximum:g}.",
                key))
    return result


# ---------------------------------------------------------------------------
# the capacity read period (§1.3, decision 4)
# ---------------------------------------------------------------------------


def capacity_read_period(config: dict[str, Any]) -> int:
    """The single period at which the optimizer reads lane capacity.

    The optimizer reads at ``max(demand.period)`` (``ScenarioState.horizon()``,
    used by ``select_greedy_lanes`` and ``select_ortools_lanes``). The generator
    writes demand for periods ``1..simulation.horizon_periods``, so for a config
    that has not been generated yet, that setting **is** the read period.

    Derived from the config under edit, never a constant — a custom scenario with
    a 26-period history reads at 26, and a disruption over periods 18-27 that is a
    no-op at 52 suddenly bites. ``test_capacity_read_period_matches_the_real_state``
    pins this identity against real generated data.
    """
    return int(get_value(config, "simulation.horizon_periods") or 0)


def lane_counts(config: dict[str, Any]) -> dict[str, int]:
    """How many lanes of each family this network has, from the ``network:`` counts."""
    network = config.get("network") or {}
    suppliers = int(network.get("suppliers") or 0)
    plants = int(network.get("plants") or 0)
    dcs = int(network.get("distribution_centers") or 0)
    customers = int(network.get("customers") or 0)
    return {
        "inbound_raw": suppliers * plants,
        "plant_to_dc": plants * dcs,
        "dc_to_customer": dcs * customers,
    }


def _window(block: dict[str, Any] | None) -> tuple[int, int] | None:
    if not isinstance(block, dict):
        return None
    start = block.get("start_period")
    duration = block.get("duration_periods")
    if start is None or duration is None:
        return None
    start_i, duration_i = int(start), int(duration)
    return start_i, start_i + duration_i - 1


def capacity_reachability(config: dict[str, Any]) -> dict[str, Any]:
    """Whether this config's lane disruption can change the optimizer's answer.

    Returns Iteration 5's vocabulary unchanged: ``reaches_optimizer`` and
    ``capacity_read_period``. ``applicable`` is ``False`` when the scenario has no
    lane disruption at all, which is not the same as a disruption that misses.
    """
    read_period = capacity_read_period(config)
    disruption = config.get("lane_disruption")
    window = _window(disruption)
    if window is None:
        return {
            "applicable": False,
            "reaches_optimizer": True,
            "capacity_read_period": read_period,
            "why": "This scenario has no lane disruption, so nothing depends on the "
                   "capacity read period.",
        }
    first, last = window
    reaches = first <= read_period <= last
    if reaches:
        why = (
            f"The disruption covers period {read_period}, which is the period the optimizer "
            f"reads lane capacity at, so it will affect the result."
        )
    else:
        why = (
            f"The optimizer reads lane capacity at period {read_period} only, and this "
            f"disruption runs from period {first} to {last}. It will therefore not change "
            f"the answer at all. Do not read the result as resilience — the disruption is "
            f"not being absorbed by the network, it is not being seen. Extend the window to "
            f"period {read_period} (or to the end of the horizon) to make it bite."
        )
    return {
        "applicable": True,
        "reaches_optimizer": reaches,
        "capacity_read_period": read_period,
        "window": {"from_period": first, "to_period": last},
        "why": why,
        "suggested_duration_periods": max(1, read_period - first + 1) if not reaches else None,
    }


# ---------------------------------------------------------------------------
# feasibility pre-check (decision 11)
# ---------------------------------------------------------------------------


def network_comparability(
    config: dict[str, Any],
    base: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Whether this network's objective may be compared to the recorded baseline.

    🔴 Iteration 6b guardrail 4. ``capacity_reachability`` answers *"can this change
    reach the optimizer?"*; this answers the question after it — *"is the answer it
    produced the same **kind** of number as 81,789.36?"*

    It is not, whenever a **problem-size** count differs from baseline. Changing the
    customer base or the BOM depth changes total demand, so the objective measures a
    different quantity. Measured 2026-08-21: 7 customers scores 66,548.24, which
    looks like an 18.6% improvement and is really 12% less demand to serve.

    The classification comes from the ledger (``answer_class``), not from a list
    kept here, so this cannot drift from what the controls say. Node counts
    (suppliers, plants, DCs) leave total demand bit-identical and stay comparable.
    """
    base_network = (base if base is not None else load_base_config()).get("network") or {}
    network = config.get("network") or {}

    resized: list[dict[str, Any]] = []
    edited: list[dict[str, Any]] = []
    for key in NETWORK_KEYS:
        setting = SETTINGS_BY_KEY.get(key)
        if setting is None:
            continue
        name = key.split(".", 1)[1]
        was, now = base_network.get(name), network.get(name)
        if was is None or now is None or was == now:
            continue
        entry = {
            "key": key, "label": setting.label,
            "baseline_value": was, "scenario_value": now,
        }
        # Any of the eight makes this a custom *dataset* rather than a custom
        # scenario — that distinction is what Ryan asked for twice, so the payload
        # has to carry it or the UI can only guess from the settings it was handed.
        edited.append(entry)
        if setting.answer_class == PROBLEM_SIZE:
            resized.append(entry)

    if not resized:
        return {
            "comparable_to_baseline": True, "resized_settings": [],
            "network_edited": bool(edited), "edited_settings": edited,
            "why": "", "note": "",
        }

    changed = ", ".join(
        f"{item['label'].lower()} {item['baseline_value']} \u2192 {item['scenario_value']}"
        for item in resized
    )
    return {
        "comparable_to_baseline": False,
        "resized_settings": resized,
        "network_edited": True,
        "edited_settings": edited,
        "why": f"This network is a different size from baseline ({changed}), so total demand "
               f"is different and the objective is a different quantity.",
        # The tail only: ``why`` above already opens with the size statement, and with
        # the specific counts in it. Appending the full note repeated the sentence.
        "note": NOT_COMPARABLE_TAIL,
    }


def feasibility(config: dict[str, Any], run_horizon: int = 8) -> ValidationResult:
    """Refuse configurations that would produce a 500 or a meaningless objective."""
    result = ValidationResult()
    horizon = capacity_read_period(config)
    if horizon and horizon < run_horizon:
        result.refusals.append(Refusal(
            "horizon_shorter_than_run",
            f"The history is {horizon} periods but the plan is solved over {run_horizon}. "
            f"Give it at least {run_horizon} periods of history.",
            "simulation.horizon_periods"))

    disruption = config.get("lane_disruption")
    if isinstance(disruption, dict):
        family = str(disruption.get("lane_type") or "inbound_raw")
        available = lane_counts(config).get(family, 0)
        wanted = int(disruption.get("affected_lane_count") or 0)
        if wanted > available:
            result.refusals.append(Refusal(
                "affected_lane_count_exceeds_network",
                f"This network has {available} {family.replace('_', ' ')} lanes, so "
                f"{wanted} cannot be disrupted. Lower it to {available} or fewer.",
                "lane_disruption.affected_lane_count"))

    for block_name, label in (("demand.shock", "demand spike"), ("lane_disruption", "lane disruption")):
        block = get_value(config, block_name)
        window = _window(block if isinstance(block, dict) else None)
        if window is None:
            continue
        first, last = window
        if horizon and first > horizon:
            result.refusals.append(Refusal(
                "window_starts_after_horizon",
                f"The {label} starts at period {first}, but the history is only {horizon} "
                f"periods long. Move it inside the horizon.",
                f"{block_name}.start_period"))
        elif horizon and last > horizon:
            result.refusals.append(Refusal(
                "window_exceeds_horizon",
                f"The {label} runs to period {last}, past the end of the {horizon}-period "
                f"history. Shorten it to {horizon - first + 1} periods or fewer.",
                f"{block_name}.duration_periods"))
    return result


# ---------------------------------------------------------------------------
# the whole check
# ---------------------------------------------------------------------------


def capacity_wipe_warning(config: dict[str, Any]) -> Warning_ | None:
    """🔴 Zeroing an EVERY lane of a family does not create a shortage — it removes a cost.

    Measured on this device (baseline, 2026-08-20), zeroing all 10 ``inbound_raw``
    lanes at the capacity read period:

    ==================  ==========  ==========
    metric              base        all zeroed
    ==================  ==========  ==========
    objective           81,789.36   77,788.55
    transport cost      20,478.98   16,478.17
    backorder cost      18,493.56   18,493.56
    lost-sale cost      19,916.14   19,916.14
    fill rate           0.8366      0.8366
    ==================  ==========  ==========

    Only transport moves. Every other cost component is identical to the cent and
    service does not change, so **the objective improves by exactly the cost of
    the traffic that stopped running.** A planner who builds "we lose every
    supplier lane" and reads a cheaper plan has been misled, so this is said up
    front — the same discipline as Iteration 5's no-op card, applied to a lever
    that *does* reach the optimizer and still must not be read as resilience.

    This was a refusal until a review measured it. Refusing it was wrong twice
    over: the run works, and the stated reason ("the objective would be
    meaningless") was false.
    """
    disruption = config.get("lane_disruption")
    if not isinstance(disruption, dict):
        return None
    if float(disruption.get("capacity_multiplier", 1.0)) != 0.0:
        return None
    family = str(disruption.get("lane_type") or "inbound_raw")
    available = lane_counts(config).get(family, 0)
    wanted = int(disruption.get("affected_lane_count") or 0)
    if available <= 0 or wanted < available:
        return None
    if not capacity_reachability(config)["reaches_optimizer"]:
        # Already covered, and more severely, by the read-period warning.
        return None
    readable = family.replace("_", " ")
    return Warning_(
        "capacity_wipe_does_not_create_shortage",
        f"You are setting all {available} {readable} lanes to zero capacity at period "
        f"{capacity_read_period(config)}, the one period the optimizer reads. Measured on "
        f"this device, that does not cause shortages: fill rate and every cost except "
        f"transport stay identical, and the objective can come out LOWER because the plan "
        f"stops paying to ship on those lanes. Do not read the result as resilience, and do "
        f"not read a cheaper objective as an improvement. Disrupt fewer lanes if you want to "
        f"see rerouting cost.",
        "lane_disruption.capacity_multiplier",
        detail={
            "lane_family": family,
            "lanes_zeroed": available,
            "mechanism": "the only cost component that moves is transport",
            "expect_objective_to": "fall",
        },
    )


def description_injection_warning(description: str | None) -> Warning_ | None:
    """Flag prompt-injection payloads in the planner's own description text.

    The carry-forward guardrail is *flagged, never executed*. This matters here
    rather than later because ``description`` is the one free-text field a custom
    scenario carries, and it does not stay inert: the dataset view renders it, and
    the chat layer retrieves it as the ``dataset.scenario_diff.description`` fact —
    so once Phase 2 persists a config, hostile text in this field reaches an LLM
    prompt. Flagging it at validation closes that before persistence opens it.

    Reuses ``src/rag/advisory``'s committed pattern set rather than inventing a
    second one, so there is one definition of what an injection looks like. The
    import is function-local: ``advisory`` imports the pipeline at module level,
    and this package deliberately has no execution path.
    """
    if not description or not description.strip():
        return None
    from src.rag.advisory import _match_injection_patterns

    matches = _match_injection_patterns(description)
    if not matches:
        return None
    names = sorted({match["pattern"] for match in matches})
    return Warning_(
        "description_prompt_injection",
        f"The description looks like it contains instructions aimed at a language model "
        f"({', '.join(names)}). It is stored and displayed as written and is never executed, "
        f"but rewrite it as a plain description if that was not deliberate.",
        "description",
        detail={"patterns": names, "matches": matches},
    )


def no_op_warnings(overrides: dict[str, Any]) -> list[Warning_]:
    """Flag edits to settings that cannot move the answer (guardrail 1).

    These are *warnings*, not refusals: the settings are real, they are recorded
    in the dataset, and the dataset view will show them changed. Hiding them
    would be dishonest about what the dataset contains; presenting them as live
    controls would be worse.
    """
    inert = [key for key in sorted(overrides) if (SETTINGS_BY_KEY.get(key) or None)
             and SETTINGS_BY_KEY[key].reach == INERT]
    labels = [key for key in sorted(overrides) if (SETTINGS_BY_KEY.get(key) or None)
              and SETTINGS_BY_KEY[key].reach == LABEL_ONLY]
    out: list[Warning_] = []
    if inert:
        out.append(Warning_(
            "settings_recorded_not_read",
            f"{len(inert)} of the settings you changed are {INERT_LABEL}. They will show up on "
            f"the dataset view and will not change the result: "
            f"{', '.join(inert)}.",
            detail={"settings": inert, "label": INERT_LABEL}))
    if labels:
        out.append(Warning_(
            "settings_label_only",
            f"{', '.join(labels)} is {LABEL_ONLY_LABEL}.",
            detail={"settings": labels, "label": LABEL_ONLY_LABEL}))
    return out


def validate_custom_scenario(
    slug: str,
    config: dict[str, Any],
    overrides: dict[str, Any] | None = None,
    run_horizon: int = 8,
    description: str | None = None,
) -> ValidationResult:
    """Every check, in the order a planner would want to hear about them."""
    result = ValidationResult()
    name_check = validate_slug(slug)
    result.refusals.extend(name_check.refusals)
    overrides_ok = True
    if overrides:
        override_check = validate_overrides(overrides)
        result.refusals.extend(override_check.refusals)
        overrides_ok = override_check.ok
    # Only cross-check feasibility once the individual values are known good.
    # Running it on a config that still holds a rejected value produces true but
    # useless follow-on refusals — `horizon_periods: true` becomes "the history is
    # 1 period", which sends the planner after the wrong problem.
    if overrides_ok:
        result.refusals.extend(feasibility(config, run_horizon=run_horizon).refusals)

    reach = capacity_reachability(config)
    if reach["applicable"] and not reach["reaches_optimizer"]:
        result.warnings.append(Warning_(
            "capacity_window_misses_read_period",
            reach["why"],
            "lane_disruption.duration_periods",
            detail={
                "reaches_optimizer": False,
                "capacity_read_period": reach["capacity_read_period"],
                "window": reach["window"],
                "suggested_duration_periods": reach["suggested_duration_periods"],
            },
        ))
    sizing = network_comparability(config)
    if not sizing["comparable_to_baseline"]:
        result.warnings.append(Warning_(
            "resized_network_not_comparable",
            f"{sizing['why']} {sizing['note']}",
            sizing["resized_settings"][0]["key"],
            detail={
                "comparable_to_baseline": False,
                "resized_settings": sizing["resized_settings"],
            },
        ))
    injection = description_injection_warning(description)
    if injection is not None:
        result.warnings.append(injection)
    wipe = capacity_wipe_warning(config)
    if wipe is not None:
        result.warnings.append(wipe)
    if overrides:
        result.warnings.extend(no_op_warnings(overrides))
    return result
