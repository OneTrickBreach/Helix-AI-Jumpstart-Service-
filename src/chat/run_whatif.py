"""Parse a what-if sentence and run it, from the command line.

    python3 -m src.chat.run_whatif --scenario stress-large \
        --question "what if DC-004 is knocked out?" --confirm

Without ``--confirm`` it stops at the confirmation card, exactly like the API.
"""

from __future__ import annotations

import argparse
import json

from src.chat.intent import parse_intent
from src.chat.perturbation import Perturbation
from src.chat.whatif import confirmation_for, run_what_if


def _money(value: float | None) -> str:
    return "—" if value is None else f"{value:,.2f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--confirm", action="store_true", help="actually run it")
    parser.add_argument("--include-ppo", action="store_true", help="also evaluate PPO (slow)")
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--no-llm", dest="use_llm", action="store_false")
    parser.set_defaults(use_llm=True)
    args = parser.parse_args()

    parsed = parse_intent(args.question, args.scenario, llm=None if args.use_llm else False)
    print(f"\n[BETA] {args.question}\n")
    print(f"parse: {parsed.outcome} ({parsed.reason}) via {parsed.parser or 'no parser needed'}")
    if parsed.outcome != "parsed":
        print(f"\n{parsed.message}")
        return 0

    print(f"\n{parsed.message}")
    perturbation = Perturbation(**{k: v for k, v in parsed.perturbation.items()})

    if not args.confirm:
        card = confirmation_for(perturbation)
        for warning in card["warnings"]:
            print(f"\n⚠  {warning}")
        print(f"\nestimated {card['estimated_seconds']}s — re-run with --confirm to execute.")
        return 0

    def progress(stage: str, status: str) -> None:
        if status == "complete":
            print(f"   ✓ {stage}")

    print()
    result = run_what_if(
        perturbation,
        horizon=args.horizon,
        include_ppo=args.include_ppo,
        progress_callback=progress,
    )

    print(f"\n{'metric':22s} {'base':>16s} {'what-if':>16s} {'change':>14s}")
    print("-" * 72)
    for metric in ("objective", "total_cost", "fill_rate", "days_of_inventory", "cvar_75"):
        delta = result.deltas[metric]
        percent = f"{delta['percent'] * 100:+.2f}%" if delta["percent"] is not None else "—"
        print(f"{metric:22s} {_money(delta['before']):>16s} {_money(delta['after']):>16s} {percent:>14s}")

    print(f"\n{result.explanation}")
    for warning in result.warnings:
        print(f"\n⚠  {warning}")
    print(
        f"\nseed {result.seed} · horizon {result.horizon} · PPO {'included' if result.ppo_included else 'excluded'}"
        f" · {result.timing['total_seconds']}s"
        f" · cached={result.cached}"
    )
    print(f"diff: {json.dumps(result.diff, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
