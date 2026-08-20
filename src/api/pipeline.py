"""Secure API endpoints for Phase 2/3/5 SCO workflows."""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import Response, StreamingResponse

from src.api.ratelimit import enforce
from src.api.security import require_api_key
from src.bench.profiler import benchmark_dir
from src.chat.answer import answer_question
from src.chat.intent import parse_intent
from src.chat.perturbation import Perturbation, PerturbationError
from src.chat.whatif import confirmation_for, run_what_if
from src.dataset.overview import (
    DatasetNotGeneratedError,
    UnknownScenarioError,
    build_dataset_overview,
    read_table_csv,
)
from src.forecast.statistical import forecast_finished_goods
from src.ingest.documents import embed_texts
from src.ingest.state import load_scenario_state, summarize_state
from src.optimize.baseline.policy import optimize_baseline
from src.pipeline.bench import run_head_to_head
from src.pipeline.run import run_baseline_pipeline
from src.rag.advisory import generate_advisory_rationale
from src.scenario.api import custom_settings_payload
from src.scenario.preview import build_preview
from src.scenario.store import (
    StoreError,
    clear_all as clear_custom_scenarios,
    delete as delete_custom_scenario,
    list_custom as list_custom_scenarios,
    save as save_custom_scenario,
)
from src.scenario.synthesize import CANONICAL_SCENARIOS


router = APIRouter(dependencies=[Depends(require_api_key)])
REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_CONFIG_ROOT = REPO_ROOT / "data" / "scenarios"
GENERATED_DATA_ROOT = REPO_ROOT / "data" / "generated"


class ScenarioRequest(BaseModel):
    scenario: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9._-]+$")
    horizon: int = Field(default=8, ge=1, le=52)


class TextIngestRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=64)
    prefix: str = Field(default="search_document: ", max_length=64)


class BenchmarkRequest(ScenarioRequest):
    ppo_timesteps: int = Field(default=128, ge=16, le=4096)


class RAGCorpusDocument(BaseModel):
    source_type: str = Field(default="planner_note", min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=8000)


class RAGRationaleRequest(BenchmarkRequest):
    top_k: int = Field(default=5, ge=1, le=10)
    corpus_documents: list[RAGCorpusDocument] = Field(default_factory=list, max_length=32)


class ScenarioComparisonRequest(RAGRationaleRequest):
    pass


class ChatParseRequest(BaseModel):
    scenario: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    question: str = Field(min_length=1, max_length=600)
    use_llm: bool = True


class PerturbationModel(BaseModel):
    """The perturbation to run. Re-validated server-side; the client is never trusted."""

    kind: Literal["node_outage", "lane_disruption", "demand_multiplier"]
    from_period: int = Field(ge=1, le=520)
    to_period: int = Field(ge=1, le=520)
    node_id: str | None = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9._-]+$")
    lane_id: str | None = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9._-]+$")
    capacity_multiplier: float | None = Field(default=None, ge=0.0, le=10.0)
    demand_multiplier: float | None = Field(default=None, ge=0.0, le=10.0)
    scope: Literal["all", "customer", "sku"] | None = None
    scope_id: str | None = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9._-]+$")


class ChatWhatIfRequest(BaseModel):
    scenario: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    perturbation: PerturbationModel
    # Decision 6: nothing runs without explicit confirmation. An unconfirmed
    # request gets the card back, not a queued job.
    confirmed: bool = False
    horizon: int = Field(default=8, ge=1, le=52)
    include_ppo: bool = False
    ppo_timesteps: int = Field(default=128, ge=16, le=4096)
    # Force a recomputation instead of serving an identical earlier result. Useful
    # for a "re-run" control and for tests that must not depend on a cold cache.
    # Phase 5 owns rate limiting, which is what stops this being a cheap way to
    # keep the box busy.
    fresh: bool = False


class ChatAskRequest(BaseModel):
    scenario: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    # Long enough for a real planner question, short enough that the chat surface
    # cannot be used to smuggle a large payload into the prompt path.
    question: str = Field(min_length=1, max_length=600)
    use_llm: bool = True


