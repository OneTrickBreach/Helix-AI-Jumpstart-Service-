"""Iteration 6a decision 12 — the chat surface is untouched, and stays working.

Ryan parked the chat bot on 2026-08-19: *"not concerned about that right now"*. So
6a built nothing for it. But custom scenarios became **visible** to it for free,
because ``known_scenarios()`` unions the configs on disk with the generated data
directories — the same mechanism that puts a saved scenario in the dropdown.

Visible-for-free is exactly the situation that needs a regression test rather than
a feature. Two things have to hold:

**It must not break.** A custom scenario is a real scenario on disk, so every
grounded path — the facts bundle, the router, a what-if — has to work on one, or
6a has quietly broken a shipped surface.

**It must not claim it.** The chat layer answers questions about a *loaded*
scenario; it cannot build, save or delete one. Nothing in its vocabulary should
suggest otherwise, and a question asking it to do so must not be answered as
though it could.
"""

from __future__ import annotations

import pytest

from src.api.ratelimit import reset_limits
from src.chat.facts import build_fact_bundle
from src.dataset.overview import known_scenarios
from src.scenario import store
from src.scenario.synthesize import complete_config

TEST_MARKER = "pytest6a5"
SLUG = f"{TEST_MARKER}-chat"
SCENARIO = f"custom-{SLUG}"


@pytest.fixture(scope="module", autouse=True)
def saved_custom_scenario():
    """One saved custom scenario for the module, torn down afterwards."""
    reset_limits()
    for entry in store.list_custom():
        if TEST_MARKER in entry["scenario"]:
            store._remove(entry["scenario"])
    store.save(
        SLUG,
        complete_config(SCENARIO, overrides={"demand.base_units_per_customer_period": 53}),
    )
    yield SCENARIO
    store._remove(SCENARIO)
    reset_limits()


# ---------------------------------------------------------------------------
# it must not break
# ---------------------------------------------------------------------------


def test_a_custom_scenario_is_visible_to_the_chat_layer():
    """Free, via ``known_scenarios()`` — and therefore worth pinning."""
    assert SCENARIO in known_scenarios()


def test_the_facts_bundle_builds_for_a_custom_scenario():
    """The bundle is what every grounded answer is assembled from.

    Built without the corpus so this stays a structural check rather than a
    retrieval one, and without touching the LLM.
    """
    bundle = build_fact_bundle(SCENARIO, include_corpus=False)
    assert bundle.facts, "a custom scenario produced no facts at all"
    ids = {fact.fact_id for fact in bundle.facts}
    # The same dataset-derived facts the four recorded scenarios carry.
    assert any(fact_id.startswith("dataset.network.count.") for fact_id in ids)
    assert any(fact_id.startswith("dataset.demand.") for fact_id in ids)


def test_a_grounded_question_about_a_custom_scenario_is_answered(api_client, api_headers):
    response = api_client.post(
        "/chat/ask",
        json={
            "scenario": SCENARIO,
            "question": "How many distribution centers are there?",
            "use_llm": False,
        },
        headers=api_headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["route"] == "grounded"
    assert payload["citations"]
    # The guarantee that matters on any surface: no invented numbers.
    assert payload["grounding"]["numbers_ungrounded"] == 0
    # And the label stays on, because Ryan has not said to take it off.
    assert payload["beta"] is True


def test_the_404_split_still_holds_with_custom_scenarios_in_the_list(api_client, api_headers):
    """A saved custom scenario must not make an unknown name start resolving."""
    unknown = api_client.post(
        "/chat/ask",
        json={"scenario": "custom-definitely-not-saved", "question": "hi", "use_llm": False},
        headers=api_headers,
    )
    assert unknown.status_code == 404


def test_a_what_if_runs_on_a_custom_scenario_without_writing_to_it(api_client, api_headers):
    """The Iteration 5 engine on an Iteration 6a scenario.

    A what-if is an in-memory overlay, so the saved scenario's data has to come out
    byte-identical — the same promise the four recorded scenarios get.
    """
    before = {
        path.name: path.read_bytes()
        for path in sorted(store.data_dir(SCENARIO).glob("*.csv"))
    }
    response = api_client.post(
        "/chat/whatif",
        json={
            "scenario": SCENARIO,
            "perturbation": {
                "kind": "node_outage",
                "node_id": "DC-001",
                "from_period": 1,
                "to_period": 52,
            },
            "confirmed": True,
            "horizon": 4,
        },
        headers=api_headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["executed"] is True
    assert payload["base"]["objective"] > 0
    assert payload["what_if"]["objective"] > 0
    assert payload["is_what_if"] is True
    # The labelling that stops a what-if being mistaken for a recorded result has
    # to survive on a custom scenario too. `is_what_if` is the payload's marker;
    # the "WHAT-IF RESULT" band is the card's, asserted in the browser checks.
    assert payload["is_what_if"] is True
    assert payload["label"] == "BETA"
    assert payload["numeric_values_source"]

    after = {
        path.name: path.read_bytes()
        for path in sorted(store.data_dir(SCENARIO).glob("*.csv"))
    }
    assert after == before, "a what-if wrote to the custom scenario's generated data"


def test_the_confirm_card_works_on_a_custom_scenario(api_client, api_headers):
    """Nothing runs without confirmation — on a custom scenario too."""
    response = api_client.post(
        "/chat/whatif",
        json={
            "scenario": SCENARIO,
            "perturbation": {
                "kind": "node_outage",
                "node_id": "DC-001",
                "from_period": 1,
                "to_period": 52,
            },
            "confirmed": False,
        },
        headers=api_headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["executed"] is False
    assert payload["confirmation"]
    # Nothing ran: the confirmed-run keys are absent entirely.
    assert "base" not in payload and "what_if" not in payload


# ---------------------------------------------------------------------------
# it must not claim it
# ---------------------------------------------------------------------------


def test_the_chat_layer_does_not_offer_to_build_or_save_a_scenario():
    """Decision 12: visible, not claimed.

    The chat surface has no write path of any kind, and its vocabulary should not
    imply one. Checked against the shipped glossary and router sources rather than
    by asking the model, which is not deterministic.
    """
    from pathlib import Path

    chat_dir = Path(store.REPO_ROOT) / "src" / "chat"
    forbidden = ("save_custom", "scenario_name_for", "src.scenario.store", "from src.scenario")
    for path in sorted(chat_dir.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, (
                f"{path.name} reaches into the custom-scenario layer; decision 12 says "
                "the chat surface is untouched by 6a"
            )


def test_asking_the_chat_layer_to_build_a_scenario_is_not_answered_as_if_it_could(
    api_client, api_headers
):
    """It may decline, or answer about the data — it must not promise to build one."""
    response = api_client.post(
        "/chat/ask",
        json={
            "scenario": SCENARIO,
            "question": "Create and save a new scenario called my-test with double demand.",
            "use_llm": False,
        },
        headers=api_headers,
    )
    assert response.status_code == 200
    answer = response.json()["data"].get("answer") or ""
    lowered = answer.lower()
    for claim in ("i have created", "i've created", "i have saved", "i've saved", "scenario saved"):
        assert claim not in lowered, f"the chat layer claimed to have built a scenario: {answer!r}"


# The UI half of decision 12 is asserted in `web/src/chat/chatPanel.decision12.test.ts`:
# `web/` is deliberately not copied into the api image, so a pytest check on those
# files could only ever skip, and a guardrail that silently skips is not a guardrail.
