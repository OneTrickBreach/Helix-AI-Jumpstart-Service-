"""Persistence for custom scenarios: save, list, delete, clear-all.

Iteration 6a Phase 2. A saved custom scenario is **an ordinary scenario** — a
complete YAML in ``data/scenarios/`` plus generated data in ``data/generated/`` —
so ``known_scenarios()``, ``GET /scenarios``, the dataset view and the config-delta
panel all pick it up with no new discovery code (§0.2).

Three properties this module exists to guarantee:

**Save is atomic.** ``known_scenarios()`` unions configs *and* data directories, so
a config written whose generation then failed would leave a permanent dropdown
entry that answers 409 for ever. Generation therefore runs into a staging directory
outside ``data/generated/`` and is moved into place only on success; on any failure
the config is restored to exactly what it was (removed if it was new).

**The generator's ``SystemExit`` never crosses the API boundary.** ``load_scenario``
reports every error by raising it (§1.5), and FastAPI cannot render that.

**The four canonical scenarios are untouchable.** Guardrail 3: their names are
refused by save *and* by delete, and clear-all selects on the ``custom-`` prefix
rather than on "everything that is not one of the four".
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.scenario.synthesize import CANONICAL_SCENARIOS, SCENARIO_CONFIG_ROOT
from src.scenario.validate import CUSTOM_PREFIX, scenario_name_for, validate_slug

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DATA_ROOT = REPO_ROOT / "data" / "generated"
#: Staging lives beside ``generated`` rather than inside it, because
#: ``known_scenarios()`` lists every directory in ``generated`` — a half-built
#: scenario in there would appear in the dropdown while it was still being written.
STAGING_ROOT = REPO_ROOT / "data" / ".custom-staging"

#: The exact artifact names the pipeline writes per scenario. Deliberately an
#: explicit list and not a ``custom-<slug>-*`` glob: deleting ``custom-a`` with a
#: glob would also delete ``custom-a-b``'s artifacts.
BENCHMARK_ARTIFACT_SUFFIXES = (
    "-head-to-head-comparison.json",
    "-rag-advisory-rationale.json",
    "-baseline-plan-metrics.json",
    "-baseline-resource-profile.json",
)


class StoreError(Exception):
    """Base class for a refusal that the API turns into a 4xx."""

    code = "store_error"
    status_code = 400

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class ScenarioExists(StoreError):
    code = "already_exists"
    status_code = 409


class ScenarioNotFound(StoreError):
    code = "not_found"
    status_code = 404


class ScenarioProtected(StoreError):
    """A canonical scenario, or anything outside the ``custom-`` namespace."""

    code = "protected_scenario"
    status_code = 409


class GenerationFailed(StoreError):
    code = "generation_failed"
    status_code = 422


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------


def config_path(scenario: str) -> Path:
    return SCENARIO_CONFIG_ROOT / f"{scenario}.yaml"


def data_dir(scenario: str) -> Path:
    return GENERATED_DATA_ROOT / scenario


def benchmark_artifacts(scenario: str) -> list[Path]:
    """Every recorded artifact that belongs to ``scenario``, existing or not."""
    from src.bench.profiler import benchmark_dir

    root = benchmark_dir()
    return [root / f"{scenario}{suffix}" for suffix in BENCHMARK_ARTIFACT_SUFFIXES]


def is_custom(scenario: str) -> bool:
    return scenario.startswith(CUSTOM_PREFIX)


def reject_canonical_slug(slug: str) -> None:
    """Refuse a raw slug naming one of the four, before any prefixing.

    Defence in depth for guardrail 3. ``scenario_name_for("baseline")`` is
    ``"custom-baseline"``, which is *not* canonical — so without this check the
    store would happily treat "baseline" as a new custom scenario, and a delete
    would report the misleading "no saved scenario named 'custom-baseline'"
    instead of saying why the name is refused. The validation layer catches this
    too; this makes the guarantee independent of it being called.
    """
    if isinstance(slug, str) and slug.strip().lower() in CANONICAL_SCENARIOS:
        raise ScenarioProtected(
            f"'{slug.strip()}' is one of the four recorded benchmark scenarios. Its "
            "configuration, data and recorded results are never modified by the "
            "custom-scenario feature. Pick a different name."
        )


def _require_custom(scenario: str) -> None:
    """Refuse anything this module is not allowed to touch.

    Both halves matter. The canonical four are named explicitly so the refusal
    says *why*; the prefix check then catches every other scenario that a caller
    might reach for, including one that does not exist yet.
    """
    if scenario in CANONICAL_SCENARIOS:
        raise ScenarioProtected(
            f"'{scenario}' is one of the four recorded benchmark scenarios. Its "
            "configuration, data and recorded results are never modified by the "
            "custom-scenario feature."
        )
    if not is_custom(scenario):
        raise ScenarioProtected(
            f"'{scenario}' is not a custom scenario. Only scenarios named "
            f"'{CUSTOM_PREFIX}<name>' can be saved or deleted here."
        )


def _require_valid_slug(slug: str) -> None:
    """Re-check the name here, rather than trusting the caller to have done it.

    The API validates before it ever reaches this module, but ``save`` and
    ``delete`` are library functions that Phase 3 and Phase 4 call directly. A
    guarantee that depends on every future caller remembering to validate first is
    not a guarantee. Reuses Phase 1's rules so there is one definition of a legal
    name, and reports the first refusal as a sentence.
    """
    raw = slug.strip() if isinstance(slug, str) else ""
    # Strip the namespace prefix case-insensitively, but validate what the caller
    # actually wrote. Lower-casing first would make the store accept "UPPER" while
    # the API refuses it — two layers disagreeing about what a legal name is.
    bare = raw[len(CUSTOM_PREFIX):] if raw.lower().startswith(CUSTOM_PREFIX) else raw
    result = validate_slug(bare)
    if not result.ok:
        refusal = result.refusals[0]
        raise ScenarioProtected(refusal.message, code=refusal.code)


def _require_contained(scenario: str) -> None:
    """Refuse a name whose paths would land outside the two roots we own.

    Modelled on ``_resolve_scenario_dir``'s containment check: the belt is the slug
    pattern, this is the braces. ``custom-../../etc/x`` satisfies "starts with
    custom-" and resolves to ``data/scenarios/etc/x.yaml``, so prefix checks alone
    are not enough.
    """
    checks = (
        (config_path(scenario), SCENARIO_CONFIG_ROOT),
        (data_dir(scenario), GENERATED_DATA_ROOT),
    )
    for path, root in checks:
        if path.resolve().parent != root.resolve():
            raise ScenarioProtected(
                f"'{scenario}' is not a legal scenario name: it would write outside "
                f"{root.name}/. Use lower-case letters, numbers and hyphens.",
                code="name_path_traversal",
            )


def exists(scenario: str) -> bool:
    """True if anything on disk would make this name appear in the dropdown."""
    return config_path(scenario).exists() or data_dir(scenario).exists()


# ---------------------------------------------------------------------------
# generation, guarded
# ---------------------------------------------------------------------------


def _generator() -> Any:
    cached = sys.modules.get("_helix_generator")
    if cached is not None:
        return cached
    path = REPO_ROOT / "data" / "generator" / "generate.py"
    spec = importlib.util.spec_from_file_location("_helix_generator", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise GenerationFailed(f"cannot load the generator from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_helix_generator"] = module
    spec.loader.exec_module(module)
    return module


def generate_guarded(scenario: str, seed: int, output_dir: Path) -> None:
    """Run the real generator, converting every failure into a ``StoreError``.

    This is the same ``generate()`` that ``make data SCENARIO=...`` calls, so a
    saved custom scenario's data is produced by the code path the four shipped
    scenarios use — not by a parallel implementation that could drift.

    ``SystemExit`` is caught explicitly because ``load_scenario`` raises it for
    every input problem (§1.5) and it does **not** inherit from ``Exception``, so
    a bare ``except Exception`` would let it through and take down the request.
    """
    generator = _generator()
    try:
        generator.generate(seed=seed, scenario=scenario, output_dir=output_dir)
    except SystemExit as exc:
        raise GenerationFailed(
            f"The generator refused the configuration for '{scenario}': {exc}"
        ) from exc
    except Exception as exc:  # noqa: BLE001 - the boundary has to be total
        raise GenerationFailed(
            f"Generating data for '{scenario}' failed: {type(exc).__name__}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------


@dataclass
class _ConfigBackup:
    """Enough to put ``data/scenarios/`` back exactly as it was."""

    path: Path
    previous: str | None

    def restore(self) -> None:
        if self.previous is None:
            self.path.unlink(missing_ok=True)
        else:
            self.path.write_text(self.previous, encoding="utf-8")


def save(
    slug: str,
    config: dict[str, Any],
    seed: int | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Write the config, generate the data, and report what happened.

    Order matters and is forced on us: the generator reads
    ``data/scenarios/<name>.yaml`` by name, so the config has to be on disk before
    generation can run. Everything after that point is written to staging and moved
    into place atomically, and any failure restores the config.
    """
    reject_canonical_slug(slug)
    _require_valid_slug(slug)
    scenario = scenario_name_for(slug)
    _require_custom(scenario)
    _require_contained(scenario)
    if config.get("scenario") != scenario:
        raise StoreError(
            f"The configuration declares scenario '{config.get('scenario')}' but is "
            f"being saved as '{scenario}'. The generator requires them to match.",
            code="config_name_mismatch",
        )

    already = exists(scenario)
    if already and not overwrite:
        raise ScenarioExists(
            f"A scenario named '{scenario}' already exists. Delete it first, or save "
            "under a different name."
        )

    cfg_path = config_path(scenario)
    backup = _ConfigBackup(
        cfg_path, cfg_path.read_text(encoding="utf-8") if cfg_path.exists() else None
    )
    # The config is the source of truth for the seed (decision 7), and
    # ``generate()`` prefers ``random_seed_override`` over its own argument. A
    # caller passing a different seed would get data that its own saved config
    # cannot reproduce, so that disagreement is refused rather than resolved.
    recorded_seed = config.get("random_seed_override")
    if seed is not None and recorded_seed is not None and int(seed) != int(recorded_seed):
        raise StoreError(
            f"The seed given ({int(seed)}) does not match the seed in the configuration "
            f"({int(recorded_seed)}). A saved scenario has to be reproducible from its own "
            "config, so these cannot differ.",
            code="seed_mismatch",
        )
    effective_seed = int(recorded_seed if recorded_seed is not None else (seed or 12345))

    staging = STAGING_ROOT / scenario
    final = data_dir(scenario)
    superseded = final.with_name(f".superseded-{scenario}")
    had_data = final.exists()

    try:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(
            yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        _rmtree_quiet(staging)
        staging.parent.mkdir(parents=True, exist_ok=True)
        generate_guarded(scenario, effective_seed, staging)

        # Swap in. ``os.replace`` on a directory is atomic within one filesystem
        # but will not replace a non-empty target, so an overwrite moves the old
        # data aside first and it is discarded only once the new data is in place.
        final.parent.mkdir(parents=True, exist_ok=True)
        _rmtree_quiet(superseded)
        if had_data:
            os.replace(final, superseded)
        try:
            os.replace(staging, final)
        except OSError:
            if had_data and superseded.exists() and not final.exists():
                os.replace(superseded, final)
            raise
    except StoreError:
        _rollback(scenario, staging, backup, had_data)
        raise
    except Exception as exc:  # noqa: BLE001 - never leave a half-saved scenario
        _rollback(scenario, staging, backup, had_data)
        raise GenerationFailed(
            f"Saving '{scenario}' failed and was rolled back: {type(exc).__name__}: {exc}"
        ) from exc

    # Past the point of no return: the new data is in place and the config matches
    # it. Clearing the superseded copy is housekeeping, and a failure here must not
    # be reported as a failed save.
    _rmtree_quiet(superseded)
    return summary(scenario, created=not already)


def _rmtree_quiet(path: Path) -> None:
    try:
        if path.exists():
            shutil.rmtree(path)
    except OSError:  # pragma: no cover - best effort
        pass


def _rollback(scenario: str, staging: Path, backup: _ConfigBackup, had_data: bool) -> None:
    """Put the box back as it was. Never raises — it runs on the failure path.

    The invariant it restores is the one that matters: a scenario is either fully
    present (config **and** data) or fully absent. A config with no data is the
    state that would answer 409 from the dropdown for ever.
    """
    final = data_dir(scenario)
    superseded = final.with_name(f".superseded-{scenario}")
    _rmtree_quiet(staging)
    try:
        if superseded.exists():
            if final.exists():
                _rmtree_quiet(superseded)
            else:
                os.replace(superseded, final)
    except OSError:  # pragma: no cover - best effort
        pass
    if not had_data:
        # We created it in this call, so removing it cannot lose anything. The swap
        # is the last statement in the try block, so reaching here means it did not
        # complete.
        _rmtree_quiet(final)
    try:
        backup.restore()
    except OSError:  # pragma: no cover - best effort
        pass


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


def read_config(scenario: str) -> dict[str, Any]:
    path = config_path(scenario)
    if not path.exists():
        raise ScenarioNotFound(f"No saved scenario named '{scenario}'.")
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise StoreError(f"The saved configuration for '{scenario}' is not readable.")
    return config


def summary(scenario: str, created: bool | None = None) -> dict[str, Any]:
    """What a caller needs to show a saved scenario in a list or after saving."""
    cfg_path = config_path(scenario)
    data_path = data_dir(scenario)
    config: dict[str, Any] | None = None
    if cfg_path.exists():
        loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        config = loaded if isinstance(loaded, dict) else None
    payload: dict[str, Any] = {
        "scenario": scenario,
        "slug": scenario[len(CUSTOM_PREFIX):] if is_custom(scenario) else scenario,
        "is_custom": is_custom(scenario),
        "description": (config or {}).get("description"),
        "seed": (config or {}).get("random_seed_override"),
        "horizon_periods": ((config or {}).get("simulation") or {}).get("horizon_periods"),
        "generated": data_path.is_dir(),
        "config_exists": cfg_path.exists(),
        "saved_at": (
            # Whole seconds: a float timestamp reads like a precision we do not have.
            int(cfg_path.stat().st_mtime) if cfg_path.exists() else None
        ),
        "has_recorded_run": any(path.exists() for path in benchmark_artifacts(scenario)),
        "label": "CUSTOM SCENARIO — not one of the four recorded benchmark results",
    }
    if created is not None:
        payload["created"] = created
    return payload


def list_custom() -> list[dict[str, Any]]:
    """Every custom scenario on the box, from configs *and* stray data directories.

    Unions the same two sources ``known_scenarios()`` does, so this list cannot
    disagree with the dropdown — including about a scenario that only half exists.
    """
    names = {
        path.stem for path in SCENARIO_CONFIG_ROOT.glob(f"{CUSTOM_PREFIX}*.yaml")
    }
    if GENERATED_DATA_ROOT.exists():
        names.update(
            path.name
            for path in GENERATED_DATA_ROOT.iterdir()
            if path.is_dir() and is_custom(path.name)
        )
    return [summary(name) for name in sorted(names)]


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def delete(slug: str) -> dict[str, Any]:
    """Remove a custom scenario's config, its data and its recorded artifacts."""
    reject_canonical_slug(slug)
    _require_valid_slug(slug)
    scenario = scenario_name_for(slug)
    _require_custom(scenario)
    _require_contained(scenario)
    if not exists(scenario):
        raise ScenarioNotFound(f"No saved scenario named '{scenario}'.")
    return _remove(scenario)


def _remove(scenario: str) -> dict[str, Any]:
    removed: list[str] = []
    cfg_path = config_path(scenario)
    if cfg_path.exists():
        cfg_path.unlink()
        removed.append(str(cfg_path.relative_to(REPO_ROOT)))
    data_path = data_dir(scenario)
    if data_path.exists():
        shutil.rmtree(data_path)
        removed.append(str(data_path.relative_to(REPO_ROOT)))
    # A rationale run creates a per-scenario Qdrant collection. Guardrail 6: if
    # saving can create it, deleting has to remove it, or clear-all quietly leaves
    # a vector store full of scenarios that no longer exist. Best effort by design
    # — a delete must not fail because the vector store is unreachable.
    from src.rag.advisory import delete_scenario_collection

    vector_store = delete_scenario_collection(scenario)
    if vector_store.get("deleted"):
        removed.append(f"qdrant:{vector_store['collection']}")

    for artifact in benchmark_artifacts(scenario):
        if artifact.exists():
            artifact.unlink()
            try:
                removed.append(str(artifact.relative_to(REPO_ROOT)))
            except ValueError:
                # HELIX_BENCHMARK_DIR can point outside the repo (the test suite
                # does exactly that, which is why it cannot clobber the demo's
                # recorded artifacts).
                removed.append(str(artifact))
    return {
        "scenario": scenario,
        "removed": removed,
        "removed_count": len(removed),
        "vector_store": vector_store,
    }


def clear_all() -> dict[str, Any]:
    """Delete every custom scenario, and nothing else.

    Selects on the ``custom-`` prefix. That is the point of the prefix: the
    alternative — "delete everything that is not one of the four" — would turn a
    typo in the canonical list into data loss.
    """
    scenarios = [entry["scenario"] for entry in list_custom()]
    results = [_remove(scenario) for scenario in scenarios]
    removed = [path for result in results for path in result["removed"]]

    # Sweep orphaned artifacts: a run writes benchmark/custom-<slug>-*.json, and a
    # scenario removed by some other route (or by a test whose artifact directory
    # was redirected) can leave those behind. A prefix glob is safe *here* and
    # nowhere else, because every custom scenario has just been deleted — so the
    # custom-a / custom-a-b collision that rules out globbing in `_remove` cannot
    # apply. Without this, "clear all" would not actually clear everything.
    removed.extend(_sweep_orphaned_artifacts())
    return {
        "deleted": [result["scenario"] for result in results],
        "deleted_count": len(results),
        "removed": removed,
        "protected": list(CANONICAL_SCENARIOS),
    }


def _sweep_orphaned_artifacts() -> list[str]:
    """Delete every ``custom-*`` benchmark artifact. Only safe once nothing custom exists."""
    from src.bench.profiler import benchmark_dir

    swept: list[str] = []
    root = benchmark_dir()
    if not root.is_dir():
        return swept
    for path in sorted(root.glob(f"{CUSTOM_PREFIX}*.json")):
        try:
            path.unlink()
        except OSError:  # pragma: no cover - best effort
            continue
        try:
            swept.append(str(path.relative_to(REPO_ROOT)))
        except ValueError:
            swept.append(str(path))
    return swept