class CustomScenarioPreviewRequest(BaseModel):
    """Iteration 6a Phase 1 — preview a custom scenario. Writes nothing, runs nothing.

    ``name`` deliberately carries no regex here. Decision 11 is validate-then-refuse
    in plain English, and a pydantic pattern mismatch would surface as a 422 with a
    regex in it. ``validate_slug`` produces a sentence a planner can act on instead;
    the length bound is all that is needed to stop an oversized payload.
    """

    name: str = Field(min_length=1, max_length=64)
    overrides: dict[str, Any] = Field(default_factory=dict, max_length=200)
    simple: dict[str, Any] = Field(default_factory=dict, max_length=32)
    seed: int = Field(default=12345, ge=0, le=2_147_483_647)
    description: str | None = Field(default=None, max_length=280)
    horizon: int = Field(default=8, ge=1, le=52)
    include_ppo: bool = False
    include_rationale: bool = False


class CustomScenarioSaveRequest(CustomScenarioPreviewRequest):
    """Iteration 6a Phase 2 — save a custom scenario.

    Same body as the preview, so what a planner previewed is exactly what gets
    saved, plus ``overwrite``. Overwriting is explicit rather than implied: a
    silent overwrite of a scenario someone else on the box built is not a
    behaviour worth defaulting to (decision 14 — storage is box-global).
    """

    overwrite: bool = False


class GenericResponse(BaseModel):
    scenario: str | None = None
    status: Literal["ok"]
    data: dict[str, Any]


def _scenario_configs() -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    for path in sorted(SCENARIO_CONFIG_ROOT.glob("*.yaml")):
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        name = str(config.get("scenario") or path.stem)
        generated = GENERATED_DATA_ROOT / name
        scenarios.append(
            {
                "scenario": name,
                "description": config.get("description"),
                "generated": generated.exists(),
                "config_path": str(path.relative_to(REPO_ROOT)),
                "generated_path": str(generated.relative_to(REPO_ROOT))
                if generated.exists()
                else None,
                "horizon_periods": (config.get("simulation") or {}).get("horizon_periods"),
                "criticality_tier": (config.get("service_targets") or {}).get("criticality_tier"),
            }
        )
    generated_only = {
        path.name
        for path in GENERATED_DATA_ROOT.iterdir()
        if path.is_dir() and not (SCENARIO_CONFIG_ROOT / f"{path.name}.yaml").exists()
    } if GENERATED_DATA_ROOT.exists() else set()
    for name in sorted(generated_only):
        scenarios.append(
            {
                "scenario": name,
                "description": None,
                "generated": True,
                "config_path": None,
                "generated_path": str((GENERATED_DATA_ROOT / name).relative_to(REPO_ROOT)),
                "horizon_periods": None,
                "criticality_tier": None,
            }
        )
    return scenarios


def _recorded_latencies(scenario: str) -> dict[str, float]:
    """Per-approach latencies from the recorded run, for the confirm card's estimate.

    Returns an empty mapping when no run is on record; the estimator then falls
    back to conservative defaults rather than inventing a figure.
    """
    path = benchmark_dir() / f"{scenario}-head-to-head-comparison.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {
        str(row["approach"]): float(row["latency_seconds"])
        for row in payload.get("comparison", [])
        if "approach" in row and "latency_seconds" in row
    }


def _run_scenario_comparison(
    req: ScenarioComparisonRequest,
    progress_callback: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    benchmark_result = run_head_to_head(
        req.scenario,
        horizon=req.horizon,
        ppo_timesteps=req.ppo_timesteps,
        progress_callback=progress_callback,
    )
    if progress_callback is not None:
        progress_callback("rag", "running")
    rationale = generate_advisory_rationale(
        benchmark_result=benchmark_result,
        top_k=req.top_k,
        extra_documents=[
            doc.model_dump() if hasattr(doc, "model_dump") else doc.dict()
            for doc in req.corpus_documents
        ],
    )
    if progress_callback is not None:
        progress_callback("rag", "complete")
    return {
        "benchmark": benchmark_result,
        "rationale": rationale,
    }


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, sort_keys=True)}\n\n"


@router.get("/scenarios", response_model=GenericResponse)
def list_scenarios():
    return GenericResponse(status="ok", data={"scenarios": _scenario_configs()})


@router.get("/scenarios/custom/settings", response_model=GenericResponse)
def custom_scenario_settings():
    """The settings ledger: every editable setting, its range, and what it can change.

    Read-only. This is the honest-labelling surface — each setting carries the
    reach it *earned* from the two derivations in :mod:`src.scenario.ledger`, so
    the Advanced tier can show the 13 + 1 settings that cannot move the answer
    under decision 15's heading rather than as live controls.
    """
    return GenericResponse(status="ok", data=custom_settings_payload())


