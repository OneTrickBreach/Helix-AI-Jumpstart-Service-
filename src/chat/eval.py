"""Run the committed evaluation set against the read-only Q&A layer.

Two modes, and both matter:

``--llm`` (default)   the real on-device Nemotron. This is the honest test of the
                      shipped path, and the only way to know whether the model
                      actually quotes the facts it was given.
``--no-llm``          the deterministic template path. Fast, reproducible, and run
                      as part of ``make test`` so a regression in routing or fact
                      selection fails the suite rather than waiting for a demo.

Exits non-zero on any failure and writes ``benchmark/chat-eval-phase1.json``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from src.bench.profiler import write_json
from src.chat.answer import answer_question
from src.chat.facts import FactBundle, build_fact_bundle
from src.chat.grounding import extract_numbers, numbers_match


QUESTIONS_PATH = Path(__file__).resolve().parent / "eval_questions.yaml"


def load_questions(path: Path | str = QUESTIONS_PATH) -> list[dict[str, Any]]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    questions = payload.get("questions") or []
    ids = [item["id"] for item in questions]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate question ids in the evaluation set")
    return questions


def check_answer(case: dict[str, Any], result: Any) -> list[dict[str, Any]]:
    """Every expectation for one case, each as an independent pass/fail."""
    expect = case.get("expect", {}) or {}
    checks: list[dict[str, Any]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    if "route" in expect:
        record("route", result.route == expect["route"], f"got {result.route}, want {expect['route']}")
    if "reason" in expect:
        record("reason", result.reason == expect["reason"], f"got {result.reason}, want {expect['reason']}")

    retrieved = [item["fact_id"] for item in result.facts_used]
    if "top_fact" in expect:
        top = retrieved[0] if retrieved else "<none>"
        record("top_fact", top == expect["top_fact"], f"got {top}, want {expect['top_fact']}")
    if "any_fact" in expect:
        wanted = set(expect["any_fact"])
        hit = sorted(wanted.intersection(retrieved))
        record("any_fact", bool(hit), f"matched {hit or 'nothing'} from {expect['any_fact']}")

    answer_lower = result.answer.lower()
    for needle in expect.get("contains", []) or []:
        record(f"contains:{needle}", str(needle).lower() in answer_lower)
    for needle in expect.get("excludes", []) or []:
        record(f"excludes:{needle}", str(needle).lower() not in answer_lower)
    alternatives = expect.get("contains_any") or []
    if alternatives:
        hit = [needle for needle in alternatives if str(needle).lower() in answer_lower]
        record("contains_any", bool(hit), f"matched {hit or 'nothing'} from {alternatives}")

    stated = [value for _, value in extract_numbers(result.answer)]
    for wanted in expect.get("numbers", []) or []:
        found = any(numbers_match(value, float(wanted)) for value in stated)
        record(f"states_number:{wanted}", found, f"answer states {stated[:12]}")
    number_alternatives = expect.get("numbers_any") or []
    if number_alternatives:
        hit = [
            wanted
            for wanted in number_alternatives
            if any(numbers_match(value, float(wanted)) for value in stated)
        ]
        record("states_number_any", bool(hit), f"answer states {stated[:12]}, wanted one of {number_alternatives}")

    if expect.get("grounded", True):
        grounding = result.grounding or {}
        record(
            "no_ungrounded_numbers",
            int(grounding.get("numbers_ungrounded", 0) or 0) == 0,
            f"ungrounded: {grounding.get('ungrounded_tokens')}",
        )

    record("answer_not_empty", bool(result.answer.strip()))
    return checks


def run_eval(use_llm: bool = True, questions_path: Path | str = QUESTIONS_PATH) -> dict[str, Any]:
    cases = load_questions(questions_path)
    bundles: dict[str, FactBundle] = {}
    results: list[dict[str, Any]] = []

    for case in cases:
        scenario = case["scenario"]
        if scenario not in bundles:
            bundles[scenario] = build_fact_bundle(scenario)
        result = answer_question(
            case["question"],
            scenario,
            bundle=bundles[scenario],
            llm=None if use_llm else False,
        )
        checks = check_answer(case, result)
        results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "scenario": scenario,
                "question": case["question"],
                "passed": all(check["ok"] for check in checks),
                "checks": checks,
                "route": result.route,
                "reason": result.reason,
                "answer_source": result.answer_source,
                "answer": result.answer,
                "citations": [item["source"] for item in result.citations],
                "facts_used": [item["fact_id"] for item in result.facts_used],
                "grounding": result.grounding,
            }
        )

    by_category: dict[str, dict[str, int]] = {}
    for item in results:
        bucket = by_category.setdefault(item["category"], {"passed": 0, "total": 0})
        bucket["total"] += 1
        bucket["passed"] += int(item["passed"])

    ungrounded = [
        {"id": item["id"], "tokens": item["grounding"].get("ungrounded_tokens")}
        for item in results
        if int((item["grounding"] or {}).get("numbers_ungrounded", 0) or 0) > 0
    ]
    fallbacks = sorted({item["answer_source"] for item in results if item["answer_source"].startswith("template")})

    return {
        "mode": "llm" if use_llm else "template",
        "questions": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "failed": [item["id"] for item in results if not item["passed"]],
        "by_category": by_category,
        "answers_with_ungrounded_numbers": ungrounded,
        "answer_sources": sorted({item["answer_source"] for item in results}),
        "template_fallbacks_used": fallbacks,
        "results": results,
    }


def print_summary(summary: dict[str, Any]) -> None:
    print(f"\nChat eval — mode={summary['mode']}  {summary['passed']}/{summary['questions']} passed\n")
    print(f"{'id':4s} {'cat':13s} {'route':17s} {'source':34s} ok  question")
    print("-" * 118)
    for item in summary["results"]:
        mark = "✓ " if item["passed"] else "✗ "
        print(
            f"{item['id']:4s} {item['category']:13s} {item['route']:17s} {item['answer_source']:34s} "
            f"{mark} {item['question'][:44]}"
        )
        if not item["passed"]:
            for check in item["checks"]:
                if not check["ok"]:
                    print(f"       FAILED {check['check']}: {check['detail']}")
            print(f"       answer: {item['answer'][:220]}")
    print("\nby category:", json.dumps(summary["by_category"], sort_keys=True))
    print("answer sources:", ", ".join(summary["answer_sources"]))
    print("answers containing an un-grounded number:", summary["answers_with_ungrounded_numbers"] or "none")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-llm", dest="use_llm", action="store_false", help="deterministic template path only")
    parser.add_argument("--json-out", default=None, help="artifact filename under benchmark/")
    parser.set_defaults(use_llm=True)
    args = parser.parse_args()

    summary = run_eval(use_llm=args.use_llm)
    print_summary(summary)
    name = args.json_out or f"chat-eval-phase1-{summary['mode']}.json"
    path = write_json(summary, name)
    print(f"\nartifact: {path}")
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
