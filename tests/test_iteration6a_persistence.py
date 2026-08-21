"""Iteration 6a Phase 2 — persistence: save, list, delete, clear-all.

The properties worth testing here are not "does save write a file". They are:

**A scenario is never half-saved.** ``known_scenarios()`` unions configs *and* data
directories, so a config written whose generation then failed would leave a
permanent dropdown entry that answers 409. Every failure path is asserted to leave
the box exactly as it was.

**The four canonical scenarios are untouchable** (guardrail 3), by save and by
delete, and clear-all selects on the ``custom-`` prefix rather than on "not one of
the four".

**A saved scenario is a real scenario.** It is discovered, it renders in the
Iteration 4 dataset view with a change list, and the generator can load it back —
with no changes to any of that code.

Every test cleans up after itself: these write into the real ``data/scenarios/``
and ``data/generated/``, because that is where the feature has to work. Benchmark
artifacts are already redirected for the whole session by ``isolate_benchmark_artifacts``.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from src.api.health import app
from src.api.ratelimit import reset_limits
from src.bench.profiler import benchmark_dir
from src.bench.suite import SCENARIOS as SUITE_SCENARIOS
from src.dataset.overview import build_dataset_overview, known_scenarios
from src.scenario import store
from src.scenario.synthesize import CANONICAL_SCENARIOS, complete_config

API_KEY = "test-key-iteration6a-phase2"
REPO_ROOT = Path(__file__).resolve().parents[1]

#: Every scenario these tests create carries this marker, so cleanup can be
#: exhaustive without ever reaching for a name a human might have saved.
TEST_MARKER = "pytest6a"


def _headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


def _slug(name: str) -> str:
    return f"{TEST_MARKER}-{name}"


def _config(slug: str, level: int = 40) -> dict:
    return complete_config(
        store.scenario_name_for(slug),
        overrides={"demand.base_units_per_customer_period": level},
    )


def _foreign_custom_scenarios() -> list[str]:
    """Custom scenarios on this box that these tests did not create.

    ``clear_all()`` is box-global by design (decision 14), so a test that calls it
    would delete a scenario a human saved — losing the one built for a demo. Any
    test that calls it therefore skips, loudly, when it would destroy real state.
    """
    return [
        entry["scenario"] for entry in store.list_custom()
        if TEST_MARKER not in entry["scenario"]
    ]


def _skip_if_it_would_destroy_real_scenarios() -> None:
    foreign = _foreign_custom_scenarios()
    if foreign:
        pytest.skip(
            "clear-all is box-global and would delete saved scenarios that these tests "
            f"did not create: {', '.join(foreign)}. Delete them first to run this test."
        )


def _purge() -> None:
    for entry in store.list_custom():
        if TEST_MARKER in entry["scenario"]:
            store._remove(entry["scenario"])
    for path in benchmark_dir().glob(f"custom-{TEST_MARKER}-*"):
        path.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def clean_slate():
    # The rate limiter is process-global and the save bucket is deliberately small
    # (20/60 s), which a test session exceeds long before a planner would. Resetting
    # per test keeps the limit meaningful in production without making the suite
    # depend on how many saves ran before it.
    reset_limits()
    _purge()
    yield
    _purge()
    reset_limits()


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _dir_fingerprint(path: Path) -> dict[str, str]:
    return {p.name: _md5(p) for p in sorted(path.iterdir()) if p.is_file()}


# ---------------------------------------------------------------------------
# the round trip
# ---------------------------------------------------------------------------


def test_save_then_list_then_delete():
    slug = _slug("roundtrip")
    saved = store.save(slug, _config(slug))
    assert saved["scenario"] == f"custom-{slug}"
    assert saved["created"] is True
    assert saved["generated"] is True

    listed = [entry["scenario"] for entry in store.list_custom()]
    assert f"custom-{slug}" in listed

    removed = store.delete(slug)
    assert removed["removed_count"] >= 2
    assert not store.exists(f"custom-{slug}")
    assert f"custom-{slug}" not in [entry["scenario"] for entry in store.list_custom()]


def test_a_saved_scenario_writes_all_nine_tables_and_metadata():
    slug = _slug("tables")
    store.save(slug, _config(slug))
    written = {p.name for p in store.data_dir(f"custom-{slug}").iterdir()}
    expected = {
        "nodes.csv", "skus.csv", "bom.csv", "demand.csv", "production_lines.csv",
        "lanes.csv", "lane_periods.csv", "service_targets.csv",
        "initial_inventory.csv", "metadata.json",
    }
    assert expected <= written


def test_the_saved_config_is_complete_and_the_generator_can_load_it_back():
    """§1.5: ``load_scenario`` has no defaults merge, so a sparse patch would break.

    Loading it back through the generator's own loader is the real check — that is
    the code path ``make data SCENARIO=custom-x`` takes.
    """
    slug = _slug("complete")
    store.save(slug, _config(slug))
    generator = store._generator()
    reloaded = generator.load_scenario(f"custom-{slug}")
    for group in ("simulation", "demand", "capacity", "lanes", "costs",
                  "service_targets", "network"):
        assert group in reloaded, f"saved config is missing {group}"
    assert reloaded["scenario"] == f"custom-{slug}"
    # Decision 7: the seed travels with the config, so a re-run is reproducible.
    assert reloaded["random_seed_override"] == 12345


def test_saving_the_same_config_twice_produces_byte_identical_data():
    """Guardrail 4 — reproducible or it does not ship."""
    slug = _slug("repro")
    store.save(slug, _config(slug))
    first = _dir_fingerprint(store.data_dir(f"custom-{slug}"))
    store.save(slug, _config(slug), overwrite=True)
    assert _dir_fingerprint(store.data_dir(f"custom-{slug}")) == first


# ---------------------------------------------------------------------------
# atomicity
# ---------------------------------------------------------------------------


def test_a_failed_generation_leaves_no_config_and_no_data(monkeypatch):
    slug = _slug("atomic")
    monkeypatch.setattr(
        store, "generate_guarded",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(store.StoreError):
        store.save(slug, _config(slug))
    assert not store.config_path(f"custom-{slug}").exists()
    assert not store.data_dir(f"custom-{slug}").exists()
    # The dropdown is the thing that must not be polluted.
    assert f"custom-{slug}" not in known_scenarios()
    assert f"custom-{slug}" not in [e["scenario"] for e in store.list_custom()]


def test_a_generator_system_exit_never_escapes(monkeypatch):
    """§1.5: ``load_scenario`` raises ``SystemExit``, which FastAPI cannot render.

    ``SystemExit`` does not inherit from ``Exception``, so a bare ``except
    Exception`` would let it through and take down the request handler.
    """
    slug = _slug("sysexit")
    generator = store._generator()
    monkeypatch.setattr(
        generator, "generate",
        lambda **k: (_ for _ in ()).throw(SystemExit("must declare scenario")),
    )
    with pytest.raises(store.GenerationFailed) as excinfo:
        store.save(slug, _config(slug))
    assert "must declare scenario" in str(excinfo.value)
    assert not store.config_path(f"custom-{slug}").exists()


def test_a_failed_overwrite_leaves_the_existing_scenario_untouched(monkeypatch):
    slug = _slug("overwrite")
    store.save(slug, _config(slug, level=40))
    config_before = store.config_path(f"custom-{slug}").read_text(encoding="utf-8")
    data_before = _dir_fingerprint(store.data_dir(f"custom-{slug}"))

    monkeypatch.setattr(
        store, "generate_guarded",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(store.StoreError):
        store.save(slug, _config(slug, level=99), overwrite=True)

    assert store.config_path(f"custom-{slug}").read_text(encoding="utf-8") == config_before
    assert _dir_fingerprint(store.data_dir(f"custom-{slug}")) == data_before


def test_a_successful_overwrite_replaces_the_data():
    slug = _slug("replace")
    store.save(slug, _config(slug, level=40))
    before = _dir_fingerprint(store.data_dir(f"custom-{slug}"))
    result = store.save(slug, _config(slug, level=99), overwrite=True)
    assert result["created"] is False
    assert _dir_fingerprint(store.data_dir(f"custom-{slug}")) != before


def test_saving_over_an_existing_scenario_without_overwrite_is_refused():
    slug = _slug("dup")
    store.save(slug, _config(slug))
    with pytest.raises(store.ScenarioExists):
        store.save(slug, _config(slug))


def test_no_staging_directory_survives_a_save():
    slug = _slug("staging")
    store.save(slug, _config(slug))
    leftover = list(store.STAGING_ROOT.iterdir()) if store.STAGING_ROOT.exists() else []
    assert leftover == []


# ---------------------------------------------------------------------------
# guardrail 3 — the canonical four
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", CANONICAL_SCENARIOS)
def test_a_canonical_name_is_refused_by_save(name):
    with pytest.raises(store.ScenarioProtected):
        store.save(name, _config(name))


@pytest.mark.parametrize("name", CANONICAL_SCENARIOS)
def test_a_canonical_name_is_refused_by_delete(name):
    """The raw slug is checked *before* prefixing.

    ``scenario_name_for("baseline")`` is ``"custom-baseline"``, which is not
    canonical — so without an explicit raw-slug guard this would report a
    misleading "no saved scenario named 'custom-baseline'" instead of saying why.
    """
    with pytest.raises(store.ScenarioProtected):
        store.delete(name)


@pytest.mark.parametrize("name", CANONICAL_SCENARIOS)
def test_saving_a_custom_scenario_does_not_touch_a_canonical_one(name):
    fingerprint = (
        _md5(store.config_path(name)),
        _dir_fingerprint(store.data_dir(name)),
    )
    slug = _slug("bystander")
    store.save(slug, _config(slug))
    store.delete(slug)
    assert (_md5(store.config_path(name)), _dir_fingerprint(store.data_dir(name))) == fingerprint


@pytest.mark.parametrize(
    "slug",
    ["../x", "../../etc/x", "..", "a/b", "a\\b", "UPPER", "has space", "dot.dot", "x" * 60, ""],
)
def test_the_store_refuses_an_illegal_slug_without_relying_on_the_caller(slug):
    """The API validates first, but ``save``/``delete`` are called directly too.

    ``custom-../../etc/x`` starts with ``custom-`` and resolves to
    ``data/scenarios/etc/x.yaml``, so the prefix check alone is not containment.
    """
    with pytest.raises(store.ScenarioProtected):
        store.save(slug, _config("irrelevant"))
    with pytest.raises(store.ScenarioProtected):
        store.delete(slug)


def test_a_traversing_name_is_refused_by_the_containment_check_too():
    """Belt and braces: the pattern is the belt, resolved-path containment the braces."""
    with pytest.raises(store.ScenarioProtected) as excinfo:
        store._require_contained("custom-../../etc/x")
    assert excinfo.value.code == "name_path_traversal"
    store._require_contained("custom-ordinary-name")  # must not raise


def test_a_seed_that_disagrees_with_the_config_is_refused():
    """Guardrail 4: a saved scenario must be reproducible from its own config."""
    slug = _slug("seed")
    config = _config(slug)
    assert config["random_seed_override"] == 12345
    with pytest.raises(store.StoreError) as excinfo:
        store.save(slug, config, seed=999)
    assert excinfo.value.code == "seed_mismatch"
    assert not store.config_path(f"custom-{slug}").exists()


def test_a_config_left_without_data_can_be_recovered_by_deleting_it():
    """The state the plan warns about, and the way out of it.

    ``known_scenarios()`` unions configs and data directories, so a config with no
    data answers 409 from the dropdown. Save refuses to overwrite it silently; the
    409 message says to delete it, and delete has to actually work on it.
    """
    scenario = f"custom-{_slug('orphan')}"
    store.config_path(scenario).write_text(f"scenario: {scenario}\n", encoding="utf-8")
    assert store.exists(scenario)
    with pytest.raises(store.ScenarioExists):
        store.save(_slug("orphan"), _config(_slug("orphan")))
    store.delete(_slug("orphan"))
    assert not store.exists(scenario)


def test_a_data_directory_without_a_config_is_listed_and_deletable():
    scenario = f"custom-{_slug('straydata')}"
    store.data_dir(scenario).mkdir(parents=True, exist_ok=True)
    entry = next(e for e in store.list_custom() if e["scenario"] == scenario)
    assert entry["generated"] is True
    assert entry["config_exists"] is False
    store.delete(_slug("straydata"))
    assert not store.exists(scenario)


def test_anything_outside_the_custom_namespace_is_refused():
    """Defence in depth, asserted directly.

    ``delete()`` cannot actually reach this branch, because ``scenario_name_for``
    always prefixes — which is the point: the guard is there so a future caller
    that builds the name differently still cannot touch a non-custom scenario.
    """
    for name in ("baseline", "some-other-scenario", "custom"):
        with pytest.raises(store.ScenarioProtected):
            store._require_custom(name)


# ---------------------------------------------------------------------------
# delete and clear-all
# ---------------------------------------------------------------------------


def test_delete_removes_the_config_the_data_and_the_recorded_artifacts():
    slug = _slug("artifacts")
    store.save(slug, _config(slug))
    scenario = f"custom-{slug}"
    made = []
    for path in store.benchmark_artifacts(scenario):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        made.append(path)

    store.delete(slug)
    assert not store.config_path(scenario).exists()
    assert not store.data_dir(scenario).exists()
    assert [p for p in made if p.exists()] == []


def test_deleting_a_slug_does_not_remove_a_longer_slugs_artifacts():
    """``custom-a`` and ``custom-a-b``: a ``custom-a-*`` glob would take both."""
    short, long = _slug("a"), _slug("a-b")
    store.save(short, _config(short))
    store.save(long, _config(long))
    keep = store.benchmark_artifacts(f"custom-{long}")[0]
    keep.parent.mkdir(parents=True, exist_ok=True)
    keep.write_text("{}", encoding="utf-8")

    store.delete(short)
    assert keep.exists()
    assert store.exists(f"custom-{long}")


def test_delete_also_drops_the_scenarios_vector_store_collection(monkeypatch):
    """Found in Phase 3, fixed here: guardrail 6 in the place it had a hole.

    Opting into a written rationale creates a per-scenario Qdrant collection. Save
    could create it and delete could not remove it, so the feature accumulated
    state in the vector store that clear-all left behind for ever.
    """
    calls: list[str] = []
    import src.rag.advisory as advisory

    monkeypatch.setattr(
        advisory, "delete_scenario_collection",
        lambda scenario: calls.append(scenario) or {
            "collection": f"helix_sco_rag_{scenario}", "deleted": True, "status_code": 200
        },
    )
    slug = _slug("vectorstore")
    store.save(slug, _config(slug))
    result = store.delete(slug)
    assert calls == [f"custom-{slug}"]
    assert f"qdrant:helix_sco_rag_custom-{slug}" in result["removed"]
    assert result["vector_store"]["deleted"] is True


def test_a_delete_still_succeeds_when_the_vector_store_is_unreachable(monkeypatch):
    """Cleanup is best effort: a delete must not fail because Qdrant is down."""
    import src.rag.advisory as advisory

    monkeypatch.setattr(
        advisory, "delete_scenario_collection",
        lambda scenario: {"collection": "x", "deleted": False, "error": "ConnectError: down"},
    )
    slug = _slug("qdrantdown")
    store.save(slug, _config(slug))
    result = store.delete(slug)
    assert not store.exists(f"custom-{slug}")
    assert result["vector_store"]["deleted"] is False
    assert not any(path.startswith("qdrant:") for path in result["removed"])


def test_clear_all_never_targets_a_canonical_vector_store_collection(monkeypatch):
    _skip_if_it_would_destroy_real_scenarios()
    calls: list[str] = []
    import src.rag.advisory as advisory

    monkeypatch.setattr(
        advisory, "delete_scenario_collection",
        lambda scenario: calls.append(scenario) or {"collection": scenario, "deleted": False},
    )
    slugs = [_slug("vs1"), _slug("vs2")]
    for slug in slugs:
        store.save(slug, _config(slug))
    store.clear_all()
    assert sorted(calls) == sorted(f"custom-{slug}" for slug in slugs)
    for canonical in CANONICAL_SCENARIOS:
        assert canonical not in calls


def test_clear_all_selects_only_the_custom_namespace_without_deleting_anything():
    """The selector, asserted non-destructively so it always runs.

    This is the half that matters for safety: clear-all's target list is exactly
    what ``list_custom()`` reports, and never one of the four.
    """
    slug = _slug("selector")
    store.save(slug, _config(slug))
    targets = [entry["scenario"] for entry in store.list_custom()]
    assert f"custom-{slug}" in targets
    assert all(name.startswith("custom-") for name in targets)
    for canonical in CANONICAL_SCENARIOS:
        assert canonical not in targets


def test_clear_all_removes_every_custom_scenario_and_nothing_else():
    _skip_if_it_would_destroy_real_scenarios()
    slugs = [_slug("clear1"), _slug("clear2")]
    for slug in slugs:
        store.save(slug, _config(slug))
    canonical_before = {
        name: (_md5(store.config_path(name)), _dir_fingerprint(store.data_dir(name)))
        for name in CANONICAL_SCENARIOS
    }

    result = store.clear_all()
    assert all(f"custom-{slug}" in result["deleted"] for slug in slugs)
    assert store.list_custom() == []
    for name in CANONICAL_SCENARIOS:
        assert (
            _md5(store.config_path(name)),
            _dir_fingerprint(store.data_dir(name)),
        ) == canonical_before[name]
    assert set(result["protected"]) == set(CANONICAL_SCENARIOS)


def test_clear_all_sweeps_an_orphaned_artifact_left_by_a_deleted_scenario():
    """Without this, "clear all" would leave artifacts for scenarios that are gone.

    A prefix glob is safe only here — every custom scenario has just been deleted,
    so the ``custom-a`` / ``custom-a-b`` collision that rules it out in ``_remove``
    cannot apply.
    """
    _skip_if_it_would_destroy_real_scenarios()
    orphan = benchmark_dir() / f"custom-{_slug('orphaned')}-head-to-head-comparison.json"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text("{}", encoding="utf-8")
    canonical_artifact = benchmark_dir() / "baseline-head-to-head-comparison.json"
    canonical_artifact.write_text("{}", encoding="utf-8")

    result = store.clear_all()
    assert not orphan.exists()
    assert canonical_artifact.exists(), "the sweep must only touch custom- artifacts"
    assert any("orphaned" in path for path in result["removed"])


def test_save_and_delete_leave_an_audit_line(caplog):
    """"Where did my scenario go?" has to have an answer.

    Saved scenarios are box-global and deleting one removes its config, data and
    recorded artifact. During Phase 5 review a reviewer's saved scenario vanished
    and there was no way to say what removed it — the container had been recreated
    and taken the access log with it.
    """
    import logging

    slug = _slug("audit")
    with caplog.at_level(logging.INFO, logger="helix.scenario.store"):
        store.save(slug, _config(slug))
        store.delete(slug)
    messages = [record.getMessage() for record in caplog.records]
    assert any(f"scenario_saved scenario=custom-{slug}" in message for message in messages)
    assert any(f"scenario_deleted scenario=custom-{slug}" in message for message in messages)


def test_clear_all_logs_a_warning_naming_what_it_removed(caplog):
    """Clear-all is the most destructive verb here, so it logs at WARNING."""
    _skip_if_it_would_destroy_real_scenarios()
    import logging

    slug = _slug("auditclear")
    store.save(slug, _config(slug))
    with caplog.at_level(logging.INFO, logger="helix.scenario.store"):
        store.clear_all()
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("scenarios_cleared" in message for message in warnings)
    assert any(f"custom-{slug}" in message for message in warnings)


def test_the_store_logger_actually_has_somewhere_to_write():
    """An audit line nobody can read is worse than none — it looks like one exists.

    Module loggers here had no handler, so the first version of this logged into
    the void while its own caplog test passed (pytest attaches a handler of its
    own). This asserts the production path: importing the app gives the ``helix``
    namespace a handler and an effective level that lets INFO through.
    """
    import logging

    import src.api.health  # noqa: F401  - importing configures app logging

    store_logger = logging.getLogger("helix.scenario.store")
    assert store_logger.isEnabledFor(logging.INFO), "INFO is filtered out in production"
    handlers = []
    current: logging.Logger | None = store_logger
    while current:
        handlers.extend(current.handlers)
        current = current.parent if current.propagate else None
    assert handlers, "no handler anywhere up the chain: the audit line goes nowhere"


def test_deleting_something_that_does_not_exist_is_a_not_found():
    with pytest.raises(store.ScenarioNotFound):
        store.delete(_slug("ghost"))


# ---------------------------------------------------------------------------
# a saved scenario is a real scenario — with no changes to Iteration 4 code
# ---------------------------------------------------------------------------


def test_a_saved_scenario_is_discovered_with_no_new_discovery_code():
    slug = _slug("discovery")
    store.save(slug, _config(slug))
    assert f"custom-{slug}" in known_scenarios()


def test_a_saved_scenario_renders_in_the_dataset_view_with_its_change_list():
    slug = _slug("datasetview")
    store.save(
        slug,
        complete_config(
            f"custom-{slug}",
            overrides={
                "demand.base_units_per_customer_period": 55,
                "capacity.capacity_tightness": 1.1,
            },
        ),
    )
    overview = build_dataset_overview(f"custom-{slug}")
    assert len(overview) == 13, "the dataset view lost or gained a section"
    diff = overview["scenario_diff"]
    assert diff["vs"] == "baseline"
    assert diff["comparable"] is True
    changed = {f"{c['group']}.{c['parameter']}" for c in diff["config_changes"]}
    assert "demand.base_units_per_customer_period" in changed
    assert "capacity.capacity_tightness" in changed


# ---------------------------------------------------------------------------
# §1.7 — a custom scenario cannot leak into the recorded suite
# ---------------------------------------------------------------------------


def test_the_recorded_suite_still_sees_exactly_four_scenarios():
    slug = _slug("noleak")
    store.save(slug, _config(slug))
    assert SUITE_SCENARIOS == (
        "baseline", "component-shortage-shock", "demand-surge", "stress-large",
    )
    assert f"custom-{slug}" not in SUITE_SCENARIOS


def test_bench_all_and_demo_data_iterate_a_literal_list_of_four():
    """The Makefile's own loops, read rather than assumed."""
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    for target in ("bench-all", "demo-data"):
        block = re.search(rf"^{target}:.*?(?=^\S|\Z)", makefile, re.S | re.M)
        assert block, f"{target} not found in the Makefile"
        body = block.group(0)
        assert "for scenario in baseline component-shortage-shock demand-surge stress-large" in body
        assert "custom" not in body


