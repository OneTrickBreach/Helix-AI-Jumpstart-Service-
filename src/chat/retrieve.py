"""Deterministic fact selection.

Scoring is keyword/entity overlap, not embeddings. Three reasons, in order of
importance: it is reproducible (the same question always retrieves the same
facts, so an eval set means something), it costs no GPU, and when it is wrong it
is wrong in a way you can read off the score breakdown instead of guessing at a
vector space.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.chat.facts import ENTITY_PATTERN, Fact, FactBundle


# Section words that should pull their whole section up when the question names
# them, e.g. "lanes" -> every lanes fact gets a small boost.
_KIND_HINTS: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    (re.compile(r"\b(result|results|objective|cost|won|winner|win|better|improv|saving|percent|%|fill rate|cvar|tail)\b", re.I), ("benchmark",)),
    (re.compile(r"\b(ppo|reinforcement|rl|learned)\b", re.I), ("benchmark",)),
    (re.compile(r"\b(advisory|rationale|llm|language model|ai wrote|model)\b", re.I), ("advisory",)),
    (re.compile(r"\b(memory|gib|envelope|headroom|device|hardware|gb10|fit on)\b", re.I), ("device",)),
    (re.compile(r"\b(policy|sop|playbook|agreement|procedure|guideline|rule|should we|escalat)\b", re.I), ("corpus",)),
)

MAX_BODY_OVERLAP_SCORE = 1.75
# Corpus prose is context, not measurement. It should support an answer, not lead it.
CORPUS_DAMPING = 0.7

_STOPWORDS = frozenset(
    """a an and any are as at be been being but by can could did do does for from get give had has have how
    i if in into is it its many me much my of on or our over per should so some tell that the their them then
    there these they this to us was we were what when where which who whom why will with would you your
    please just about show explain does'nt
    """.split()
)


@dataclass(frozen=True)
class ScoredFact:
    fact: Fact
    score: float
    matched: tuple[str, ...]


def tokenize(question: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9'-]*", question.lower())
    return [word for word in words if word not in _STOPWORDS and len(word) > 1]


def phrases(question: str, max_len: int = 4) -> set[str]:
    """All contiguous word n-grams, used to match multi-word keywords."""
    words = re.findall(r"[a-z0-9][a-z0-9'-]*", question.lower())
    found: set[str] = set()
    for size in range(1, max_len + 1):
        for start in range(0, max(0, len(words) - size + 1)):
            found.add(" ".join(words[start : start + size]))
    return found


def mentioned_entities(question: str) -> list[str]:
    return [match.group(0).upper() for match in ENTITY_PATTERN.finditer(question)]


def score_fact(fact: Fact, tokens: list[str], question_phrases: set[str], entities: list[str], kind_boosts: set[str]) -> ScoredFact:
    matched: list[str] = []
    score = 0.0

    # Entity match is the strongest signal: "LANE-0001" or "SUP-002" in the
    # question means the fact about that entity is almost certainly wanted.
    for entity in entities:
        if entity in {value.upper() for value in fact.entities}:
            score += 6.0
            matched.append(entity)

    for keyword in fact.keywords:
        if keyword in question_phrases:
            # Multi-word keywords are far more specific than single words.
            score += 3.0 if " " in keyword else 1.5
            matched.append(keyword)

    label_words = set(tokenize(fact.label))
    text_words = set(tokenize(fact.text))
    body_score = 0.0
    for token in set(tokens):
        if token in label_words:
            score += 1.0
            matched.append(token)
        elif token in text_words:
            body_score += 0.35
            matched.append(token)

    # Cap the body-overlap contribution. Without this, a long prose fact wins on
    # sheer word count: a corpus paragraph that happens to contain "cost",
    # "classical" and "optimizer" outranked the measured result for
    # "why did the classical optimizer win?".
    score += min(body_score, MAX_BODY_OVERLAP_SCORE)

    if fact.kind in kind_boosts:
        score += 1.2

    if fact.kind == "corpus":
        score *= CORPUS_DAMPING

    return ScoredFact(fact=fact, score=round(score, 4), matched=tuple(dict.fromkeys(matched)))


def kind_boosts(question: str) -> set[str]:
    boosts: set[str] = set()
    for pattern, kinds in _KIND_HINTS:
        if pattern.search(question):
            boosts.update(kinds)
    return boosts


def select_facts(
    question: str,
    bundle: FactBundle,
    limit: int = 10,
    min_score: float = 1.5,
    include_flagged: bool = False,
) -> list[ScoredFact]:
    """Top-scoring facts for a question, best first.

    Injection-flagged corpus facts are excluded by default: flagged content is
    surfaced to the caller as a finding, never fed to the model as evidence.
    """
    tokens = tokenize(question)
    question_phrases = phrases(question)
    entities = mentioned_entities(question)
    boosts = kind_boosts(question)
    scored = [
        score_fact(fact, tokens, question_phrases, entities, boosts)
        for fact in bundle.facts
        if include_flagged or not fact.injection_flagged
    ]
    scored = [item for item in scored if item.score >= min_score]
    # Deterministic ordering: score desc, then fact_id asc so ties never shuffle.
    scored.sort(key=lambda item: (-item.score, item.fact.fact_id))
    return scored[:limit]
