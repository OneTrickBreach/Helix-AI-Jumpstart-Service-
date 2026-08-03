"""Secure API endpoints for Phase 2/3/5 SCO workflows."""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.responses import Response, StreamingResponse

from src.api.security import require_api_key
from src.chat.answer import answer_question
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


class ChatAskRequest(BaseModel):
    scenario: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    # Long enough for a real planner question, short enough that the chat surface
    # cannot be used to smuggle a large payload into the prompt path.
    question: str = Field(min_length=1, max_length=600)
    use_llm: bool = True


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
def chat_ask(req: ChatAskRequest):
    """Iteration 5 (BETA) — grounded read-only Q&A over one scenario.

    Runs no optimizer and mutates nothing: it answers from the generated data and
    the recorded benchmark artifacts. ``use_llm=false`` returns the deterministic
    template answer for the same facts, which is what the replay/GPU-free path
    and the test suite use.
    """
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
