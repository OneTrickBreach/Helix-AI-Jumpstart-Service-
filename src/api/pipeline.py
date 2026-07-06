"""Secure API endpoints for Phase 2/3 SCO workflows."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.security import require_api_key
from src.forecast.statistical import forecast_finished_goods
from src.ingest.documents import embed_texts
from src.ingest.state import load_scenario_state, summarize_state
from src.optimize.baseline.policy import optimize_baseline
from src.pipeline.bench import run_head_to_head
from src.pipeline.run import run_baseline_pipeline
from src.rag.advisory import generate_advisory_rationale


router = APIRouter(dependencies=[Depends(require_api_key)])


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


class GenericResponse(BaseModel):
    scenario: str | None = None
    status: Literal["ok"]
    data: dict[str, Any]


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
