"""Read one what-if sentence from the command line. Does not run it.

The development counterpart to ``POST /chat/parse``: same code path, no HTTP.

    python3 -m src.chat.parse --scenario stress-large \
        --question "what if DC-004 is knocked out from period 100 to 104?"
"""

from __future__ import annotations

import argparse
import json

from src.chat.intent import parse_intent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--no-llm", dest="use_llm", action="store_false", help="deterministic rules only")
    parser.set_defaults(use_llm=True)
    args = parser.parse_args()

    result = parse_intent(args.question, args.scenario, llm=None if args.use_llm else False)

    print(f"\n[{result.label}] {result.question}\n")
    print(f"outcome:   {result.outcome} ({result.reason}) via {result.parser or 'no parser needed'}")
    print(f"\n{result.message}\n")
    if result.perturbation:
        print("perturbation:", json.dumps(result.perturbation, sort_keys=True))
    if result.impact:
        print("impact:      ", json.dumps(
            {
                key: result.impact[key]
                for key in ("reaches_optimizer", "lanes_affected_count", "capacity_read_period", "estimated_seconds")
                if key in result.impact
            },
            sort_keys=True,
        ))
    for warning in (result.confirmation or {}).get("warnings", []):
        print(f"\n⚠  {warning}")
    if result.confirmation:
        print(f"\nrun it? requires confirmation — and nothing can run yet: executable={result.confirmation['executable']}")
        print(f"        {result.confirmation['not_executable_reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
