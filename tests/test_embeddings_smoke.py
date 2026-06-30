"""
Phase 0 — Embeddings smoke test.

Verifies:
- nomic-embed-text-v1.5 model loads on GPU inside the api container
- Returns a 768-dimensional embedding vector
- Multiple texts can be encoded
"""

import pytest


class TestEmbeddingsSmoke:
    """Smoke tests for the embeddings (nomic-embed-text-v1.5) service."""

    def test_embeddings_health(self, api_client):
        """GET /embeddings/health returns model info with correct dimension."""
        resp = api_client.get("/embeddings/health", timeout=120.0)
        assert resp.status_code == 200, f"Embeddings health returned {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["status"] == "ok"
        assert data["model"] == "nomic-ai/nomic-embed-text-v1.5"
        assert data["dimension"] == 768, f"Expected 768-dim, got {data['dimension']}"
        assert data["match"] is True

    def test_embeddings_encode_single(self, api_client):
        """POST /embeddings/encode returns a 768-dim vector for a single text."""
        resp = api_client.post(
            "/embeddings/encode",
            json={"texts": ["Supply chain optimization for manufacturing"]},
            timeout=60.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] == "nomic-ai/nomic-embed-text-v1.5"
        assert data["dimension"] == 768
        assert len(data["embeddings"]) == 1
        assert len(data["embeddings"][0]) == 768
        # Embedding values should be non-zero floats
        vec = data["embeddings"][0]
        assert any(v != 0.0 for v in vec), "All embedding values are zero"

    def test_embeddings_encode_batch(self, api_client):
        """POST /embeddings/encode handles multiple texts correctly."""
        texts = [
            "Inventory management",
            "Demand forecasting",
            "Vehicle routing optimization",
        ]
        resp = api_client.post(
            "/embeddings/encode",
            json={"texts": texts},
            timeout=60.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["embeddings"]) == 3
        for i, emb in enumerate(data["embeddings"]):
            assert len(emb) == 768, f"Text {i} embedding dim: {len(emb)}, expected 768"
