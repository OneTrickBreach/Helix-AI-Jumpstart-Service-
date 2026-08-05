"""Run the committed parser evaluation set.

``--llm`` (default)  deterministic rules first, the model where they fall short.
``--no-llm``         deterministic rules only. Fast, fully reproducible, and part
                     of ``make test``.

Exits non-zero on any failure and writes ``benchmark/parse-eval-phase2.json``.
Nothing here executes a perturbation — parsing and running are deliberately
separate — and one of the assertions below is that every parse says so.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from src.bench.profiler import write_json
from src.chat.intent import parse_intent
from src.ingest.state import ScenarioState, load_scenario_state


QUESTIONS_PATH = Path(__file__).resolve().parent / "parse_eval_questions.yaml"


def load_questions(path: Path | str = QUESTIONS_PATH) -> list[dict[str, Any]]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    questions = payload.get("questions") or []
    ids = [item["id"] for item in questions]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate question ids in the parser evaluation set")
    return questions


def check_parse(case: dict[str, Any], result: Any) -> list[dict[str, Any]]:
    expect = case.get("expect", {}) or {}
    checks: list[dict[str, Any]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    if "outcome" in expect:
        record("outcome", result.outcome == expect["outcome"], f"got {result.outcome}, want {expect['outcome']}")
    if "reason" in expect:
        record("reason", result.reason == expect["reason"], f"got {result.reason}, want {expect['reason']}")
    if "parser" in expect:
        record("parser", result.parser == expect["parser"], f"got {result.parser}, want {expect['parser']}")

    perturbation = result.perturbation or {}
    if "kind" in expect:
        record("kind", perturbation.get("kind") == expect["kind"], f"got {perturbation.get('kind')}")
    for field, wanted in (expect.get("fields") or {}).items():
        actual = perturbation.get(field)
        if isinstance(wanted, float) or isinstance(actual, float):
            ok = actual is not None and abs(float(actual) - float(wanted)) < 1e-6
        else:
            ok = actual == wanted
        record(f"field:{field}", ok, f"got {actual!r}, want {wanted!r}")

    impact = result.impact or {}
    if "reaches_optimizer" in expect:
        record(
            "reaches_optimizer",
            impact.get("reaches_optimizer") is expect["reaches_optimizer"],
            f"got {impact.get('reaches_optimizer')}, want {expect['reaches_optimizer']}",
        )
    if "lanes_affected" in expect:
        record(
            "lanes_affected",
            impact.get("lanes_affected_count") == expect["lanes_affected"],
            f"got {impact.get('lanes_affected_count')}, want {expect['lanes_affected']}",
        )

    message = (result.message or "").lower()
    for needle in expect.get("contains", []) or []:
        record(f"contains:{needle}", str(needle).lower() in message)

    if "warns" in expect:
        warnings = " ".join((result.confirmation or {}).get("warnings", [])).lower()
        record("warns", str(expect["warns"]).lower() in warnings, f"warnings: {warnings[:120]}")

    # Invariants that hold for every case, whatever the outcome.
    record("never_executable", result.executable is False)
    record("beta_labelled", result.beta is True and result.label == "BETA")
    if result.outcome == "parsed":
        card = result.confirmation or {}
        record("has_confirmation_card", bool(card.get("reading")) and card.get("requires_confirmation") is True)
        record("card_needs_confirmation", card.get("requires_confirmation") is True)
    else:
        record("no_perturbation_without_parse", not result.perturbation)
    return checks


def run_eval(use_llm: bool = True, questions_path: Path | str = QUESTIONS_PATH) -> dict[str, Any]:
    cases = load_questions(questions_path)
    states: dict[str, ScenarioState] = {}
    results: list[dict[str, Any]] = []

    skipped: list[str] = []
    for case in cases:
        if case.get("requires") == "llm" and not use_llm:
            # Only resolvable with the model. Skipping is honest; failing would
            # say the parser is broken when the mode simply excludes the model.
            skipped.append(case["id"])
            continue
        scenario = case["scenario"]
        if scenario not in states:
            states[scenario] = load_scenario_state(scenario)
        result = parse_intent(
            case["question"],
            scenario,
            state=states[scenario],
            llm=None if use_llm else False,
        )
        checks = check_parse(case, result)
        results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "scenario": scenario,
                "question": case["question"],
                "passed": all(check["ok"] for check in checks),
                "checks": checks,
                "outcome": result.outcome,
                "reason": result.reason,
                "parser": result.parser,
                "message": result.message,
                "perturbation": result.perturbation,
                "impact": result.impact,
                "warnings": (result.confirmation or {}).get("warnings", []),
            }
        )

    by_category: dict[str, dict[str, int]] = {}
    for item in results:
        bucket = by_category.setdefault(item["category"], {"passed": 0, "total": 0})
        bucket["total"] += 1
        bucket["passed"] += int(item["passed"])

    llm_parses = [item["id"] for item in results if item["parser"] == "llm"]
    failed = [item["id"] for item in results if not item["passed"]]
    # Coverage, not correctness: in LLM mode the set must actually exercise the
    # model-assisted path. It stopped doing so once the deterministic rules were
    # sharpened, which would have left the fallback silently untested.
    coverage_gap = use_llm and not llm_parses
    if coverage_gap:
        failed = [*failed, "COVERAGE:no-llm-assisted-parse"]

    return {
        "mode": "llm" if use_llm else "deterministic",
        "questions": len(results),
        "skipped_requires_llm": skipped,
        "passed": sum(1 for item in results if item["passed"]),
        "failed": failed,
        "llm_assisted_parses": llm_parses,
        "by_category": by_category,
        "by_outcome": {
            outcome: sum(1 for item in results if item["outcome"] == outcome)
            for outcome in sorted({item["outcome"] for item in results})
        },
        "parsed_by_parser": {
            parser: sum(1 for item in results if item["parser"] == parser)
            for parser in sorted({item["parser"] for item in results})
        },
        "unreachable_perturbations_flagged": [
            item["id"]
            for item in results
            if (item["impact"] or {}).get("reaches_optimizer") is False
        ],
        "execution_paths_exercised": 0,
        "results": results,
    }


def print_summary(summary: dict[str, Any]) -> None:
    print(f"\nParser eval — mode={summary['mode']}  {summary['passed']}/{summary['questions']} passed\n")
    print(f"{'id':4s} {'category':19s} {'outcome':11s} {'parser':14s} ok  question")
    print("-" * 116)
    for item in summary["results"]:
        mark = "✓ " if item["passed"] else "✗ "
        question = item["question"] or "(empty)"
        print(f"{item['id']:4s} {item['category']:19s} {item['outcome']:11s} {item['parser']:14s} {mark} {question[:44]}")
        if not item["passed"]:
            for check in item["checks"]:
                if not check["ok"]:
                    print(f"       FAILED {check['check']}: {check['detail']}")
            print(f"       message: {item['message'][:200]}")
    print("\nby category:", json.dumps(summary["by_category"], sort_keys=True))
    print("by outcome: ", json.dumps(summary["by_outcome"], sort_keys=True))
    print("by parser:  ", json.dumps(summary["parsed_by_parser"], sort_keys=True))
    print("parses flagged as unable to move the plan:", summary["unreachable_perturbations_flagged"] or "none")
    print("model-assisted parses:", summary.get("llm_assisted_parses") or "none")
    if summary.get("skipped_requires_llm"):
        print("skipped (require the model):", summary["skipped_requires_llm"])
    print("execution paths exercised:", summary["execution_paths_exercised"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-llm", dest="use_llm", action="store_false", help="deterministic rules only")
    parser.add_argument("--json-out", default=None)
    parser.set_defaults(use_llm=True)
    args = parser.parse_args()

    summary = run_eval(use_llm=args.use_llm)
    print_summary(summary)
    name = args.json_out or f"parse-eval-phase2-{summary['mode']}.json"
    print(f"\nartifact: {write_json(summary, name)}")
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