@router.post("/scenarios/custom/preview", response_model=GenericResponse)
def custom_scenario_preview(req: CustomScenarioPreviewRequest, request: Request):
    """Resolve a custom scenario and report on it **without writing or running anything**.

    Returns the complete config the edits resolve to, the diff against ``baseline``,
    the ``reaches_optimizer`` verdict for any lane disruption, and a run estimate
    with its basis. Persistence is Phase 2; execution is Phase 3.
    """
    enforce(request, bucket="light")
    payload = build_preview(
        req.name,
        overrides=req.overrides or None,
        simple=req.simple or None,
        seed=req.seed,
        description=req.description,
        run_horizon=req.horizon,
        include_ppo=req.include_ppo,
        include_rationale=req.include_rationale,
    )
    return GenericResponse(scenario=payload["scenario"], status="ok", data=payload)


def _store_error(exc: StoreError) -> HTTPException:
    """Turn a store refusal into the status code the posture already uses."""
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )


@router.post("/scenarios/custom", response_model=GenericResponse)
def custom_scenario_save(req: CustomScenarioSaveRequest, request: Request):
    """Validate, write the config, generate the data, and report what was saved.

    Decision 11 is validate-then-refuse-then-write: an infeasible configuration is
    turned down in plain English *before* anything reaches the disk. The config
    that gets written is the one ``build_preview`` resolved, so the preview and the
    saved file cannot disagree.
    """
    enforce(request, bucket="save")
    preview = build_preview(
        req.name,
        overrides=req.overrides or None,
        simple=req.simple or None,
        seed=req.seed,
        description=req.description,
        run_horizon=req.horizon,
        include_ppo=req.include_ppo,
        include_rationale=req.include_rationale,
    )
    if not preview["validation"]["ok"]:
        # 422 with the whole preview: the caller gets every refusal at once, plus
        # the resolved config it would have saved, which is what makes the message
        # actionable rather than just negative.
        raise HTTPException(status_code=422, detail=preview)
    try:
        saved = save_custom_scenario(
            req.name,
            preview["resolved_config"],
            seed=req.seed,
            overwrite=req.overwrite,
        )
    except StoreError as exc:
        raise _store_error(exc) from exc
    return GenericResponse(
        scenario=saved["scenario"],
        status="ok",
        data={
            "saved": saved,
            "validation": preview["validation"],
            "config_changes": preview["config_changes"],
            "config_changes_count": preview["config_changes_count"],
            "capacity_reachability": preview["capacity_reachability"],
            "run_estimate": preview["run_estimate"],
            "label": preview["label"],
        },
    )


@router.get("/scenarios/custom", response_model=GenericResponse)
def custom_scenario_list(request: Request):
    """Every custom scenario saved on this box (decision 14: box-global)."""
    enforce(request, bucket="light")
    scenarios = list_custom_scenarios()
    return GenericResponse(
        status="ok",
        data={
            "scenarios": scenarios,
            "count": len(scenarios),
            "protected": list(CANONICAL_SCENARIOS),
            "storage": "This box. Saved scenarios are visible to anyone who can reach it.",
        },
    )


@router.delete("/scenarios/custom", response_model=GenericResponse)
def custom_scenario_clear_all(request: Request):
    """Delete every custom scenario. Selects on the ``custom-`` prefix only."""
    enforce(request, bucket="save")
    return GenericResponse(status="ok", data=clear_custom_scenarios())


@router.delete("/scenarios/custom/{slug}", response_model=GenericResponse)
def custom_scenario_delete(slug: str, request: Request):
    """Delete one custom scenario: its config, its data and its artifacts."""
    enforce(request, bucket="save")
    try:
        removed = delete_custom_scenario(slug)
    except StoreError as exc:
        raise _store_error(exc) from exc
    return GenericResponse(scenario=removed["scenario"], status="ok", data=removed)


@router.get("/dataset/overview", response_model=GenericResponse)
def dataset_overview(
    scenario: str = Query(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$"),
):
    """Pre-aggregated, deterministic description of a scenario's dataset."""
    try:
        return GenericResponse(
            scenario=scenario,
            status="ok",
            data={"dataset_overview": build_dataset_overview(scenario)},
        )
    except UnknownScenarioError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except DatasetNotGeneratedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/dataset/table")
def dataset_table(
    scenario: str = Query(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$"),
    table: str = Query(min_length=1, max_length=64, pattern=r"^[a-z_]+$"),
):
    """Download one whitelisted table of one scenario as raw CSV."""
    try:
        filename, csv_text = read_table_csv(scenario, table)
    except UnknownScenarioError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except DatasetNotGeneratedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{scenario}-{filename}"',
        },
    )


