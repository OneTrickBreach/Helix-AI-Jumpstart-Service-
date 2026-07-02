"""GPU text ingestion scaffold used by the secure API layer."""

from __future__ import annotations

from functools import lru_cache


MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
EXPECTED_DIM = 768


@lru_cache(maxsize=1)
def get_embedding_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME, trust_remote_code=True, device="cuda")


def embed_texts(texts: list[str], prefix: str = "search_document: ") -> dict:
    model = get_embedding_model()
    prefixed = [f"{prefix}{text}" for text in texts]
    embeddings = model.encode(prefixed, show_progress_bar=False)
    return {
        "embeddings": embeddings.tolist(),
        "model": MODEL_NAME,
        "dimension": len(embeddings[0]) if len(embeddings) else EXPECTED_DIM,
        "device": str(model.device),
    }
