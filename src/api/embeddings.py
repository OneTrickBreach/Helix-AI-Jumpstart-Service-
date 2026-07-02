"""
AI Jumpstart Service — Embeddings endpoint (Phase 0).

Loads nomic-ai/nomic-embed-text-v1.5 (768-dim) via sentence-transformers on GPU.
Provides:
- GET  /embeddings/health  — test embedding to verify model loaded
- POST /embeddings/encode  — encode text into embedding vector(s)

Per the plan: embeddings run inside the `api` container (not a separate service).
"""

import os
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.security import require_api_key

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Lazy-load the model (first request triggers download + GPU load)
# ---------------------------------------------------------------------------
_model = None
MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
EXPECTED_DIM = 768


def _get_model():
    """Lazy-load the sentence-transformers model onto GPU."""
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {MODEL_NAME}")
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(
            MODEL_NAME,
            trust_remote_code=True,
            device="cuda",
        )
        logger.info(f"Embedding model loaded on device: {_model.device}")
    return _model


class EncodeRequest(BaseModel):
    texts: list[str]
    prefix: Optional[str] = "search_document: "


class EncodeResponse(BaseModel):
    embeddings: list[list[float]]
    model: str
    dimension: int


@router.get("/health")
def embeddings_health():
    """Encode a test string and return the embedding dimension to verify the model works."""
    try:
        model = _get_model()
        test_embedding = model.encode(
            ["search_document: test"], show_progress_bar=False
        )
        dim = len(test_embedding[0])
        return {
            "status": "ok",
            "model": MODEL_NAME,
            "dimension": dim,
            "expected_dimension": EXPECTED_DIM,
            "match": dim == EXPECTED_DIM,
            "device": str(model.device),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Embeddings model not ready: {e}")


@router.post("/encode", response_model=EncodeResponse, dependencies=[Depends(require_api_key)])
def encode(req: EncodeRequest):
    """Encode text(s) into embedding vector(s) using nomic-embed-text-v1.5."""
    try:
        model = _get_model()
        # nomic-embed expects a prefix for the task type
        prefixed = [f"{req.prefix}{t}" for t in req.texts]
        embeddings = model.encode(prefixed, show_progress_bar=False)
        return EncodeResponse(
            embeddings=embeddings.tolist(),
            model=MODEL_NAME,
            dimension=len(embeddings[0]),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Encoding failed: {e}")