@router.post("/chat/ask", response_model=GenericResponse)
def chat_ask(
    req: ChatAskRequest,
    request: Request,
    response: Response,
    x_session_id: str | None = Header(default=None),
):
    """Iteration 5 (BETA) — grounded read-only Q&A over one scenario.

    Runs no optimizer and mutates nothing: it answers from the generated data and
    the recorded benchmark artifacts. ``use_llm=false`` returns the deterministic
    template answer for the same facts, which is what the replay/GPU-free path
    and the test suite use.

    Rate limited (Phase 5): a question is cheap but not free — it holds the local
    model for a couple of seconds.
    """
    response.headers.update(enforce(request, "ask", x_session_id))
    try:
        result = answer_question(
            req.question,
            req.scenario,
            llm=None if req.use_llm else False,
        )
        return GenericResponse(scenario=req.scenario, status="ok", data=result.as_dict())
    except UnknownScenarioError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except DatasetNotGeneratedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/chat/parse", response_model=GenericResponse)
def chat_parse(
    req: ChatParseRequest,
    request: Request,
    response: Response,
    x_session_id: str | None = Header(default=None),
):
    """Iteration 5 (BETA) — read a what-if sentence into a validated perturbation.

    **This endpoint does not execute anything.** It returns a parse plus a
    confirm-before-run card, a clarifying question, or a refusal. Running a
    perturbation through the real pipeline is Phase 3; there is deliberately no
    execution path at this checkpoint, which is why every payload carries
    ``executable: false``.
    """
    response.headers.update(enforce(request, "ask", x_session_id))
    try:
        result = parse_intent(
            req.question,
            req.scenario,
            llm=None if req.use_llm else False,
            recorded_latencies=_recorded_latencies(req.scenario),
        )
        return GenericResponse(scenario=req.scenario, status="ok", data=result.as_dict())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=f"Scenario data has not been generated yet: {exc}")


def _perturbation_from_request(req: ChatWhatIfRequest) -> Perturbation:
    payload = req.perturbation
    return Perturbation(
        kind=payload.kind,
        scenario=req.scenario,
        from_period=payload.from_period,
        to_period=payload.to_period,
        node_id=payload.node_id,
        lane_id=payload.lane_id,
        capacity_multiplier=payload.capacity_multiplier,
        demand_multiplier=payload.demand_multiplier,
        scope=payload.scope,
        scope_id=payload.scope_id,
    )


@router.post("/chat/whatif", response_model=GenericResponse)
def chat_whatif(
    req: ChatWhatIfRequest,
    request: Request,
    response: Response,
    x_session_id: str | None = Header(default=None),
):
    """Iteration 5 (BETA) — run one validated perturbation through the real pipeline.

    ``confirmed=false`` returns the confirm-before-run card and runs nothing.
    ``confirmed=true`` re-validates the perturbation server-side, applies it as an
    in-memory overlay, and returns real before/after numbers from the same code
    path on both sides. The generated data is never written to.

    Rate limited (Phase 5), and only a *confirmed* request counts against the run
    budget: asking for the card costs nothing but a file read, and a planner
    reconsidering a wording should not burn their allowance.
    """
    response.headers.update(
        enforce(request, "run" if req.confirmed else "light", x_session_id, counts_as_run=req.confirmed)
    )
    perturbation = _perturbation_from_request(req)
    try:
        if not req.confirmed:
            return GenericResponse(
                scenario=req.scenario,
                status="ok",
                data={
                    "executed": False,
                    "reason": "confirmation_required",
                    "confirmation": confirmation_for(
                        perturbation, recorded_latencies=_recorded_latencies(req.scenario)
                    ),
                },
            )
        result = run_what_if(
            perturbation,
            horizon=req.horizon,
            include_ppo=req.include_ppo,
            ppo_timesteps=req.ppo_timesteps,
            use_cache=not req.fresh,
        )
        return GenericResponse(
            scenario=req.scenario, status="ok", data={"executed": True, **result.as_dict()}
        )
    except PerturbationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=f"Scenario data has not been generated yet: {exc}")


