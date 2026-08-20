"""Print the settings ledger. Read-only; useful when reviewing the honest labelling."""

from __future__ import annotations

from src.scenario.ledger import (
    GROUPS,
    REACH_LABELS,
    SETTINGS,
    ledger_counts,
    settings_by_reach,
)


def main() -> int:
    counts = ledger_counts()
    print(f"{counts['total']} editable settings across {len(GROUPS)} groups\n")
    for group in GROUPS:
        rows = [setting for setting in SETTINGS if setting.group == group]
        print(f"{group}  ({len(rows)})")
        for setting in rows:
            bounds = ""
            if setting.minimum is not None and setting.maximum is not None:
                bounds = f"[{setting.minimum:g} .. {setting.maximum:g}]"
            elif setting.choices:
                bounds = "{" + ", ".join(setting.choices) + "}"
            flag = " " if setting.reaches_optimizer else "!"
            print(f"  {flag} {setting.key:52s} {setting.kind:7s} {bounds:26s} {setting.reach}")
        print()
    print("reach classes:")
    by_reach = settings_by_reach()
    for reach, label in REACH_LABELS.items():
        print(f"  {len(by_reach[reach]):3d}  {reach:34s} {label}")
    print(f"\n  {counts['cannot_change_the_answer']} settings cannot change the optimizer's answer "
          f"('!' above). They are excluded from the Simple tier and labelled in Advanced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
