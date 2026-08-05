"""Numeric grounding validation.

The rule this enforces: **every number in an answer must already be present in
the facts that produced it.** Not "should be" — checked, with the answer rejected
and replaced by a deterministic template when the check fails.

Each accepted number records *which* rule authorized it, so the authorization
surface is auditable rather than a single opaque boolean. Phase 5 extends this
with a rejection-rate metric and a planted-fake-number test; the mechanism is
here because Phase 1's definition of done is zero un-grounded numbers, and that
is not a claim worth making without a check behind it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.chat.facts import Fact


# Numbers as a model writes them: 1,234.56 · 0.8366 · 83.66% · $70,451 · 7.1%
NUMBER_TOKEN = re.compile(r"(?<![\w.])[-+]?\$?\d{1,3}(?:,\d{3})*(?:\.\d+)?%?|(?<![\w.])[-+]?\$?\d+(?:\.\d+)?%?")

# Citation markers and formatting artifacts must not be read as claims.
CITATION_MARKER = re.compile(r"\[F\d+\]|\[C\d+\]")

RELATIVE_TOLERANCE = 5e-4


@dataclass(frozen=True)
class NumberCheck:
    token: str
    value: float
    grounded: bool
    rule: str = ""
    matched_fact_id: str = ""


@dataclass
class GroundingReport:
    ok: bool
    checked: list[NumberCheck] = field(default_factory=list)
    ungrounded_tokens: list[str] = field(default_factory=list)
    authorized_rules: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "numbers_checked": len(self.checked),
            "numbers_ungrounded": len(self.ungrounded_tokens),
            "ungrounded_tokens": self.ungrounded_tokens,
            "authorization_rules": self.authorized_rules,
            "detail": [
                {
                    "token": check.token,
                    "grounded": check.grounded,
                    "rule": check.rule,
                    "fact_id": check.matched_fact_id,
                }
                for check in self.checked
            ],
        }


def parse_number(token: str) -> float | None:
    cleaned = token.strip().replace(",", "").replace("$", "")
    percent = cleaned.endswith("%")
    if percent:
        cleaned = cleaned[:-1]
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value


def extract_numbers(text: str) -> list[tuple[str, float]]:
    """Every numeric token in a piece of text, with its parsed value."""
    stripped = CITATION_MARKER.sub(" ", text)
    found: list[tuple[str, float]] = []
    for match in NUMBER_TOKEN.finditer(stripped):
        token = match.group(0)
        value = parse_number(token)
        if value is not None:
            found.append((token, value))
    return found


def numbers_match(candidate: float, authorized: float) -> bool:
    """True when ``candidate`` is ``authorized``, a rounding of it, or within tolerance."""
    if candidate == authorized:
        return True
    # A model quoting "81,789" for 81789.35946 is rounding, not inventing, so
    # accept any rounding of the authorized value to 0-6 decimal places.
    for digits in range(0, 7):
        if candidate == round(authorized, digits):
            return True
    scale = max(abs(authorized), 1.0)
    return abs(candidate - authorized) / scale <= RELATIVE_TOLERANCE


def authorized_values(
    facts: list[Fact], question: str = "", allow_prose_numbers: bool = True
) -> list[tuple[float, str, str]]:
    """(value, rule, fact_id) triples that an answer may state.

    Three rules, in descending strictness:

    ``fact_value``      a number the fact carries structurally.
    ``fact_text``       a number written in a measured fact's own sentence.
    ``prose_number``    a number appearing in retrieved prose (a corpus document or
                        the recorded advisory paragraph). Still from a file on
                        disk, so still grounded — but recorded separately, because
                        "the playbook mentions 21 days" is not a measurement and an
                        answer that quotes it as one should be visible in the report.
    ``percent_of_fact`` a fraction in 0..1 expressed as a percentage. Facts state
                        both forms, so this only catches the case where the model
                        converts anyway; it is recorded separately precisely
                        because it is the loosest rule.

    ``question`` is accepted for signature stability but deliberately NOT used as
    an authorization source. Echoing the user's own number sounds harmless until
    the question is leading — "is the objective 50,000?" would authorize the model
    to answer "yes, the objective is 50,000". Measured on the phase 1 eval set,
    that rule authorized nothing at all, so failing closed costs nothing: a number
    the facts do not contain now falls back to the template.

    🔴 **Phase 5 closed the loosest rule to model output.** ``prose_number`` is the
    weakest authorization here: a figure inside a retrieved paragraph is on disk but
    is not a measurement, and once authorized it can be restated by the model in a
    sentence that reads like one. Measured before changing anything: across the
    31-question eval set with the real model, ``prose_number`` authorized **nothing
    at all** (35 `fact_value`, 16 `fact_text`, 3 `percent_of_fact`, 0
    `prose_number`), while the deterministic template — which only ever quotes a
    fact verbatim — used it 4 times. So ``allow_prose_numbers=False`` on the model
    path costs nothing measured and removes the surface; the template keeps it,
    because there the number and its sentence are the fact's own.
    """
    allowed: list[tuple[float, str, str]] = []
    for fact in facts:
        for value in fact.numbers:
            allowed.append((value, "fact_value", fact.fact_id))
            if 0.0 < abs(value) <= 1.0:
                allowed.append((value * 100.0, "percent_of_fact", fact.fact_id))
        is_prose = fact.kind in {"corpus", "advisory"}
        if is_prose and not allow_prose_numbers:
            continue
        rule = "prose_number" if is_prose else "fact_text"
        for _, value in extract_numbers(fact.text):
            allowed.append((value, rule, fact.fact_id))
    return allowed


def validate_numbers(
    answer: str, facts: list[Fact], question: str = "", allow_prose_numbers: bool = True
) -> GroundingReport:
    allowed = authorized_values(facts, question, allow_prose_numbers)
    report = GroundingReport(ok=True)
    for token, value in extract_numbers(answer):
        match = next(
            (
                (rule, fact_id)
                for authorized, rule, fact_id in allowed
                if numbers_match(value, authorized)
            ),
            None,
        )
        if match is None:
            report.ok = False
            report.ungrounded_tokens.append(token)
            report.checked.append(NumberCheck(token=token, value=value, grounded=False))
            continue
        rule, fact_id = match
        report.authorized_rules[rule] = report.authorized_rules.get(rule, 0) + 1
        report.checked.append(
            NumberCheck(token=token, value=value, grounded=True, rule=rule, matched_fact_id=fact_id)
        )
    return report
