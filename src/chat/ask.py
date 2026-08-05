"""Ask one grounded question from the command line.

The development counterpart to ``POST /chat/ask``: same code path, no HTTP, no
API key. Handy for checking a single answer without a browser, and for pasting a
real answer into a journal entry.

    python3 -m src.chat.ask --scenario baseline --question "how many DCs are there?"
"""

from __future__ import annotations

import argparse
import json

from src.chat.answer import answer_question


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--no-llm", dest="use_llm", action="store_false", help="deterministic template path")
    parser.add_argument("--facts", action="store_true", help="also print the retrieved facts and scores")
    parser.set_defaults(use_llm=True)
    args = parser.parse_args()

    result = answer_question(args.question, args.scenario, llm=None if args.use_llm else False)

    print(f"\n[{result.label}] {result.question}\n")
    print(result.answer)
    print(f"\nroute:      {result.route} ({result.reason})")
    print(f"source:     {result.answer_source}")
    print(f"citations:  {[citation['source'] for citation in result.citations]}")
    print(
        "grounding:  "
        + json.dumps({key: result.grounding.get(key) for key in ("ok", "numbers_checked", "numbers_ungrounded")})
    )
    if result.notes:
        print(f"notes:      {result.notes}")
    if args.facts:
        print("\nretrieved facts:")
        for item in result.facts_used:
            print(f"  {item['score']:7.2f}  {item['fact_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