@router.get("/chat/whatif/stream")
def chat_whatif_stream(
    request: Request,
    scenario: str = Query(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$"),
    kind: Literal["node_outage", "lane_disruption", "demand_multiplier"] = Query(),
    from_period: int = Query(ge=1, le=520),
    to_period: int = Query(ge=1, le=520),
    node_id: str | None = Query(default=None, max_length=32, pattern=r"^[A-Za-z0-9._-]+$"),
    lane_id: str | None = Query(default=None, max_length=32, pattern=r"^[A-Za-z0-9._-]+$"),
    capacity_multiplier: float | None = Query(default=None, ge=0.0, le=10.0),
    demand_multiplier: float | None = Query(default=None, ge=0.0, le=10.0),
    scope: Literal["all", "customer", "sku"] | None = Query(default=None),
    scope_id: str | None = Query(default=None, max_length=32, pattern=r"^[A-Za-z0-9._-]+$"),
    horizon: int = Query(default=8, ge=1, le=52),
    include_ppo: bool = Query(default=False),
    confirmed: bool = Query(default=False),
    fresh: bool = Query(default=False),
    # EventSource cannot set headers, so the browser passes its session id here.
    # Same validation as the header form; an unusable value simply means the
    # per-session run cap does not apply, never that the window does not.
    session_id: str | None = Query(default=None, max_length=64, pattern=r"^[A-Za-z0-9._-]+$"),
):
    """Stream a what-if with TRUTHFUL stage events, same pattern as the benchmark stream.

    A worker thread runs the real engine and pushes (stage, status) at the actual
    boundaries; this generator drains them. No stage is announced before it starts
    and none is marked complete before it finishes.

    Rate limited before the worker starts, so a refused request never reaches the
    optimizer — but the refusal is delivered **in-band, as an SSE `error` event**,
    unlike `POST /chat/whatif` which returns a normal HTTP 429. The reason is the
    client: `EventSource` cannot read a status code or a response body, so a 429 here
    would reach the browser as an indistinguishable connection failure and the panel
    would have to guess at the cause. Sending the reason down the channel the client
    is already listening on is the only way it can say something true. The cost is
    that this response carries no `X-RateLimit-*` headers, because the limit is not
    checked until the body starts streaming.
    """
    req = ChatWhatIfRequest(
        scenario=scenario,
        perturbation=PerturbationModel(
            kind=kind,
            from_period=from_period,
            to_period=to_period,
            node_id=node_id,
            lane_id=lane_id,
            capacity_multiplier=capacity_multiplier,
            demand_multiplier=demand_multiplier,
            scope=scope,
            scope_id=scope_id,
        ),
        confirmed=confirmed,
        horizon=horizon,
        include_ppo=include_ppo,
        fresh=fresh,
    )
    perturbation = _perturbation_from_request(req)

    def events():
        event_queue: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()

        def progress(stage: str, status: str) -> None:
            event_queue.put(("stage", {"stage": stage, "status": status, "message": f"{stage} {status}"}))

        def worker() -> None:
            try:
                try:
                    enforce(request, "run" if confirmed else "light", session_id, counts_as_run=confirmed)
                except HTTPException as exc:
                    event_queue.put(
                        ("error", {"status": "rate_limited", "detail": str(exc.detail)})
                    )
                    return
                if not req.confirmed:
                    event_queue.put(
                        (
                            "confirm",
                            {
                                "executed": False,
                                "reason": "confirmation_required",
                                "confirmation": confirmation_for(
                                    perturbation, recorded_latencies=_recorded_latencies(scenario)
                                ),
                            },
                        )
                    )
                    return
                result = run_what_if(
                    perturbation,
                    horizon=req.horizon,
                    include_ppo=req.include_ppo,
                    progress_callback=progress,
                    use_cache=not req.fresh,
                )
                event_queue.put(("done", {"executed": True, **result.as_dict()}))
            except PerturbationError as exc:
                event_queue.put(("error", {"status": "error", "detail": str(exc)}))
            except Exception as exc:  # noqa: BLE001 - surfaced to the client as an SSE error
                event_queue.put(("error", {"status": "error", "detail": f"What-if failed: {exc}"}))
            finally:
                event_queue.put(None)

        worker_thread = threading.Thread(target=worker, daemon=True)
        worker_thread.start()
        while True:
            item = event_queue.get()
            if item is None:
                break
            event_name, data = item
            yield _sse_event(event_name, data)
        worker_thread.join()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/ingest/scenario", response_model=GenericResponse)
def ingest_scenario(req: ScenarioRequest):
    try:
        state = load_scenario_state(req.scenario)
        return GenericResponse(scenario=req.scenario, status="ok", data=summarize_state(state))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/ingest/text", response_model=GenericResponse)
def ingest_text(req: TextIngestRequest):
    try:
        return GenericResponse(status="ok", data=embed_texts(req.texts, prefix=req.prefix))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Text ingestion failed: {exc}")


@router.post("/forecast", response_model=GenericResponse)
def forecast(req: ScenarioRequest):
    try:
        state = load_scenario_state(req.scenario)
        return GenericResponse(
            scenario=req.scenario,
            status="ok",
            data=forecast_finished_goods(state, horizon=req.horizon),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/optimize/baseline", response_model=GenericResponse)
def baseline_optimize(req: ScenarioRequest):
    try:
        state = load_scenario_state(req.scenario)
        forecast_data = forecast_finished_goods(state, horizon=req.horizon)
        return GenericResponse(
            scenario=req.scenario,
            status="ok",
            data=optimize_baseline(state, forecast_data),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/pipeline/run", response_model=GenericResponse)
def run_pipeline(req: ScenarioRequest):
    try:
        return GenericResponse(
            scenario=req.scenario,
            status="ok",
            data=run_baseline_pipeline(req.scenario, horizon=req.horizon),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/pipeline/bench", response_model=GenericResponse)
def benchmark(req: BenchmarkRequest):
    try:
        return GenericResponse(
            scenario=req.scenario,
            status="ok",
            data=run_head_to_head(
                req.scenario,
                horizon=req.horizon,
                ppo_timesteps=req.ppo_timesteps,
            ),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/rag/rationale", response_model=GenericResponse)
def rag_rationale(req: RAGRationaleRequest):
    try:
        benchmark_result = run_head_to_head(
            req.scenario,
            horizon=req.horizon,
            ppo_timesteps=req.ppo_timesteps,
        )
        rationale = generate_advisory_rationale(
            benchmark_result=benchmark_result,
            top_k=req.top_k,
            extra_documents=[
                doc.model_dump() if hasattr(doc, "model_dump") else doc.dict()
                for doc in req.corpus_documents
            ],
        )
        return GenericResponse(scenario=req.scenario, status="ok", data=rationale)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"RAG rationale failed: {exc}")


@router.post("/scenario-comparison", response_model=GenericResponse)
def scenario_comparison(req: ScenarioComparisonRequest):
    try:
        return GenericResponse(
            scenario=req.scenario,
            status="ok",
            data=_run_scenario_comparison(req),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Scenario comparison failed: {exc}")


@router.get("/scenario-comparison/stream")
def scenario_comparison_stream(
    scenario: str = Query(min_length=1, pattern=r"^[a-zA-Z0-9._-]+$"),
    horizon: int = Query(default=8, ge=1, le=52),
    ppo_timesteps: int = Query(default=128, ge=16, le=4096),
    top_k: int = Query(default=5, ge=1, le=10),
):
    req = ScenarioComparisonRequest(
        scenario=scenario,
        horizon=horizon,
        ppo_timesteps=ppo_timesteps,
        top_k=top_k,
    )

    def events():
        # Stream TRUTHFUL progress: a worker thread runs the real pipeline and
        # pushes (stage, status) events onto a queue at the actual boundaries of
        # each stage (via progress_callback), while this generator drains the
        # queue and emits them as they happen. This avoids both faking progress
        # up front and duplicating the benchmark orchestration logic.
        event_queue: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()

        def progress(stage: str, status: str) -> None:
            event_queue.put(
                (
                    "stage",
                    {
                        "stage": stage,
                        "status": status,
                        "message": f"{stage} stage {status}",
                    },
                )
            )

        def worker() -> None:
            try:
                payload = _run_scenario_comparison(req, progress_callback=progress)
                event_queue.put(
                    ("done", {"scenario": scenario, "status": "ok", "data": payload})
                )
            except FileNotFoundError as exc:
                event_queue.put(("error", {"status": "error", "detail": str(exc)}))
            except Exception as exc:  # noqa: BLE001 - surfaced to client as an SSE error event
                event_queue.put(
                    (
                        "error",
                        {"status": "error", "detail": f"Scenario comparison failed: {exc}"},
                    )
                )
            finally:
                event_queue.put(None)

        worker_thread = threading.Thread(target=worker, daemon=True)
        worker_thread.start()
        while True:
            item = event_queue.get()
            if item is None:
                break
            event_name, data = item
            yield _sse_event(event_name, data)
        worker_thread.join()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