def test_gitignore_covers_a_saved_scenarios_config_data_and_artifacts():
    """A saved scenario is box-local state and must not become an untracked file.

    Asserted on the patterns, because ``git check-ignore`` needs a ``.git``
    directory and ``.dockerignore`` deliberately keeps that out of the image. When
    the suite does run somewhere with git available, the behaviour is checked too.
    """
    patterns = {
        line.strip()
        for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert "data/scenarios/custom-*.yaml" in patterns, "a saved config would be untracked"
    assert "data/**/generated/" in patterns, "generated custom data would be committed"
    assert "benchmark/*.json" in patterns, "a custom run's artifact would be committed"
    # The canonical configs are the recorded benchmark inputs: they stay tracked.
    for name in CANONICAL_SCENARIOS:
        assert f"data/scenarios/{name}.yaml" not in patterns

    if not (REPO_ROOT / ".git").exists():
        return
    def ignored(path: str) -> bool:
        return subprocess.run(
            ["git", "check-ignore", "-q", path], cwd=REPO_ROOT, check=False
        ).returncode == 0
    assert ignored("data/scenarios/custom-example.yaml")
    assert ignored("data/generated/custom-example/demand.csv")
    assert ignored("benchmark/custom-example-head-to-head-comparison.json")
    for name in CANONICAL_SCENARIOS:
        assert not ignored(f"data/scenarios/{name}.yaml")


# ---------------------------------------------------------------------------
# the API surface
# ---------------------------------------------------------------------------


def test_the_persistence_endpoints_require_the_api_key(monkeypatch):
    monkeypatch.setenv("HELIX_API_KEY", API_KEY)
    client = TestClient(app)
    assert client.post("/scenarios/custom", json={"name": "x"}).status_code == 401
    assert client.get("/scenarios/custom").status_code == 401
    assert client.delete("/scenarios/custom").status_code == 401
    assert client.delete("/scenarios/custom/x").status_code == 401


def test_the_save_endpoint_saves_lists_and_deletes(monkeypatch):
    monkeypatch.setenv("HELIX_API_KEY", API_KEY)
    client = TestClient(app)
    slug = _slug("api")
    response = client.post(
        "/scenarios/custom",
        headers=_headers(),
        json={"name": slug, "simple": {"demand_level": 50}},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["saved"]["scenario"] == f"custom-{slug}"
    assert data["config_changes_count"] >= 1
    assert "CUSTOM SCENARIO" in data["label"]

    listed = client.get("/scenarios/custom", headers=_headers()).json()["data"]
    assert f"custom-{slug}" in [entry["scenario"] for entry in listed["scenarios"]]

    # It shows up in the ordinary scenario list too, which is what populates the
    # dropdown — no new discovery code (§0.2).
    scenarios = client.get("/scenarios", headers=_headers()).json()["data"]["scenarios"]
    assert f"custom-{slug}" in [entry["scenario"] for entry in scenarios]

    deleted = client.delete(f"/scenarios/custom/{slug}", headers=_headers())
    assert deleted.status_code == 200
    assert not store.exists(f"custom-{slug}")


def test_the_save_endpoint_refuses_an_invalid_config_before_writing(monkeypatch):
    monkeypatch.setenv("HELIX_API_KEY", API_KEY)
    client = TestClient(app)
    slug = _slug("invalid")
    response = client.post(
        "/scenarios/custom",
        headers=_headers(),
        json={"name": slug, "overrides": {"service_targets.fill_rate_target": 9}},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert [r["code"] for r in detail["validation"]["refusals"]] == ["above_maximum"]
    # Decision 11: refuse before anything reaches the disk.
    assert not store.config_path(f"custom-{slug}").exists()
    assert not store.data_dir(f"custom-{slug}").exists()


def test_the_save_endpoint_returns_409_on_a_duplicate(monkeypatch):
    monkeypatch.setenv("HELIX_API_KEY", API_KEY)
    client = TestClient(app)
    slug = _slug("dupapi")
    body = {"name": slug}
    assert client.post("/scenarios/custom", headers=_headers(), json=body).status_code == 200
    again = client.post("/scenarios/custom", headers=_headers(), json=body)
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "already_exists"


@pytest.mark.parametrize("name", CANONICAL_SCENARIOS)
def test_the_api_refuses_to_save_or_delete_a_canonical_scenario(monkeypatch, name):
    monkeypatch.setenv("HELIX_API_KEY", API_KEY)
    client = TestClient(app)
    saved = client.post("/scenarios/custom", headers=_headers(), json={"name": name})
    assert saved.status_code == 422
    assert "name_reserved" in [
        r["code"] for r in saved.json()["detail"]["validation"]["refusals"]
    ]
    removed = client.delete(f"/scenarios/custom/{name}", headers=_headers())
    assert removed.status_code == 409
    assert removed.json()["detail"]["code"] == "protected_scenario"


def test_the_clear_all_endpoint_only_touches_custom_scenarios(monkeypatch):
    _skip_if_it_would_destroy_real_scenarios()
    monkeypatch.setenv("HELIX_API_KEY", API_KEY)
    client = TestClient(app)
    slug = _slug("clearapi")
    client.post("/scenarios/custom", headers=_headers(), json={"name": slug})
    response = client.delete("/scenarios/custom", headers=_headers())
    assert response.status_code == 200
    data = response.json()["data"]
    assert f"custom-{slug}" in data["deleted"]
    for canonical in CANONICAL_SCENARIOS:
        assert store.config_path(canonical).exists()
        assert store.data_dir(canonical).is_dir()


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "../../etc/passwd"},
        {"name": ""},
        {"name": "UPPER"},
        {"name": "x" * 200},
        # Iteration 6b: `network.plants: 3` is legitimate work now — it is close to
        # the thing Ryan actually asked for — so the hostile case is a network value
        # that cannot be RUN, not a network key per se.
        {"name": "ok", "overrides": {"network.plants": 0}},
        {"name": "ok", "overrides": {"network.distribution_centers": 0}},
        {"name": "ok", "overrides": {"network.customers": 99999}},
        {"name": "ok", "overrides": {"network.warehouses": 2}},
        {"name": "ok", "overrides": {"simulation.horizon_periods": True}},
        {"name": "ok", "simple": {"holding_cost": "lots"}},
        {"name": "ok", "simple": {"demand_spike": 3}},
        {"name": "ok", "simple": {"not_a_control": 1}},
        {"name": "ok", "overrides": {"nope.nope": 1}},
    ],
)
def test_hostile_save_payloads_are_refused_never_a_500(monkeypatch, payload):
    """Guardrail 5: never a 500, and never a write."""
    monkeypatch.setenv("HELIX_API_KEY", API_KEY)
    client = TestClient(app)
    try:
        response = client.post("/scenarios/custom", headers=_headers(), json=payload)
        assert response.status_code in (409, 422), response.text
        leaked = list(store.SCENARIO_CONFIG_ROOT.glob("custom-ok.yaml"))
        assert not leaked, f"a payload that should have been refused wrote {leaked}"
    finally:
        # 🔴 Every case here shares the name `custom-ok`, so a single unexpectedly
        # ACCEPTED payload used to leave its config on disk and turn every later
        # case into a phantom failure — five misleading reds pointing at the wrong
        # payload. Clean up regardless of outcome: the assertion above still fails
        # for the payload that actually misbehaved, and only for that one.
        client.delete("/scenarios/custom/custom-ok", headers=_headers())
