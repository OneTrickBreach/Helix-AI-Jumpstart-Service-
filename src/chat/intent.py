"""Turn a sentence into a validated perturbation, a question, or a refusal.

Deterministic first, model second — the same shape as the Phase 1 router, for the
same reasons. Common phrasings ("what if DC-001 goes down from period 3 to 6?")
are parsed by rule: reproducible, instant, no GPU, and debuggable by reading the
matched groups. Anything the rules cannot fully resolve goes to the LLM, which
proposes a *structured* parse that is then validated by exactly the same schema
and entity resolver. The model never widens what is legal; it only helps read the
sentence.

Four outcomes:

    ``parsed``        a validated perturbation plus a confirm-before-run card.
    ``clarify``       the reading is ambiguous; state what is missing and ask.
    ``refused``       outside the whitelist, and refused rather than approximated.
    ``not_found``     names a place that is not in this scenario (with what is).

No outcome executes anything: parsing is separate from running on purpose, so a
misread sentence cannot spend compute. Running a validated perturbation is
``src.chat.whatif.run_what_if``, and it requires explicit confirmation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import polars as pl

from src.chat.facts import NODE_TYPE_SINGULAR, NODE_TYPE_WORDS
from src.chat.perturbation import (
    WHITELIST,
    Impact,
    Perturbation,
    PerturbationError,
    analyse,
    build_confirmation_card,
    max_period,
    validate,
)
from src.chat.router import scan_question
from src.ingest.state import ScenarioState, load_scenario_state
from src.rag.advisory import call_shared_llm, strip_reasoning_scratchpad


PARSE_MARKER = "PARSE:"
# 1400: the parser is a reasoning model and will deliberate about edge cases
# ("is an inbound-only outage really a node_outage?") until the budget runs out.
# Measured: at 900 tokens a paraphrase naming DC-002 truncated mid-deliberation
# and produced no JSON at all.
MAX_PARSE_TOKENS = 1400

LlmCall = Callable[[list[dict[str, str]], str], dict[str, Any]]

# ---------------------------------------------------------------------------
# vocabulary
# ---------------------------------------------------------------------------

OUTAGE_WORDS = re.compile(
    r"\b(?:outage|out\s+of\s+action|goes?\s+(?:down|offline|dark)|went\s+down|knock(?:ed)?\s+out|"
    r"shut(?:s|down|\s+down)?|clos(?:e|es|ed|ing)|off\s?line|unavailable|fails?|failed|"
    r"deplet(?:e|ed|es)|wiped\s+out|lost|los(?:e|es)|strike|flood(?:ed)?|fire)\b",
    re.I,
)
DEMAND_WORDS = re.compile(r"\bdemand\b|\borders?\b|\bvolume\b|\bsales\b", re.I)
CAPACITY_WORDS = re.compile(r"\bcapacit(?:y|ies)\b|\bthroughput\b|\bcan\s+only\s+(?:carry|move|ship)\b", re.I)
LANE_WORDS = re.compile(r"\blane\b|\broute\b|\bshipping\s+lane\b|\bleg\b", re.I)

ENTITY_ID = re.compile(r"\b(SUP|PLANT|DC|CUST|FG|SA|RC|LANE)-(\d{1,4})\b", re.I)

# "from period 3 to period 6" · "periods 3-6" · "in period 4" · "for 10 weeks from week 18"
PERIOD_RANGE = re.compile(
    r"(?:from\s+)?(?:period|week)s?\s*#?\s*(\d{1,3})\s*(?:-|–|to|through|until|thru)\s*(?:period|week)?\s*#?\s*(\d{1,3})",
    re.I,
)
PERIOD_SINGLE = re.compile(r"\b(?:in|at|during|for|from)\s+(?:period|week)\s*#?\s*(\d{1,3})\b", re.I)
PERIOD_FOR_N = re.compile(
    r"\bfor\s+(\d{1,3})\s+(?:period|week)s?\s+(?:from|starting(?:\s+(?:at|in|from))?)\s+(?:period|week)?\s*#?\s*(\d{1,3})",
    re.I,
)
PERIOD_ONWARDS = re.compile(r"\bfrom\s+(?:period|week)\s*#?\s*(\d{1,3})\s+(?:onwards?|on\b|to\s+the\s+end)", re.I)

DOUBLE = re.compile(r"\bdoubl\w*\b|\b2x\b|\btwice\b|\btwo\s+times\b", re.I)
TRIPLE = re.compile(r"\btripl\w*\b|\b3x\b|\bthree\s+times\b", re.I)
HALVE = re.compile(r"\bhalv\w*\b|\bhalf\b|\b0\.5x\b", re.I)
TO_ZERO = re.compile(r"\bto\s+zero\b|\bzero\b|\bnothing\b|\bcompletely\b|\bentirely\b|\bfully\b", re.I)
# Unambiguously "goes to nothing", for demand as well as capacity — "demand drops
# to zero" states its magnitude and must not be sent back asking for a number.
TO_ZERO_EXPLICIT = re.compile(
    r"\bto\s+(?:zero|nothing)\b|\bzero\s+demand\b|\bno\s+demand\b|\bdries?\s+up\b"
    r"|\bstops?\s+(?:completely|entirely|altogether)\b|\bdisappears?\b",
    re.I,
)
PERCENT_CHANGE = re.compile(r"\b(up|down|increase[sd]?|decrease[sd]?|rise[sd]?|fall[s]?|drops?|grows?|cut)\b[^.]{0,24}?\b(\d{1,5})\s*%", re.I)
PERCENT_TO = re.compile(r"\bto\s+(\d{1,5})\s*%", re.I)
MULTIPLIER_X = re.compile(r"\b(\d+(?:\.\d+)?)\s*x\b", re.I)

# Things we explicitly will not model, each with the honest reason.
OUT_OF_SCOPE: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "add_or_remove_entities",
        re.compile(
            r"\badd(?:ing)?\s+(?:a|an|another|\d+)\s*(?:new\s+)?(?:node|location|warehouse|dc|distribution|plant|factory|supplier|customer|sku|product|lane)"
            r"|\b(?:remove|delete|drop)\s+(?:a|an|the)?\s*(?:node|location|warehouse|dc|plant|factory|supplier|customer|sku|product)"
            r"|\bif\s+we\s+had\s+\d+\s+(?:warehouse|dc|plant|factory|supplier|customer)",
            re.I,
        ),
        "I can't add or remove locations, products or lanes. The network is fixed by the generated dataset; "
        "I can only perturb what is already in it.",
    ),
    (
        "change_objective",
        re.compile(r"\b(?:change|swap|replace|optimi[sz]e\s+for|maximi[sz]e|minimi[sz]e)\b[^.]{0,30}\bobjective\b|\bweight\s+(?:the\s+)?(?:cost|fill\s*rate)\b", re.I),
        "I can't change what the optimizer is optimizing for. The objective is fixed so that every run in the "
        "benchmark stays comparable.",
    ),
    (
        "edit_bom",
        re.compile(r"\b(?:bom|bill\s+of\s+materials|recipe)\b[^.]{0,40}\b(?:change|edit|swap|substitut\w+|redesign)\b|\b(?:change|edit|swap|substitut\w+|cheaper)\b[^.]{0,50}\b(?:bom|bill\s+of\s+materials)\b", re.I),
        "I can't edit the bill of materials. Component demand is derived through the BOM when the data is "
        "generated, so changing it means regenerating the dataset, not perturbing it.",
    ),
    (
        "real_customer_data",
        re.compile(r"\bmy\s+(?:real|actual|own)\b|\bour\s+(?:real|actual|own)\s+(?:data|network|numbers)|\bupload\b|\bimport\b[^.]{0,20}\b(?:csv|data|file)\b", re.I),
        "I can't work with real customer data. This box runs a seeded synthetic dataset; onboarding real data is "
        "a later iteration.",
    ),
    (
        "lead_time_inflation",
        re.compile(r"\blead\s*times?\b[^.]{0,40}\b(?:doubl\w*|tripl\w*|increase\w*|longer|slower|inflat\w*|stretch\w*|\d+\s*x)\b|\b(?:doubl\w*|tripl\w*|increase\w*)\b[^.]{0,20}\blead\s*times?\b", re.I),
        "Lead-time inflation isn't in the three perturbations I can model yet. It is one of five deferred types, "
        "and shipping three that are provably correct beats eight that are plausible.",
    ),
    (
        "cost_shock",
        re.compile(r"\b(?:fuel|freight|transport|holding|ordering)\s+cost\w*\b[^.]{0,30}\b(?:rise|rises|up|increase\w*|doubl\w*|\d+\s*%)|\bcost\s+shock\b", re.I),
        "Cost shocks aren't in the three perturbations I can model yet — they are one of five deferred types.",
    ),
    (
        "service_target_change",
        re.compile(r"\b(?:service\s+target|fill[-\s]*rate\s+target|sla)\b[^.]{0,30}\b(?:change|raise|lower|increase|decrease|set)\b|\b(?:raise|lower|increase|decrease|set)\b[^.]{0,30}\b(?:fill[-\s]*rate\s+target|service\s+target)\b", re.I),
        "Changing service targets isn't in the three perturbations I can model yet — it is one of five deferred "
        "types.",
    ),
)

# Two perturbations joined together. Compounding is explicitly out of scope.
COMPOUND = re.compile(
    r"\b(?:and|plus|while|as\s+well\s+as|at\s+the\s+same\s+time|simultaneously|both)\b",
    re.I,
)


@dataclass
class ParseResult:
    outcome: str                      # parsed | clarify | refused | not_found
    scenario: str
    question: str
    parser: str = ""                  # deterministic | llm | none
    reason: str = ""
    message: str = ""
    perturbation: dict[str, Any] | None = None
    impact: dict[str, Any] | None = None
    confirmation: dict[str, Any] | None = None
    missing: list[str] = field(default_factory=list)
    options: list[str] = field(default_factory=list)
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    injection_flags: list[dict[str, Any]] = field(default_factory=list)
    beta: bool = True
    label: str = "BETA"
    executable: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "scenario": self.scenario,
            "question": self.question,
            "parser": self.parser,
            "reason": self.reason,
            "message": self.message,
            "perturbation": self.perturbation,
            "impact": self.impact,
            "confirmation": self.confirmation,
            "missing": self.missing,
            "options": self.options,
            "unresolved": self.unresolved,
            "injection_flags": self.injection_flags,
            "beta": self.beta,
            "label": self.label,
            "executable": self.executable,
        }


# ---------------------------------------------------------------------------
# entity resolution
# ---------------------------------------------------------------------------

_ID_PREFIX_BY_NODE_TYPE = {
    "supplier": "SUP",
    "plant": "PLANT",
    "distribution_center": "DC",
    "customer": "CUST",
}
_TYPE_WORD_TO_NODE_TYPE = {word: node_type for node_type, words in NODE_TYPE_WORDS.items() for word in words}


def node_ids_by_type(state: ScenarioState) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for row in state.nodes.select("node_id", "node_type").sort("node_id").to_dicts():
        grouped.setdefault(row["node_type"], []).append(row["node_id"])
    return grouped


def scenarios_containing(node_type: str, at_least: int, exclude: str, data_root: Any = None) -> list[str]:
    """Which other scenarios have at least ``at_least`` nodes of this type.

    Reads only ``nodes.csv`` per scenario, so offering "shall I run it on
    stress-large?" costs a few milliseconds rather than a full overview build.
    """
    from src.dataset.overview import known_scenarios
    from src.ingest.state import DEFAULT_DATA_ROOT

    root = data_root or DEFAULT_DATA_ROOT
    found: list[str] = []
    for name in known_scenarios(root):
        if name == exclude:
            continue
        path = root / name / "nodes.csv"
        if not path.exists():
            continue
        try:
            nodes = pl.read_csv(path, null_values=[""])
        except Exception:  # noqa: BLE001 - a broken scenario should not break the offer
            continue
        if "node_type" not in nodes.columns:
            continue
        count = nodes.filter(pl.col("node_type") == node_type).height
        if count >= at_least:
            found.append(name)
    return sorted(found)


@dataclass
class EntityRef:
    raw: str
    node_type: str | None
    ordinal: int | None
    resolved_id: str | None


def resolve_entities(question: str, state: ScenarioState) -> tuple[list[EntityRef], list[EntityRef]]:
    """(resolved, unresolved) place/lane/product references named in the question."""
    known_nodes = set(state.nodes.select("node_id").to_series().to_list())
    known_lanes = set(state.lanes.select("lane_id").to_series().to_list())
    known_skus = set(state.skus.select("sku_id").to_series().to_list())
    resolved: list[EntityRef] = []
    unresolved: list[EntityRef] = []
    seen: set[str] = set()

    for match in ENTITY_ID.finditer(question):
        prefix, digits = match.group(1).upper(), match.group(2)
        raw = f"{prefix}-{digits}"
        canonical = f"{prefix}-{digits.zfill(3)}"
        if raw in seen:
            continue
        seen.add(raw)
        node_type = next((key for key, value in _ID_PREFIX_BY_NODE_TYPE.items() if value == prefix), None)
        actual = next((cand for cand in (raw, canonical) if cand in known_nodes | known_lanes | known_skus), None)
        ref = EntityRef(raw=raw, node_type=node_type, ordinal=int(digits), resolved_id=actual)
        (resolved if actual else unresolved).append(ref)

    pattern = "|".join(sorted((re.escape(word) for word in _TYPE_WORD_TO_NODE_TYPE), key=len, reverse=True))
    for match in re.finditer(rf"\b({pattern})\s*#?\s*(\d{{1,4}})\b", question, re.I):
        word, ordinal = match.group(1).lower(), int(match.group(2))
        node_type = _TYPE_WORD_TO_NODE_TYPE[word]
        raw = f"{match.group(1)} {ordinal}"
        if raw in seen:
            continue
        seen.add(raw)
        candidate = f"{_ID_PREFIX_BY_NODE_TYPE[node_type]}-{ordinal:03d}"
        actual = candidate if candidate in known_nodes else None
        ref = EntityRef(raw=raw, node_type=node_type, ordinal=ordinal, resolved_id=actual)
        (resolved if actual else unresolved).append(ref)

    return resolved, unresolved


def not_found_message(unresolved: list[EntityRef], state: ScenarioState, data_root: Any = None) -> str:
    """The §1.1 answer: name what exists, and offer a scenario that has what they asked for."""
    grouped = node_ids_by_type(state)
    parts: list[str] = []
    for ref in unresolved:
        if ref.node_type:
            singular = NODE_TYPE_SINGULAR.get(ref.node_type, ref.node_type.replace("_", " "))
            existing = grouped.get(ref.node_type, [])
            listed = ", ".join(existing) if len(existing) <= 12 else ", ".join(existing[:12]) + ", …"
            parts.append(
                f"There is no {ref.raw} in the {state.scenario} scenario. It has {len(existing)} "
                f"{singular}{'' if len(existing) == 1 else 's'}: {listed}."
            )
            if ref.ordinal:
                offers = scenarios_containing(ref.node_type, ref.ordinal, state.scenario, data_root)
                if offers:
                    parts.append(
                        f"Did you mean one of those, or shall I run it on {offers[0]}, which has "
                        f"{ref.ordinal} or more {singular}s?"
                    )
                else:
                    parts.append(f"No scenario in this demo has that many {singular}s.")
        else:
            parts.append(f"There is no {ref.raw} in the {state.scenario} scenario.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# deterministic parsing
# ---------------------------------------------------------------------------


def _periods(question: str, limit: int) -> tuple[int, int] | None:
    match = PERIOD_FOR_N.search(question)
    if match:
        length, start = int(match.group(1)), int(match.group(2))
        return start, min(limit, start + length - 1)
    match = PERIOD_RANGE.search(question)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = PERIOD_ONWARDS.search(question)
    if match:
        return int(match.group(1)), limit
    match = PERIOD_SINGLE.search(question)
    if match:
        return int(match.group(1)), int(match.group(1))
    return None


def _multiplier(question: str, *, for_capacity: bool) -> float | None:
    if TO_ZERO_EXPLICIT.search(question):
        return 0.0
    if for_capacity and TO_ZERO.search(question):
        return 0.0
    if DOUBLE.search(question):
        return 2.0
    if TRIPLE.search(question):
        return 3.0
    if HALVE.search(question):
        return 0.5
    match = MULTIPLIER_X.search(question)
    if match:
        return float(match.group(1))
    match = PERCENT_TO.search(question)
    if match:
        return int(match.group(1)) / 100.0
    match = PERCENT_CHANGE.search(question)
    if match:
        direction, amount = match.group(1).lower(), int(match.group(2))
        fraction = amount / 100.0
        down = direction.startswith(("down", "decrease", "fall", "drop", "cut"))
        return round(1.0 - fraction, 6) if down else round(1.0 + fraction, 6)
    if for_capacity and TO_ZERO.search(question):
        return 0.0
    return None


def _demand_scope(question: str, state: ScenarioState, resolved: list[EntityRef]) -> tuple[str, str | None]:
    known_skus = set(state.skus.select("sku_id").to_series().to_list())
    customers = set(state.customers())
    for ref in resolved:
        if ref.resolved_id in known_skus:
            return "sku", ref.resolved_id
        if ref.resolved_id in customers:
            return "customer", ref.resolved_id
    return "all", None


def parse_deterministic(question: str, state: ScenarioState) -> tuple[Perturbation | None, list[str]]:
    """A perturbation if the rules can read the sentence outright, else what is missing."""
    limit = max_period(state)
    resolved, _ = resolve_entities(question, state)
    known_lanes = set(state.lanes.select("lane_id").to_series().to_list())
    known_nodes = set(state.nodes.select("node_id").to_series().to_list())
    lane_refs = [ref for ref in resolved if ref.resolved_id in known_lanes]
    node_refs = [ref for ref in resolved if ref.resolved_id in known_nodes]
    window = _periods(question, limit)
    missing: list[str] = []

    # lane_disruption — checked before demand: a named lane plus "volume" is about
    # that lane, not about customer demand.
    if lane_refs and (LANE_WORDS.search(question) or CAPACITY_WORDS.search(question) or OUTAGE_WORDS.search(question)):
        multiplier = _multiplier(question, for_capacity=True)
        if multiplier is None:
            if OUTAGE_WORDS.search(question):
                multiplier = 0.0
            else:
                return None, ["capacity_multiplier"]
        start, end = window or (1, limit)
        return (
            Perturbation(
                kind="lane_disruption",
                scenario=state.scenario,
                from_period=start,
                to_period=end,
                lane_id=lane_refs[0].resolved_id,
                capacity_multiplier=multiplier,
            ),
            [],
        )

    # demand_multiplier
    if DEMAND_WORDS.search(question):
        multiplier = _multiplier(question, for_capacity=False)
        if multiplier is None:
            return None, ["multiplier"]
        scope, scope_id = _demand_scope(question, state, resolved)
        start, end = window or (1, limit)
        return (
            Perturbation(
                kind="demand_multiplier",
                scenario=state.scenario,
                from_period=start,
                to_period=end,
                demand_multiplier=multiplier,
                scope=scope,
                scope_id=scope_id,
            ),
            [],
        )

    # node_outage — a named location that goes down
    if node_refs and OUTAGE_WORDS.search(question):
        start, end = window or (1, limit)
        return (
            Perturbation(
                kind="node_outage",
                scenario=state.scenario,
                from_period=start,
                to_period=end,
                node_id=node_refs[0].resolved_id,
            ),
            [],
        )

    if OUTAGE_WORDS.search(question) and not node_refs and not lane_refs:
        missing.append("which_location")
    if CAPACITY_WORDS.search(question) and not lane_refs and not node_refs:
        missing.append("which_lane_or_location")
    return None, missing


# ---------------------------------------------------------------------------
# LLM fallback: propose a structured parse, validated by the same schema
# ---------------------------------------------------------------------------


def build_parse_prompt(question: str, state: ScenarioState) -> list[dict[str, str]]:
    grouped = node_ids_by_type(state)
    limit = max_period(state)
    inventory = "; ".join(
        f"{NODE_TYPE_SINGULAR.get(node_type, node_type)}s: {', '.join(ids[:12])}"
        + (f" (+{len(ids) - 12} more)" if len(ids) > 12 else "")
        for node_type, ids in sorted(grouped.items())
    )
    lane_ids = state.lanes.select("lane_id").to_series().to_list()
    skus = state.skus.select("sku_id").to_series().to_list()
    return [
        {
            "role": "system",
            # Terse for the same measured reason as the Phase 1 answer prompt: a
            # long rule list makes this model narrate its checklist and burn the
            # token budget before emitting anything.
            "content": (
                "/no_think\n"
                "You convert a supply-chain what-if question into ONE JSON object. You never answer the "
                "question and never invent an id.\n"
                'Allowed: {"kind":"node_outage","node_id":...,"from_period":int,"to_period":int} | '
                '{"kind":"lane_disruption","lane_id":...,"capacity_multiplier":float,"from_period":int,'
                '"to_period":int} | {"kind":"demand_multiplier","demand_multiplier":float,'
                '"scope":"all|customer|sku","scope_id":...,"from_period":int,"to_period":int}\n'
                'If it is none of those, or two of them at once, or a magnitude is not stated: '
                '{"kind":"unsupported","why":"<short reason>"}\n'
                "Do not deliberate, explain, or weigh alternatives. Choose the closest allowed shape and emit "
                "the JSON.\n"
                f"Output the JSON on one line after the marker {PARSE_MARKER}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Scenario {state.scenario} has {limit} periods. Ids that exist — {inventory}; "
                f"lanes: {', '.join(lane_ids[:20])}{' …' if len(lane_ids) > 20 else ''}; "
                f"products: {', '.join(skus[:20])}{' …' if len(skus) > 20 else ''}.\n\n"
                f"Question: {question}\n\n"
                f"Reply with only: {PARSE_MARKER} <one JSON object>"
            ),
        },
    ]


def extract_parse_json(raw: str) -> dict[str, Any] | None:
    text = strip_reasoning_scratchpad(raw)
    lowered = text.lower()
    if PARSE_MARKER.lower() in lowered:
        text = text[lowered.rindex(PARSE_MARKER.lower()) + len(PARSE_MARKER) :]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _perturbation_from_payload(payload: dict[str, Any], state: ScenarioState) -> Perturbation:
    kind = str(payload.get("kind", "")).strip()
    if kind not in WHITELIST:
        raise PerturbationError(str(payload.get("why") or f"'{kind}' is not a perturbation I can model."))
    limit = max_period(state)

    def period(name: str, default: int) -> int:
        value = payload.get(name, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            raise PerturbationError(f"{name} must be a whole number of periods.") from None

    def number(name: str) -> float | None:
        value = payload.get(name)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            raise PerturbationError(f"{name} must be a number.") from None

    return Perturbation(
        kind=kind,
        scenario=state.scenario,
        from_period=period("from_period", 1),
        to_period=period("to_period", limit),
        node_id=(str(payload["node_id"]).upper() if payload.get("node_id") else None),
        lane_id=(str(payload["lane_id"]).upper() if payload.get("lane_id") else None),
        capacity_multiplier=number("capacity_multiplier"),
        demand_multiplier=number("demand_multiplier"),
        scope=(str(payload["scope"]).lower() if payload.get("scope") else None),
        scope_id=(str(payload["scope_id"]).upper() if payload.get("scope_id") else None),
    )


def _default_llm(prompt: list[dict[str, str]], scenario: str) -> dict[str, Any]:
    return call_shared_llm(
        prompt,
        scenario=scenario,
        max_tokens=MAX_PARSE_TOKENS,
        temperature=0.0,
        profile_name="chat_intent_parser_llm",
    )


# ---------------------------------------------------------------------------
# the entry point
# ---------------------------------------------------------------------------

# Missing pieces the model may help read (a magnitude the sentence states in words
# the rules cannot parse). Anything else — which location, which lane — is asked.
_MAGNITUDE_KEYS = frozenset({"multiplier", "capacity_multiplier"})

_MISSING_QUESTIONS = {
    "multiplier": "By how much? Give me a number — 'doubles', 'up 30%', or '1.5x' all work.",
    "capacity_multiplier": "By how much should that lane's capacity change? 'closed completely' or 'down 40%' both work.",
    "which_location": "Which location? Name it and I'll read the outage against the lanes that touch it.",
    "which_lane_or_location": "Which lane or location did you mean?",
}


def _capabilities_sentence() -> str:
    return (
        "I can model three things: a location unable to ship or receive, one lane's capacity changing, and "
        "demand scaled for everything, one customer or one product."
    )


def parse_intent(
    question: str,
    scenario: str,
    state: ScenarioState | None = None,
    llm: LlmCall | None = None,
    recorded_latencies: dict[str, float] | None = None,
    data_root: Any = None,
) -> ParseResult:
    """Read one what-if sentence. Never executes; ``src.chat.whatif`` runs them.

    ``llm=False`` restricts parsing to the deterministic rules, which is what the
    test suite and the template eval mode use.
    """
    if state is None:
        state = load_scenario_state(scenario) if data_root is None else load_scenario_state(scenario, data_root=data_root)
    text = question.strip()
    base = {"scenario": state.scenario, "question": question}

    if not text:
        return ParseResult(outcome="clarify", reason="empty_question", parser="none", **base,
                           message="Describe the disruption you want to model. " + _capabilities_sentence())

    findings = [{**finding, "detected_at": "user_question"} for finding in scan_question(text)]
    if findings:
        return ParseResult(
            outcome="refused",
            reason="prompt_injection_in_question",
            parser="none",
            injection_flags=findings,
            message=(
                "I've flagged that message rather than acting on it, and nothing in it reached the model. "
                + _capabilities_sentence()
            ),
            **base,
        )

    for reason, pattern, explanation in OUT_OF_SCOPE:
        if pattern.search(text):
            return ParseResult(
                outcome="refused", reason=reason, parser="none", message=f"{explanation} {_capabilities_sentence()}",
                **base,
            )

    # A place that does not exist is answered before anything else is attempted:
    # parsing "warehouse 4" into a perturbation would be inventing a node.
    resolved, unresolved = resolve_entities(text, state)
    if unresolved:
        return ParseResult(
            outcome="not_found",
            reason="unknown_entity",
            parser="none",
            message=not_found_message(unresolved, state, data_root),
            unresolved=[
                {
                    "reference": ref.raw,
                    "node_type": ref.node_type,
                    "ordinal": ref.ordinal,
                    "existing_ids": node_ids_by_type(state).get(ref.node_type or "", []),
                }
                for ref in unresolved
            ],
            **base,
        )

    perturbation, missing = parse_deterministic(text, state)
    parser = "deterministic"

    # Compounding is refused, but only once we know there really are two
    # perturbations in the sentence — "from period 3 to 6 and nothing else"
    # contains "and" without asking for two changes.
    if perturbation is not None and COMPOUND.search(text) and _looks_compound(text):
        return ParseResult(
            outcome="refused",
            reason="compound_perturbation",
            parser=parser,
            message=(
                "I can only model one change at a time, and combining two would make it impossible to say "
                "which one moved the result. Ask me about one, then the other. " + _capabilities_sentence()
            ),
            **base,
        )

    # 🔴 The distinction that matters when the rules come up short: is the missing
    # piece absent from the sentence, or present but unreadable by a regex?
    #
    #   absent  ("what if demand spikes?")            -> ASK. Guardrail 2 requires
    #           an ambiguous request to be asked about, and handing it to a model
    #           invites it to supply a magnitude the planner never stated.
    #           Measured: the model did not invent one, it refused — turning a
    #           one-question clarification into a dead end. Asking is better than
    #           both.
    #   present ("a third of its usual volume")       -> let the model read it.
    #           Asking "by how much?" when they already said "a third" reads as
    #           not listening.
    #
    # A missing *entity* is never delegated: the model must not choose which
    # warehouse the planner meant.
    if perturbation is None and missing:
        magnitude_only = all(key in _MAGNITUDE_KEYS for key in missing)
        if not (magnitude_only and _states_a_magnitude(text)):
            asks = [_MISSING_QUESTIONS[key] for key in missing if key in _MISSING_QUESTIONS]
            return ParseResult(
                outcome="clarify",
                reason="incomplete_request",
                parser="deterministic",
                missing=missing,
                message=" ".join(asks) if asks else "I couldn't tell what you want changed. " + _capabilities_sentence(),
                **base,
            )

    if perturbation is None and llm is not False:
        caller: LlmCall = llm if callable(llm) else _default_llm
        try:
            response = caller(build_parse_prompt(text, state), state.scenario)
            payload = extract_parse_json(str(response.get("text", "")))
            finish_reason = response.get("finish_reason")
        except Exception as exc:  # noqa: BLE001 - fall back to asking, never to guessing
            return ParseResult(
                outcome="clarify",
                reason="parser_unavailable",
                parser="llm",
                message=(
                    f"I couldn't read that automatically ({type(exc).__name__}) and I won't guess at what you "
                    f"meant. {_capabilities_sentence()}"
                ),
                **base,
            )
        if payload is None:
            truncated = finish_reason == "length"
            return ParseResult(
                outcome="clarify",
                reason="parser_truncated" if truncated else "unparsable",
                parser="llm",
                message=(
                    "I couldn't turn that into something I can model, and I won't guess. Try naming the "
                    "location or lane and the period range directly. " + _capabilities_sentence()
                ),
                **base,
            )
        parser = "llm"
        try:
            perturbation = _perturbation_from_payload(payload, state)
        except PerturbationError as exc:
            return ParseResult(
                outcome="refused", reason="unsupported_request", parser=parser,
                message=f"{exc} {_capabilities_sentence()}", **base,
            )
        # Defence in depth: the model may not supply a magnitude the planner never
        # gave. If its parse needs one and the sentence contains no magnitude at
        # all, ask rather than accept a plausible-looking invention.
        if _needs_magnitude(perturbation) and not _states_a_magnitude(text):
            return ParseResult(
                outcome="clarify",
                reason="magnitude_not_stated",
                parser=parser,
                missing=["multiplier"],
                message=_MISSING_QUESTIONS["multiplier"],
                **base,
            )

    if perturbation is None:
        asks = [_MISSING_QUESTIONS[key] for key in missing if key in _MISSING_QUESTIONS]
        return ParseResult(
            outcome="clarify",
            reason="incomplete_request",
            parser=parser,
            missing=missing,
            message=(" ".join(asks) if asks else "I couldn't tell what you want changed. " + _capabilities_sentence()),
            **base,
        )

    try:
        perturbation = validate(perturbation, state)
    except PerturbationError as exc:
        return ParseResult(
            outcome="refused", reason="invalid_perturbation", parser=parser,
            message=f"{exc} {_capabilities_sentence()}", **base,
        )

    impact: Impact = analyse(perturbation, state, recorded_latencies)
    card = build_confirmation_card(perturbation, state, impact)
    return ParseResult(
        outcome="parsed",
        reason="ready_for_confirmation",
        parser=parser,
        perturbation=perturbation.as_dict(),
        impact=impact.as_dict(),
        confirmation=card,
        message=card["reading"],
        executable=False,
        **base,
    )


def _needs_magnitude(perturbation: Perturbation) -> bool:
    """True for kinds whose meaning depends on a number the planner must supply.

    A node outage does not: "DC-001 is down" fully specifies zero capacity.
    """
    return perturbation.kind in {"lane_disruption", "demand_multiplier"}


def _states_a_magnitude(text: str) -> bool:
    """Does the sentence give a magnitude at all?

    Digits that are not magnitudes are stripped first, and both cases were found
    by test rather than by inspection:

    * period references — "demand changes in period 5" states no magnitude, and
      treating the 5 as one sends a clarifiable question off to be refused;
    * entity ids — ``CUST-001`` contains "001", which let a model-invented
      multiplier pass the very check meant to catch it.
    """
    text = ENTITY_ID.sub(" ", text)
    text = re.sub(r"\b(?:period|week)s?\s*#?\s*\d+(?:\s*(?:-|–|to|through|until|thru)\s*\d+)?", " ", text, flags=re.I)
    return bool(
        DOUBLE.search(text)
        or TRIPLE.search(text)
        or HALVE.search(text)
        or TO_ZERO_EXPLICIT.search(text)
        or TO_ZERO.search(text)
        or MULTIPLIER_X.search(text)
        or PERCENT_TO.search(text)
        or PERCENT_CHANGE.search(text)
        or re.search(r"\b(?:a\s+)?(?:third|quarter|fifth|tenth)\b", text, re.I)
        or re.search(r"\b\d+(?:\.\d+)?\b", text)
    )


def _looks_compound(text: str) -> bool:
    """Two distinct perturbation subjects in one sentence."""
    signals = 0
    if DEMAND_WORDS.search(text):
        signals += 1
    if OUTAGE_WORDS.search(text) or CAPACITY_WORDS.search(text):
        signals += 1
    # Two different entity ids of node/lane kind also implies two changes when
    # joined by "and": "if DC-001 and DC-002 both go down".
    ids = {match.group(0).upper() for match in ENTITY_ID.finditer(text)}
    if len(ids) > 1:
        signals += 1
    return signals > 1

