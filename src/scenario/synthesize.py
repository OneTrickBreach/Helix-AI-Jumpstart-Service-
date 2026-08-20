"""Turn a planner's edits into a **complete** scenario config.

§1.5 is the constraint: ``load_scenario`` reads only ``data/scenarios/<name>.yaml``,
indexes straight into ``config["demand"]`` and friends, and has **no defaults merge
and no schema**. So a saved custom scenario has to be written out whole — baseline's
values with the user's overrides applied — not as a sparse patch. The upside is that
the result is an ordinary scenario file: ``make data SCENARIO=custom-x`` works on it,
and ``metadata.json`` embeds it so the dataset view can diff it for free.

Nothing here writes to disk. Phase 2 owns persistence.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.scenario.ledger import NETWORK_KEYS, get_value, set_value

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_CONFIG_ROOT = REPO_ROOT / "data" / "scenarios"

#: Every custom scenario starts from ``baseline`` — the scenario with no shock and
#: no disruption, so "what did I change?" is always answered against normal
#: operating conditions.
BASE_SCENARIO = "baseline"

#: The four recorded scenarios. Reserved: a custom scenario may never take one of
#: these names, and no 6a code path may write their files (guardrail 3).
CANONICAL_SCENARIOS = ("baseline", "component-shortage-shock", "demand-surge", "stress-large")

#: Decision 7 — the seed is part of the saved config, not ambient.
DEFAULT_SEED = 12345


def load_base_config(scenario: str = BASE_SCENARIO) -> dict[str, Any]:
    """Read a shipped scenario config. Read-only, and never via ``load_scenario``.

    The generator's own loader reports every error by raising ``SystemExit``
    (§1.5), which FastAPI cannot render — so this reads and parses the file
    directly and lets ordinary exceptions surface.
    """
    path = SCENARIO_CONFIG_ROOT / f"{scenario}.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"scenario config {path.name} is not a mapping")
    return config


# ---------------------------------------------------------------------------
# the Simple tier (decision 5): 8 grouped controls
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimpleControl:
    """One idea a planner would say out loud, over one or more raw settings.

    ``scale`` controls are multipliers on baseline's values that resolve to
    concrete per-tier numbers, so the saved file has no new schema (§1.5).
    """

    name: str
    label: str
    kind: str  # "value" | "scale" | "group"
    writes: tuple[str, ...]
    minimum: float | None = None
    maximum: float | None = None
    fields: tuple[str, ...] = ()
    help: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "label": self.label,
            "kind": self.kind,
            "writes": list(self.writes),
        }
        if self.minimum is not None:
            payload["minimum"] = self.minimum
        if self.maximum is not None:
            payload["maximum"] = self.maximum
        if self.fields:
            payload["fields"] = list(self.fields)
        if self.help:
            payload["help"] = self.help
        return payload


SIMPLE_CONTROLS: tuple[SimpleControl, ...] = (
    SimpleControl(
        "demand_level", "Demand level", "value",
        ("demand.base_units_per_customer_period",),
        minimum=1, maximum=1_000_000,
        help="Units each customer orders per period before seasonality and noise.",
    ),
    SimpleControl(
        "demand_spike", "Demand spike", "group",
        ("demand.shock.multiplier", "demand.shock.start_period",
         "demand.shock.duration_periods", "demand.shock.name"),
        fields=("multiplier", "start_period", "duration_periods"),
        help="A temporary surge: 1.75x for 8 weeks from week 20 is one thing a planner says.",
    ),
    SimpleControl(
        "capacity_tightness", "Capacity tightness", "value",
        ("capacity.capacity_tightness",),
        minimum=0.4, maximum=3.0,
        help="Scales lane capacity at every period. Lower is tighter.",
    ),
    SimpleControl(
        "lane_disruption", "Lane disruption", "group",
        ("lane_disruption.lane_type", "lane_disruption.affected_lane_count",
         "lane_disruption.start_period", "lane_disruption.duration_periods",
         "lane_disruption.capacity_multiplier", "lane_disruption.lead_time_multiplier",
         "lane_disruption.name"),
        fields=("lane_type", "affected_lane_count", "start_period",
                "duration_periods", "capacity_multiplier", "lead_time_multiplier"),
        help="Lanes losing capacity for a window. The window defaults to running to the "
             "end of the horizon, because the optimizer reads lane capacity at one period only.",
    ),
    SimpleControl(
        "holding_cost", "Inventory holding cost", "scale",
        ("costs.holding_cost.raw_component", "costs.holding_cost.subassembly",
         "costs.holding_cost.finished_good"),
        minimum=0.0, maximum=100.0,
        help="A multiplier on baseline's per-tier holding costs.",
    ),
    SimpleControl(
        "lost_sale_penalty", "Missed-order penalty (lost sales)", "scale",
        ("costs.lost_sale_penalty.raw_component", "costs.lost_sale_penalty.subassembly",
         "costs.lost_sale_penalty.finished_good"),
        minimum=0.0, maximum=100.0,
        help="A multiplier on baseline's per-tier lost-sale penalties. Backorder penalties "
             "are a separate setting in Advanced.",
    ),
    SimpleControl(
        "transport_cost", "Transport cost", "scale",
        ("lanes.inbound_raw.cost_per_unit", "lanes.plant_to_dc.cost_per_unit",
         "lanes.dc_to_customer.cost_per_unit"),
        minimum=0.0, maximum=100.0,
        help="A multiplier on baseline's per-lane-family cost per unit.",
    ),
    SimpleControl(
        "fill_rate_target", "Fill-rate target", "value",
        ("service_targets.fill_rate_target",),
        minimum=0.0, maximum=1.0,
        help="The service promise the plan is measured against.",
    ),
)

SIMPLE_CONTROLS_BY_NAME = {control.name: control for control in SIMPLE_CONTROLS}

#: Names the generator ignores but a scenario file carries, so a saved custom
#: scenario reads like the four shipped ones.
DEFAULT_SHOCK_NAME = "custom_demand_spike"
DEFAULT_DISRUPTION_NAME = "custom_lane_disruption"


def default_optional_block(block: str, config: dict[str, Any]) -> dict[str, Any]:
    """Sensible starting values when a planner switches an optional block on.

    Decision 4 is why the windows run to the **end of the horizon**: the optimizer
    reads lane capacity at ``max(demand.period)``, so a window that stops short of
    it is a measured no-op. Defaulting to the end means the control works out of
    the box, and narrowing it is a deliberate act the validator then warns about.
    """
    horizon = int(get_value(config, "simulation.horizon_periods") or 52)
    start = max(1, horizon // 2)
    if block == "demand.shock":
        return {
            "name": DEFAULT_SHOCK_NAME,
            "start_period": start,
            "duration_periods": horizon - start + 1,
            "multiplier": 1.5,
        }
    if block == "lane_disruption":
        return {
            "name": DEFAULT_DISRUPTION_NAME,
            "lane_type": "inbound_raw",
            "affected_lane_count": 2,
            "start_period": start,
            "duration_periods": horizon - start + 1,
            "capacity_multiplier": 0.0,
            "lead_time_multiplier": 2.0,
        }
    raise ValueError(f"unknown optional block '{block}'")  # pragma: no cover


def expand_simple(
    simple: dict[str, Any],
    base: dict[str, Any],
) -> dict[str, Any]:
    """Simple-tier values -> raw setting overrides.

    A ``scale`` control multiplies baseline's concrete per-tier values, so the
    output is indistinguishable from someone having typed those numbers in
    Advanced. That is what keeps Simple and Advanced two views of one form
    rather than two competing sources of truth.
    """
    overrides: dict[str, Any] = {}
    for name, value in simple.items():
        control = SIMPLE_CONTROLS_BY_NAME.get(name)
        if control is None:
            raise KeyError(name)
        if control.kind == "value":
            # Left as-is deliberately: a "value" control writes straight through to
            # its setting, so validate_overrides applies that setting's own declared
            # type and range and produces the better message.
            overrides[control.writes[0]] = value
        elif control.kind == "scale":
            # A scale control is a multiplier on baseline's concrete values. A
            # non-numeric value has to become a refusal, not a ValueError escaping
            # to a 500 — guardrail 5 is "never a 500".
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(name)
            factor = float(value)
            for key in control.writes:
                current = get_value(base, key)
                overrides[key] = round(float(current) * factor, 6)
        elif control.kind == "group":
            if value is None:
                continue
            if not isinstance(value, dict):
                raise TypeError(name)
            block = "demand.shock" if name == "demand_spike" else "lane_disruption"
            # Only the fields the planner actually supplied. Anything omitted is
            # filled by ``complete_config`` from ``default_optional_block``, which
            # is where decision 4's run-to-the-end-of-the-horizon default lives.
            # Emitting the whole block here would make every auto-filled default
            # look like a deliberate edit — and would then warn the planner about
            # a no-op setting they never touched.
            for field_name, field_value in value.items():
                overrides[f"{block}.{field_name}"] = field_value
    return overrides


# ---------------------------------------------------------------------------
# complete-config synthesis
# ---------------------------------------------------------------------------


def complete_config(
    scenario_name: str,
    overrides: dict[str, Any] | None = None,
    simple: dict[str, Any] | None = None,
    seed: int = DEFAULT_SEED,
    description: str | None = None,
    base_scenario: str = BASE_SCENARIO,
) -> dict[str, Any]:
    """``baseline`` + the planner's edits -> a complete, ordinary scenario config.

    ``simple`` is expanded first, then ``overrides`` is applied on top, so an
    Advanced edit always wins over the Simple control that shares its setting.
    Optional blocks left untouched stay ``None``, exactly as ``baseline`` has them.
    """
    base = load_base_config(base_scenario)
    config = copy.deepcopy(base)
    config["scenario"] = scenario_name
    config["description"] = description or (
        f"Custom scenario built from {base_scenario} on this device."
    )
    # Decision 7: the seed travels with the config so a re-run reproduces the
    # objective to the cent. Ambient seeds are how reproducibility gets lost.
    config["random_seed_override"] = int(seed)

    resolved: dict[str, Any] = {}
    if simple:
        resolved.update(expand_simple(simple, base))
    if overrides:
        resolved.update(overrides)

    # A block referenced by any override must exist in full before that override
    # lands, or the generator would index into a partial dict.
    for block in ("demand.shock", "lane_disruption"):
        touched = any(key.startswith(f"{block}.") for key in resolved)
        if touched and not isinstance(get_value(config, block), dict):
            set_value(config, block, default_optional_block(block, config))

    for key, value in resolved.items():
        set_value(config, key, value)

    return config


def is_network_key(key: str) -> bool:
    return key in NETWORK_KEYS or key.startswith("network.")
