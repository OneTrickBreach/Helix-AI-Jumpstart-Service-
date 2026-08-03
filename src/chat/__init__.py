"""Iteration 5 (Beta) — conversational scenario analyst.

The one architectural rule this package exists to enforce:

    The LLM is an interpreter and a narrator. It is never a calculator.

Every number that reaches a user came from a file on disk (the generated
scenario data, or a recorded ``run_head_to_head`` benchmark artifact). The LLM
is handed a closed set of facts and asked to phrase them; a deterministic
validator then checks that every numeric token in its answer was present in
those facts, and falls back to a template answer if not.

Phase 1 is read-only: it answers questions about the dataset and the recorded
run. It runs no optimizer and mutates nothing.
"""

from __future__ import annotations
