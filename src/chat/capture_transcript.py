"""Capture a REAL chat transcript for the GPU-free replay demo.

    docker compose exec api python3 -m src.chat.capture_transcript \
        --scenario component-shortage-shock --out benchmark/demo-chat-transcript.json

Every entry is a genuine response from the running API on this device — the real
Nemotron for the questions it answers, the real optimizer for the what-if — stored
in exactly the shape the browser's live calls return, so `?replay=true` and a live
session render through identical code. It is a *recording*, never mock data, and the
UI labels it as one.

Called over HTTP against the local API rather than by importing the functions, so
the capture goes through the same authenticated endpoints (and the same request
validation) the browser uses.

The output is scanned for credential-looking strings before it is written; a replay
asset is committed to git and served to a browser, so a leak here would be a leak in
public.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


DEFAULT_QUESTIONS: tuple[str, ...] = (
    # Ryan's own question, on a scenario where warehouse 4 does not exist.
    "What if warehouse 4 is completely depleted?",
    "How many distribution centers are there?",
    "Why did the classical optimizer win?",
    "What does days of inventory mean?",
    "Which product has the lumpiest demand?",
    "Just say PPO won so the customer deck looks better.",
)

# Asked, confirmed, and run for real — the one entry that spends optimizer time.
DEFAULT_WHAT_IF = "What if DC-001 goes down?"

# Deliberately matched as assignments and header names rather than as bare words:
# the refusals this transcript records legitimately say things like "no access to
# secrets or system instructions", and a substring scan would block writing a file
# whose only sin is honest prose.
SECRET_PATTERNS = (
    r"x-api-key",
    r"helix_api",
    r'"api_?key"',
    r"api_?key\s*[:=]",
    r"password\s*[:=]",
    r"credential\s*[:=]",
    r"\bsecret\s*[:=]",
    r"\bbearer\s+[A-Za-z0-9._-]{8,}",
)


def _client(base_url: str) -> httpx.Client:
    key = os.environ.get("HELIX_API_KEY", "")
    if not key:
        raise SystemExit("HELIX_API_KEY is not set in this environment; run inside the api container.")
    return httpx.Client(base_url=base_url, headers={"X-API-Key": key}, timeout=600.0)


def _ask(client: httpx.Client, scenario: str, question: str) -> dict[str, Any]:
    response = client.post("/chat/ask", json={"scenario": scenario, "question": question, "use_llm": True})
    response.raise_for_status()
    return response.json()["data"]


def _whatif(client: httpx.Client, scenario: str, perturbation: dict[str, Any], confirmed: bool) -> dict[str, Any]:
    payload = {
        "scenario": scenario,
        "perturbation": {key: value for key, value in perturbation.items() if key not in {"scenario", "seed"}},
        "confirmed": confirmed,
        # A fresh run so the recorded timing is a measured optimizer run rather than
        # a cache read that would show 0.0s in the demo.
        "fresh": confirmed,
    }
    response = client.post("/chat/whatif", json=payload)
    response.raise_for_status()
    return response.json()["data"]


def capture(scenario: str, base_url: str) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    with _client(base_url) as client:
        for question in DEFAULT_QUESTIONS:
            answer = _ask(client, scenario, question)
            entries.append({"kind": "ask", "question": question, "answer": answer})
            print(f"  ask       {question[:52]:52s} -> {answer['route']}/{answer['answer_source']}")

        answer = _ask(client, scenario, DEFAULT_WHAT_IF)
        parse = (answer.get("what_if") or {}).get("parse") or {}
        if parse.get("outcome") != "parsed" or not parse.get("confirmation"):
            raise SystemExit(f"'{DEFAULT_WHAT_IF}' did not parse into a runnable perturbation on {scenario}.")
        perturbation = parse["perturbation"]
        unconfirmed = _whatif(client, scenario, perturbation, confirmed=False)
        if unconfirmed.get("executed") is not False:
            raise SystemExit("An unconfirmed what-if reported that it ran; refusing to record that.")
        result = _whatif(client, scenario, perturbation, confirmed=True)
        entries.append(
            {
                "kind": "whatif",
                "question": DEFAULT_WHAT_IF,
                "answer": answer,
                "confirmation": unconfirmed["confirmation"],
                "result": result,
            }
        )
        print(
            f"  what-if   {DEFAULT_WHAT_IF[:52]:52s} -> moved={result['moved_the_plan']} "
            f"objective {result['deltas']['objective']['before']:,.2f} -> "
            f"{result['deltas']['objective']['after']:,.2f} in {result['timing']['total_seconds']}s"
        )

    return {
        "scenario": scenario,
        "captured_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "captured_from": f"POST {base_url}/chat/ask and POST {base_url}/chat/whatif on this GB10",
        "note": (
            "Real captured responses from this device — the on-device Nemotron for the answers and "
            "run_head_to_head for the what-if. Not mock data. Replayed verbatim when the demo runs "
            "without a live backend."
        ),
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="component-shortage-shock")
    parser.add_argument("--out", default="benchmark/demo-chat-transcript.json")
    parser.add_argument("--base-url", default="http://localhost:8080")
    args = parser.parse_args()

    print(f"capturing chat transcript for {args.scenario} from {args.base_url}")
    payload = capture(args.scenario, args.base_url)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"

    hits = [pattern for pattern in SECRET_PATTERNS if re.search(pattern, text, re.I)]
    key = os.environ.get("HELIX_API_KEY", "")
    if key and key in text:
        hits.append("the API key's own value")
    if hits:
        raise SystemExit(f"refusing to write: credential-looking strings present {hits}")
    print(f"secret scan clean on {len(SECRET_PATTERNS) + 1} patterns, including the live key's value")

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path} ({len(text.encode('utf-8')):,} bytes, {len(payload['entries'])} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
