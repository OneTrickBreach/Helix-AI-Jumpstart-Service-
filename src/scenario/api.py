"""The read-only payload describing the custom-scenario form.

Separate from :mod:`src.scenario.preview` because it depends on nothing but the
ledger — no config, no validation, no filesystem — so the API can serve the
schema without resolving anybody's edits.
"""

from __future__ import annotations

from typing import Any

from src.scenario.ledger import (
    GROUPS,
    INERT_LABEL,
    LABEL_ONLY,
    INERT,
    REACH_LABELS,
    SETTINGS,
    ledger_counts,
    settings_by_reach,
)
from src.scenario.synthesize import (
    BASE_SCENARIO,
    CANONICAL_SCENARIOS,
    DEFAULT_SEED,
    SIMPLE_CONTROLS,
)
from src.scenario.validate import CUSTOM_PREFIX, SLUG_MAX_LENGTH, SLUG_PATTERN


def custom_settings_payload() -> dict[str, Any]:
    by_reach = settings_by_reach()
    cannot_change = [*by_reach[INERT], *by_reach[LABEL_ONLY]]
    return {
        "base_scenario": BASE_SCENARIO,
        "default_seed": DEFAULT_SEED,
        "name_rules": {
            "prefix": CUSTOM_PREFIX,
            "pattern": SLUG_PATTERN.pattern,
            "max_length": SLUG_MAX_LENGTH,
            "reserved": list(CANONICAL_SCENARIOS),
            "note": "A custom scenario is stored as 'custom-<name>'. The four recorded "
                    "benchmark scenarios are reserved and cannot be overwritten.",
        },
        "groups": list(GROUPS),
        "settings": [setting.as_dict() for setting in SETTINGS],
        "simple_controls": [control.as_dict() for control in SIMPLE_CONTROLS],
        "reach_labels": dict(REACH_LABELS),
        "ledger": ledger_counts(),
        # Decision 15: these are shown in Advanced under an explicit heading, and
        # never in Simple. Handing the UI the list means the labelling cannot be
        # forgotten on the front end.
        "cannot_change_the_answer": {
            "heading": INERT_LABEL,
            "settings": [setting.key for setting in cannot_change],
            "count": len(cannot_change),
        },
        "excluded_from_6a": {
            "keys": ["network.*"],
            "reason": "Changing how many suppliers, plants, distribution centers or "
                      "customers exist is a custom dataset, which is Iteration 6b.",
        },
        "writes_nothing": True,
        "runs_nothing": True,
    }
