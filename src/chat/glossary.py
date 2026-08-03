"""Deterministic glossary lookup — answered without the LLM.

``glossary.json`` in this package is the canonical copy of the 25 jargon-free
definitions written in Iteration 4 Phase 2 explicitly for reuse here. The web UI
keeps its own literal in ``web/src/lib/glossary.ts`` so the bundle needs no new
build input; ``web/src/lib/glossary.parity.test.ts`` fails if the two drift.

Glossary questions never reach the language model: the answer is a sentence a
human wrote and a test checks. That removes a whole class of hallucination for
the cheapest possible cost.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


GLOSSARY_PATH = Path(__file__).resolve().parent / "glossary.json"

# Extra ways a planner might name a term. The key is the glossary key; the values
# are matched as whole phrases against the question, in addition to the term
# itself. Kept small and literal on purpose — an alias list that guesses is worse
# than one that misses, because a miss falls through to the grounded path.
TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "bom": ("bill of materials", "bom", "recipe"),
    "days_of_inventory": ("days of inventory", "days inventory", "doi"),
    "days_of_cover": ("days of cover", "days of coverage"),
    "s_S_policy": ("(s, s) policy", "(s,s) policy", "s s policy", "order up to policy"),
    "lead_time": ("lead time", "lead times"),
    "fill_rate": ("fill rate", "fill rates", "service level"),
    "lost_sale": ("lost sale", "lost sales"),
    "backorder": ("backorder", "backorders", "back order"),
    "holding_cost": ("holding cost", "holding costs", "carrying cost"),
    "ordering_cost": ("ordering cost", "ordering costs", "order cost"),
    "intermittent_demand": ("intermittent demand", "lumpy demand", "intermittent"),
    "auto_ets": ("autoets", "auto ets", "ets"),
    "croston_sba": ("croston-sba", "croston sba", "croston"),
    "safety_stock": ("safety stock",),
    "criticality_tier": ("criticality tier", "criticality tiers", "criticality"),
    "on_hand": ("on hand", "on-hand"),
    "in_transit": ("in transit", "in-transit"),
    "service_target": ("service target", "service targets"),
    "seed": ("random seed", "seed"),
    "objective": ("objective", "objective function"),
    "subassembly": ("subassembly", "subassemblies", "sub-assembly"),
    "echelon": ("echelon", "echelons"),
    "lane": ("lane", "lanes"),
    "period": ("period", "periods"),
    "capacity": ("capacity", "capacities"),
}

# Phrasings that ask what a word MEANS rather than what its value is here.
_DEFINITION_PATTERNS = (
    re.compile(r"\bwhat\s+(?:does|do)\b.*\bmean\b", re.I),
    re.compile(r"\bwhat\s+is\s+meant\s+by\b", re.I),
    re.compile(r"\b(?:define|definition\s+of|meaning\s+of)\b", re.I),
    re.compile(r"\bexplain\s+(?:the\s+)?(?:term|word|concept)\b", re.I),
    re.compile(r"\bin\s+plain\s+english\b", re.I),
)

# A bare "what is <term>?" is also a definition question — but only when the term
# is the WHOLE remainder. "What is the lead time from SUP-002?" is a data
# question, and an earlier, looser version of this rule sent it to the glossary.
_BARE_LOOKUP = re.compile(
    r"^(?:so\s+)?(?:what(?:'s|\s+is|\s+are)|whats)\s+(?:a|an|the)?\s*(?P<term>[^?]+?)\s*\??$",
    re.I,
)

# An explicit entity id means the question is about this dataset, not about a word.
_ENTITY_ID = re.compile(r"\b(?:SUP|PLANT|DC|CUST|FG|SA|RC|LANE)-\d+\b", re.I)

# Phrasings that scope the question to THIS dataset/run, so it wants a value, not
# a definition. "What is the fill rate in this scenario" is a data question.
_SCOPED_TO_RUN = re.compile(
    r"\b(this|these|our|the)\s+(scenario|dataset|data|run|plan|network|result|results)\b"
    r"|\bhere\b|\bin\s+this\b|\bon\s+screen\b|\bwe\s+(got|have|ran)\b",
    re.I,
)


@dataclass(frozen=True)
class GlossaryHit:
    key: str
    term: str
    definition: str
    example: str | None

    @property
    def source(self) -> str:
        return f"glossary.{self.key}"

    def answer_text(self) -> str:
        text = f"{self.term}: {self.definition}"
        if self.example:
            text = f"{text} {self.example}"
        return text


@lru_cache(maxsize=1)
def load_glossary() -> dict[str, dict[str, str]]:
    """The canonical term -> {term, definition, example?} mapping."""
    payload = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))
    return dict(payload["terms"])


@lru_cache(maxsize=1)
def glossary_order() -> tuple[str, ...]:
    payload = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))
    return tuple(payload["order"])


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("’", "'")).strip()


def asks_for_a_definition(question: str) -> bool:
    return any(pattern.search(question) for pattern in _DEFINITION_PATTERNS)


def scoped_to_this_run(question: str) -> bool:
    return bool(_SCOPED_TO_RUN.search(question))


def match_term(question: str) -> GlossaryHit | None:
    """Longest-alias match of a glossary term inside the question, or None.

    Longest-first so "days of inventory" is not swallowed by "period" or
    "capacity" appearing elsewhere in the same sentence.
    """
    text = _normalize(question)
    terms = load_glossary()
    candidates: list[tuple[int, str]] = []
    for key, entry in terms.items():
        phrases = {_normalize(entry["term"])}
        phrases.update(_normalize(alias) for alias in TERM_ALIASES.get(key, ()))
        for phrase in phrases:
            if re.search(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", text):
                candidates.append((len(phrase), key))
    if not candidates:
        return None
    _, key = max(candidates)
    entry = terms[key]
    return GlossaryHit(
        key=key,
        term=entry["term"],
        definition=entry["definition"],
        example=entry.get("example"),
    )


def _term_phrases(key: str) -> set[str]:
    entry = load_glossary()[key]
    phrases = {_normalize(entry["term"])}
    phrases.update(_normalize(alias) for alias in TERM_ALIASES.get(key, ()))
    return phrases


def glossary_route(question: str) -> GlossaryHit | None:
    """The glossary hit to answer with, or None to let the grounded path handle it.

    Deliberately conservative: a miss costs a slightly slower answer from real
    data, whereas a false hit answers a question about *this dataset* with a
    generic definition, which is a wrong answer.
    """
    if _ENTITY_ID.search(question) or scoped_to_this_run(question):
        return None
    hit = match_term(question)
    if hit is None:
        return None
    if asks_for_a_definition(question):
        return hit
    bare = _BARE_LOOKUP.match(question.strip())
    if bare and _normalize(bare.group("term")) in _term_phrases(hit.key):
        return hit
    return None


def lookup(key: str) -> GlossaryHit | None:
    entry = load_glossary().get(key)
    if entry is None:
        return None
    return GlossaryHit(key=key, term=entry["term"], definition=entry["definition"], example=entry.get("example"))
