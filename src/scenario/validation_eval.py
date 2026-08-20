"""Run the committed validation eval set. No GPU, no LLM, no disk writes.

``python3 -m src.scenario.validation_eval`` (or ``make scenario-eval``) reports one
line per case plus coverage of every refusal and warning class. Coverage is a
*failure* condition, not a note: a refusal class no case exercises is a guardrail
claim with no evidence behind it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from src.scenario.preview import build_preview
from src.scenario.validate import REFUSAL_CODES, WARNING_CODES

EVAL_PATH = Path(__file__).resolve().parent / "validation_eval.yaml"


def load_cases(path: Path = EVAL_PATH) -> list[dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases = payload.get("cases") or []
    if not cases:  # pragma: no cover - defensive
        raise ValueError(f"no cases in {path}")
    return cases


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one case against the real preview path."""
    preview = build_preview(
        case["name"],
        overrides=case.get("overrides"),
        simple=case.get("simple"),
        run_horizon=int(case.get("horizon", 8)),
        description=case.get("description_text"),
    )
    validation = preview["validation"]
    codes = [item["code"] for item in validation["refusals"]]
    warnings = [item["code"] for item in validation["warnings"]]
    reach = preview["capacity_reachability"]

    failures: list[str] = []
    expected_refusal = case.get("expect_refusal")
    if expected_refusal:
        if expected_refusal not in codes:
            failures.append(f"expected refusal '{expected_refusal}', got {codes or 'none'}")
    elif case.get("control"):
        if codes:
            failures.append(f"a control case was refused: {codes}")

    expected_warning = case.get("expect_warning")
    if expected_warning and expected_warning not in warnings:
        failures.append(f"expected warning '{expected_warning}', got {warnings or 'none'}")

    if "expect_reaches_optimizer" in case:
        want = bool(case["expect_reaches_optimizer"])
        if bool(reach["reaches_optimizer"]) != want:
            failures.append(f"expected reaches_optimizer={want}, got {reach['reaches_optimizer']}")

    if "expect_capacity_read_period" in case:
        want_period = int(case["expect_capacity_read_period"])
        if int(reach["capacity_read_period"]) != want_period:
            failures.append(
                f"expected capacity_read_period={want_period}, "
                f"got {reach['capacity_read_period']}"
            )

    # Guardrail 5: a refusal has to be a sentence a planner can act on, so every
    # message is required to be real prose rather than a code echoed back.
    for item in validation["refusals"]:
        message = item.get("message") or ""
        if len(message) < 25 or not message.strip().endswith((".", "!")):
            failures.append(f"refusal '{item['code']}' has no actionable message")

    return {
        "id": case["id"],
        "description": case.get("description", "").strip(),
        "passed": not failures,
        "failures": failures,
        "refusals": codes,
        "warnings": warnings,
        "reaches_optimizer": reach["reaches_optimizer"],
        "capacity_read_period": reach["capacity_read_period"],
        "control": bool(case.get("control")),
    }


def run_all(path: Path = EVAL_PATH) -> dict[str, Any]:
    cases = load_cases(path)
    results = [run_case(case) for case in cases]

    seen_refusals = {code for case in cases if case.get("expect_refusal")
                     for code in [case["expect_refusal"]]}
    seen_warnings = {case["expect_warning"] for case in cases if case.get("expect_warning")}
    uncovered_refusals = sorted(set(REFUSAL_CODES) - seen_refusals)
    uncovered_warnings = sorted(set(WARNING_CODES) - seen_warnings)

    passed = sum(1 for item in results if item["passed"])
    return {
        "cases": results,
        "passed": passed,
        "total": len(results),
        "controls": sum(1 for item in results if item["control"]),
        "coverage": {
            "refusal_codes": len(REFUSAL_CODES),
            "refusal_codes_exercised": len(seen_refusals),
            "uncovered_refusal_codes": uncovered_refusals,
            "warning_codes": len(WARNING_CODES),
            "warning_codes_exercised": len(seen_warnings),
            "uncovered_warning_codes": uncovered_warnings,
            "complete": not uncovered_refusals and not uncovered_warnings,
        },
        "ok": passed == len(results) and not uncovered_refusals and not uncovered_warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the raw report")
    args = parser.parse_args()
    report = run_all()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for item in report["cases"]:
            mark = "PASS" if item["passed"] else "FAIL"
            tag = " [control]" if item["control"] else ""
            print(f"{mark} {item['id']}{tag}  {item['description'][:88]}")
            for failure in item["failures"]:
                print(f"       -> {failure}")
        coverage = report["coverage"]
        print(
            f"\n{report['passed']}/{report['total']} cases passed "
            f"({report['controls']} controls). "
            f"Refusal classes exercised {coverage['refusal_codes_exercised']}/"
            f"{coverage['refusal_codes']}; warnings "
            f"{coverage['warning_codes_exercised']}/{coverage['warning_codes']}."
        )
        if not coverage["complete"]:
            print(f"UNCOVERED refusals: {coverage['uncovered_refusal_codes']}")
            print(f"UNCOVERED warnings: {coverage['uncovered_warning_codes']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
