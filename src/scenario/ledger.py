"""The settings ledger: what each of the 59 scenario settings can actually change.

Iteration 6a guardrail 1 — *no no-op controls*. A control that cannot change the
optimizer's answer must not be presented as if it can. This module is where that
claim is made precise, and :mod:`tests.test_iteration6a_ledger` is where it is
mechanically enforced.

Each :class:`Setting` carries a **declared** ``reach``. The declaration is not
trusted: two independent derivations reproduce it from the running system.

``derive_setting_targets``
    Builds the nine tables twice — once as-is, once with one setting moved — and
    diffs them. Answers "which CSV column does this setting write?" without
    reading the generator's source.

``derive_optimizer_reads`` (in ``tests/test_iteration6a_ledger.py``)
    Perturbs one column of a loaded ``ScenarioState`` and re-runs the optimizer.
    If the objective moves, the column is read. Answers "does the optimizer read
    this column?" behaviourally, rather than by grepping for a literal — which
    cannot work, because ``capacity_units_per_period`` is a column on *both*
    ``nodes`` (never read) and ``lanes`` (read). It lives in the test because it
    runs the optimizer, and Phase 1 ships no execution path.

A setting is therefore inert exactly when every column it writes is unread, and
the test asserting *derived == declared* is what fails when a label becomes a lie.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from src.scenario.tables import build_tables, formatted_columns

# --- reach classes ---------------------------------------------------------

#: Moves the optimizer's answer whenever it changes.
UNCONDITIONAL = "unconditional"
#: Written into ``lane_periods`` for a *window* of periods. The optimizer reads
#: lane capacity at exactly one period, so whether this reaches the answer
#: depends on whether the window covers that period. See §1.3 and decision 4.
CONDITIONAL = "conditional_on_capacity_window"
#: Lands in a column nothing downstream reads. Still visible on the dataset view.
INERT = "recorded_not_read"
#: Never written to any table at all — a name the generator ignores.
LABEL_ONLY = "label_only"

#: The exact wording decision 15 requires in the Advanced tier. Reused verbatim
#: by the API so the UI and the payload cannot drift apart.
INERT_LABEL = "recorded in the dataset, not read by the optimizer"
LABEL_ONLY_LABEL = "a name for this scenario's disruption — not written to any table"

REACH_LABELS = {
    UNCONDITIONAL: "changes the optimizer's answer",
    CONDITIONAL: "changes the answer only if the window covers the capacity read period",
    INERT: INERT_LABEL,
    LABEL_ONLY: LABEL_ONLY_LABEL,
}


@dataclass(frozen=True)
class Setting:
    """One editable scenario setting."""

    key: str
    group: str
    kind: str  # "int" | "float" | "str" | "range2"
    label: str
    reach: str
    writes: tuple[tuple[str, str], ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()
    note: str = ""

    @property
    def path(self) -> tuple[str, ...]:
        return tuple(self.key.split("."))

    @property
    def reaches_optimizer(self) -> bool:
        """``False`` for the settings that cannot move the answer at all.

        ``CONDITIONAL`` is ``True`` here: it *can* reach the optimizer. Whether a
        particular window does is a per-configuration question, answered by
        :func:`src.scenario.validate.capacity_reachability`.
        """
        return self.reach in (UNCONDITIONAL, CONDITIONAL)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "key": self.key,
            "group": self.group,
            "kind": self.kind,
            "label": self.label,
            "reach": self.reach,
            "reach_label": REACH_LABELS[self.reach],
            "reaches_optimizer": self.reaches_optimizer,
            "writes": [f"{table}.{column}" for table, column in self.writes],
        }
        if self.minimum is not None:
            payload["minimum"] = self.minimum
        if self.maximum is not None:
            payload["maximum"] = self.maximum
        if self.choices:
            payload["choices"] = list(self.choices)
        if self.note:
            payload["note"] = self.note
        return payload


_NODES_NOT_READ = (
    "lands in nodes.csv, which the forecast and the optimizer never read (it is "
    "drawn on the dataset view)"
)
_LANE_COLUMN_NOT_READ = "the column is written to lanes.csv but never consumed downstream"

SETTINGS: tuple[Setting, ...] = (
    # --- capacity (7) ------------------------------------------------------
    Setting("capacity.capacity_tightness", "capacity", "float",
            "Capacity tightness", UNCONDITIONAL,
            writes=(("lanes", "capacity_units_per_period"),
                    ("lane_periods", "effective_capacity_units")),
            minimum=0.4, maximum=3.0,
            note="scales lane capacity at EVERY period, including the one the optimizer reads"),
    Setting("capacity.plant_storage_periods", "capacity", "float",
            "Plant storage (periods of cover)", INERT,
            writes=(("nodes", "storage_capacity_units"),),
            minimum=0.5, maximum=24.0, note=_NODES_NOT_READ),
    Setting("capacity.supplier_capacity_units_per_period", "capacity", "int",
            "Supplier capacity per period", INERT,
            writes=(("nodes", "capacity_units_per_period"),),
            minimum=1, maximum=10_000_000, note=_NODES_NOT_READ),
    Setting("capacity.supplier_storage_units", "capacity", "int",
            "Supplier storage", INERT,
            writes=(("nodes", "storage_capacity_units"),),
            minimum=1, maximum=100_000_000, note=_NODES_NOT_READ),
    Setting("capacity.dc_throughput_units_per_period", "capacity", "int",
            "DC throughput per period", INERT,
            writes=(("nodes", "capacity_units_per_period"),),
            minimum=1, maximum=10_000_000,
            note="reads like the most intuitive control on the panel and does nothing: it "
                 + _NODES_NOT_READ),
    Setting("capacity.dc_storage_units", "capacity", "int",
            "DC storage", INERT,
            writes=(("nodes", "storage_capacity_units"),),
            minimum=1, maximum=100_000_000, note=_NODES_NOT_READ),
    Setting("capacity.customer_storage_units", "capacity", "int",
            "Customer storage", INERT,
            writes=(("nodes", "storage_capacity_units"),),
            minimum=0, maximum=10_000_000, note=_NODES_NOT_READ),
    # --- costs (12) --------------------------------------------------------
    *(
        Setting(f"costs.{cost}.{tier}", "costs", "float",
                f"{label} — {tier.replace('_', ' ')}", UNCONDITIONAL,
                writes=((("skus", column),)),
                minimum=0.0, maximum=maximum)
        for cost, column, label, maximum in (
            ("holding_cost", "unit_holding_cost", "Inventory holding cost", 1_000.0),
            ("ordering_cost", "ordering_cost", "Ordering cost", 100_000.0),
            ("backorder_penalty", "backorder_penalty", "Backorder penalty", 100_000.0),
            ("lost_sale_penalty", "lost_sale_penalty", "Lost-sale penalty", 100_000.0),
        )
        for tier in ("raw_component", "subassembly", "finished_good")
    ),
    # --- demand (11) -------------------------------------------------------
    Setting("demand.base_units_per_customer_period", "demand", "int",
            "Demand level (units per customer per period)", UNCONDITIONAL,
            writes=(("demand", "quantity_units"),), minimum=1, maximum=1_000_000),
    Setting("demand.seasonality_amplitude", "demand", "float",
            "Seasonality amplitude", UNCONDITIONAL,
            writes=(("demand", "quantity_units"), ("demand", "seasonal_factor")),
            minimum=0.0, maximum=1.0),
    Setting("demand.trend_per_period", "demand", "float",
            "Trend per period", UNCONDITIONAL,
            writes=(("demand", "quantity_units"), ("demand", "trend_factor")),
            minimum=-0.05, maximum=0.05),
    Setting("demand.noise_std", "demand", "float",
            "Demand noise (std dev)", UNCONDITIONAL,
            writes=(("demand", "quantity_units"), ("demand", "noise_multiplier")),
            minimum=0.0, maximum=1.0),
    Setting("demand.lump_probability", "demand", "float",
            "Lumpiness probability", UNCONDITIONAL,
            writes=(("demand", "quantity_units"), ("demand", "lump_multiplier")),
            minimum=0.0, maximum=1.0),
    Setting("demand.lump_multiplier_range", "demand", "range2",
            "Lumpiness multiplier range", UNCONDITIONAL,
            writes=(("demand", "quantity_units"), ("demand", "lump_multiplier")),
            minimum=1.0, maximum=10.0),
    Setting("demand.periods_per_year", "demand", "int",
            "Periods per year", UNCONDITIONAL,
            writes=(("demand", "quantity_units"), ("demand", "seasonal_factor")),
            minimum=1, maximum=366),
    Setting("demand.shock.name", "demand", "str",
            "Demand spike name", LABEL_ONLY,
            note="the generator reads only start_period, duration_periods and multiplier "
                 "from this block; the name is never written to any table"),
    Setting("demand.shock.start_period", "demand", "int",
            "Demand spike — first period", UNCONDITIONAL,
            writes=(("demand", "quantity_units"), ("demand", "shock_multiplier")),
            minimum=1, maximum=520),
    Setting("demand.shock.duration_periods", "demand", "int",
            "Demand spike — periods", UNCONDITIONAL,
            writes=(("demand", "quantity_units"), ("demand", "shock_multiplier")),
            minimum=1, maximum=520),
    Setting("demand.shock.multiplier", "demand", "float",
            "Demand spike — multiplier", UNCONDITIONAL,
            writes=(("demand", "quantity_units"), ("demand", "shock_multiplier")),
            minimum=0.0, maximum=10.0),
    # --- lanes (18) --------------------------------------------------------
    *(
        Setting(f"lanes.{family}.{param}", "lanes", kind,
                f"{family.replace('_', ' ')} — {label}", reach,
                writes=(("lane_periods", column),) if column.startswith("effective_")
                       else (("lanes", column),),
                minimum=minimum, maximum=maximum,
                note=note)
        for family in ("inbound_raw", "plant_to_dc", "dc_to_customer")
        for param, column, kind, label, reach, minimum, maximum, note in (
            ("lead_time_mean_days", "effective_lead_time_mean_days", "float",
             "mean lead time (days)", UNCONDITIONAL, 0.1, 365.0, ""),
            ("lead_time_std_days", "lead_time_std_days", "float",
             "lead-time variability (days)", INERT, 0.0, 365.0, _LANE_COLUMN_NOT_READ),
            ("cost_per_unit", "lane_cost_per_unit", "float",
             "transport cost per unit", UNCONDITIONAL, 0.0, 10_000.0, ""),
            ("distance_km", "distance_km", "int",
             "distance (km)", UNCONDITIONAL, 1, 40_000, ""),
            ("transport_cost_per_km", "transport_cost_per_km", "float",
             "transport cost per km", UNCONDITIONAL, 0.0, 1_000.0, ""),
            ("co2_kg_per_unit", "co2_kg_per_unit", "float",
             "CO2 per unit (kg)", INERT, 0.0, 10_000.0, _LANE_COLUMN_NOT_READ),
        )
    ),
    # --- lane_disruption (7) ----------------------------------------------
    Setting("lane_disruption.name", "lane_disruption", "str",
            "Lane disruption name", INERT,
            writes=(("lane_periods", "disruption_code"),),
            note="written to lane_periods.disruption_code, which the optimizer never reads; "
                 "the dataset view uses it to name the disruption"),
    Setting("lane_disruption.lane_type", "lane_disruption", "str",
            "Lane disruption — which lanes", CONDITIONAL,
            writes=(("lane_periods", "effective_capacity_units"),),
            choices=("inbound_raw", "plant_to_dc", "dc_to_customer")),
    Setting("lane_disruption.affected_lane_count", "lane_disruption", "int",
            "Lane disruption — how many lanes", CONDITIONAL,
            writes=(("lane_periods", "effective_capacity_units"),), minimum=0, maximum=10_000),
    Setting("lane_disruption.start_period", "lane_disruption", "int",
            "Lane disruption — first period", CONDITIONAL,
            writes=(("lane_periods", "effective_capacity_units"),), minimum=1, maximum=520),
    Setting("lane_disruption.duration_periods", "lane_disruption", "int",
            "Lane disruption — periods", CONDITIONAL,
            writes=(("lane_periods", "effective_capacity_units"),), minimum=1, maximum=520),
    Setting("lane_disruption.capacity_multiplier", "lane_disruption", "float",
            "Lane disruption — capacity multiplier", CONDITIONAL,
            writes=(("lane_periods", "effective_capacity_units"),), minimum=0.0, maximum=10.0),
    Setting("lane_disruption.lead_time_multiplier", "lane_disruption", "float",
            "Lane disruption — lead-time multiplier", CONDITIONAL,
            writes=(("lane_periods", "effective_lead_time_mean_days"),), minimum=0.0, maximum=10.0),
    # --- service_targets (3) ----------------------------------------------
    Setting("service_targets.fill_rate_target", "service_targets", "float",
            "Fill-rate target", UNCONDITIONAL,
            writes=(("service_targets", "fill_rate_target"),), minimum=0.0, maximum=1.0),
    Setting("service_targets.days_inventory_target", "service_targets", "float",
            "Days-of-inventory target", UNCONDITIONAL,
            writes=(("initial_inventory", "on_hand_units"),
                    ("service_targets", "days_inventory_target")),
            minimum=0.0, maximum=365.0,
            note="reaches the optimizer by sizing initial on-hand inventory, NOT through the "
                 "service_targets column of the same name — which is never read"),
    Setting("service_targets.criticality_tier", "service_targets", "str",
            "Criticality tier", INERT,
            writes=(("service_targets", "criticality_tier"),),
            note="only fill_rate_target and days_inventory_target are read from "
                 "service_targets.csv"),
    # --- simulation (1) ----------------------------------------------------
    Setting("simulation.horizon_periods", "simulation", "int",
            "History length (periods)", UNCONDITIONAL,
            writes=(("demand", "__rows__"), ("lane_periods", "__rows__")),
            minimum=8, maximum=520,
            note="also MOVES the period at which the optimizer reads lane capacity, because "
                 "that period is max(demand.period)"),
)

SETTINGS_BY_KEY: dict[str, Setting] = {setting.key: setting for setting in SETTINGS}

#: The 7 groups the 59 settings fall into. ``network`` is deliberately absent —
#: it is the dataset layer and belongs to Iteration 6b (§1.6, decision 6).
GROUPS = ("simulation", "demand", "capacity", "lanes", "lane_disruption", "costs", "service_targets")

#: Settings that exist in a scenario file but are NOT editable scenario settings.
#: ``random_seed_override`` is the seed (decision 7), handled separately so a
#: saved scenario is reproducible; the other two are metadata.
NON_SETTING_KEYS = ("scenario", "description", "random_seed_override")

#: Excluded from 6a: changing these is a custom *dataset*, not a custom scenario.
NETWORK_KEYS = (
    "network.suppliers", "network.plants", "network.lines_per_plant",
    "network.distribution_centers", "network.customers", "network.finished_goods",
    "network.subassemblies_per_finished_good", "network.raw_components_per_subassembly",
)


def settings_by_reach() -> dict[str, list[Setting]]:
    out: dict[str, list[Setting]] = {UNCONDITIONAL: [], CONDITIONAL: [], INERT: [], LABEL_ONLY: []}
    for setting in SETTINGS:
        out[setting.reach].append(setting)
    return out


def ledger_counts() -> dict[str, int]:
    counts = {reach: len(items) for reach, items in settings_by_reach().items()}
    counts["total"] = len(SETTINGS)
    counts["cannot_change_the_answer"] = counts[INERT] + counts[LABEL_ONLY]
    return counts


# ---------------------------------------------------------------------------
# reading / writing a setting inside a config dict
# ---------------------------------------------------------------------------


def get_value(config: dict[str, Any], key: str) -> Any:
    node: Any = config
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def set_value(config: dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    node = config
    for part in parts[:-1]:
        existing = node.get(part)
        if not isinstance(existing, dict):
            existing = {}
            node[part] = existing
        node = existing
    node[parts[-1]] = value


def probe_values(setting: Setting, current: Any) -> list[Any]:
    """Several different, in-range values for ``setting``.

    The derivation takes the **union** of what each probe changes, which makes the
    ledger independent of probe choice. That is not fussiness: the optional blocks
    default to running to the end of the horizon (decision 4), so a probe that only
    *lengthens* ``duration_periods`` extends a window past data that does not exist
    and changes nothing — making a load-bearing setting look inert. Probing in both
    directions removes the whole class of false "no-op" readings.

    Every candidate stays inside the declared range: a probe that overflows a bound
    would be testing behaviour the validator refuses anyway.
    """
    if setting.kind == "str":
        return [c for c in (setting.choices or ("ledger-probe", "ledger-probe-2")) if c != current]
    if setting.kind == "range2":
        low, high = (float(current[0]), float(current[1])) if current else (1.0, 2.0)
        lo = float(setting.minimum) if setting.minimum is not None else 1.0
        hi = float(setting.maximum) if setting.maximum is not None else 10.0
        out = []
        for candidate in ([low, min(hi, high + 1.3)], [low, max(lo, min(high - 0.5, hi))],
                          [max(lo, low + 0.4), high]):
            pair = [round(candidate[0], 6), round(candidate[1], 6)]
            if pair[0] <= pair[1] and pair != current and pair not in out:
                out.append(pair)
        return out

    minimum = setting.minimum
    maximum = setting.maximum
    numeric = float(current) if isinstance(current, (int, float)) else 0.0
    out: list[Any] = []
    # Downward first: for a window that already runs to the end of the horizon,
    # shrinking it is the only direction that reveals anything.
    for candidate in (numeric * 0.5 - 1.0, numeric * 1.4 + 1.0, numeric + 1.0, numeric - 1.0,
                      minimum, maximum):
        if candidate is None:
            continue
        value = float(candidate)
        if minimum is not None:
            value = max(float(minimum), value)
        if maximum is not None:
            value = min(float(maximum), value)
        if setting.kind == "int":
            value = int(round(value))
        if value != current and value not in out:
            out.append(value)
    if not out:
        raise ValueError(f"no in-range probe value for {setting.key}")  # pragma: no cover
    return out


# ---------------------------------------------------------------------------
# derivation 1: which columns does each setting write?
# ---------------------------------------------------------------------------


def derive_setting_targets(
    config: dict[str, Any],
    seed: int = 12345,
    keys: tuple[str, ...] | None = None,
) -> dict[str, set[tuple[str, str]]]:
    """``setting key -> the (table, column) pairs its value actually changes``.

    Row-count changes are reported as the pseudo-column ``__rows__``: a setting
    that adds periods changes what the pipeline reads even though no single
    column's value differs in place.

    ``config`` must be **complete** — every optional block present — or a setting
    inside an absent block would look like it writes nothing.
    """
    base_tables = build_tables(config, seed)
    base_columns = formatted_columns(base_tables)
    base_heights = {table: len(rows) for table, rows in base_tables.items()}

    targets: dict[str, set[tuple[str, str]]] = {}
    for setting in SETTINGS:
        if keys is not None and setting.key not in keys:
            continue
        changed: set[tuple[str, str]] = set()
        current = get_value(config, setting.key)
        for probe in probe_values(setting, current):
            variant = copy.deepcopy(config)
            set_value(variant, setting.key, probe)
            variant_tables = build_tables(variant, seed)
            rows_changed = {
                table for table, rows in variant_tables.items()
                if len(rows) != base_heights[table]
            }
            changed.update((table, "__rows__") for table in rows_changed)
            for target, values in formatted_columns(variant_tables).items():
                if target[0] in rows_changed:
                    # A different row count makes a positional column diff
                    # meaningless; the row-count change is the finding.
                    continue
                if values != base_columns[target]:
                    changed.add(target)
        targets[setting.key] = changed
    return targets


# ---------------------------------------------------------------------------
# derivation 2 (which columns the optimizer reads) lives in
# tests/test_iteration6a_ledger.py on purpose: it perturbs a column and re-runs
# the optimizer, and Phase 1 must contain no execution path. Keeping the ablation
# in the test is also the honest place for it — it is the check, not the product.
# ---------------------------------------------------------------------------


def classify(
    targets: dict[str, set[tuple[str, str]]],
    reads: dict[tuple[str, str], bool],
) -> dict[str, str]:
    """The reach each setting *earns* from the two derivations above."""
    derived: dict[str, str] = {}
    for key, written in sorted(targets.items()):
        setting = SETTINGS_BY_KEY[key]
        if not written:
            derived[key] = LABEL_ONLY
        elif any(reads.get(target, False) for target in written):
            derived[key] = CONDITIONAL if setting.group == "lane_disruption" else UNCONDITIONAL
        else:
            derived[key] = INERT
    return derived
