"""
Phase 0 — Qdrant vector DB smoke test.

Verifies:
- Qdrant service is healthy
- Can create a collection
- Can insert vectors
- Can query and get the expected nearest result
"""

import pytest
import uuid


COLLECTION_NAME = f"phase0_smoke_test_{uuid.uuid4().hex[:8]}"


class TestQdrantSmoke:
    """Smoke tests for the Qdrant vector DB service."""

    def test_qdrant_health(self, qdrant_client_http):
        """Qdrant /healthz endpoint returns healthy."""
        resp = qdrant_client_http.get("/healthz")
        assert resp.status_code == 200

    def test_qdrant_create_collection(self, qdrant_client_http):
        """Create a test collection with 768 dimensions (matching nomic-embed)."""
        resp = qdrant_client_http.put(
            f"/collections/{COLLECTION_NAME}",
            json={
                "vectors": {
                    "size": 768,
                    "distance": "Cosine",
                }
            },
            timeout=10.0,
        )
        assert resp.status_code == 200, f"Create collection failed: {resp.text}"
        data = resp.json()
        assert data["result"] is True

    def test_qdrant_insert_and_query(self, qdrant_client_http):
        """Insert 3 vectors, query with one, and verify nearest neighbor."""
        # Ensure collection exists
        resp = qdrant_client_http.put(
            f"/collections/{COLLECTION_NAME}",
            json={
                "vectors": {
                    "size": 768,
                    "distance": "Cosine",
                }
            },
            timeout=10.0,
        )

        # Create 3 simple vectors (768-dim)
        import random
        random.seed(42)

        def make_vector(dim: int = 768) -> list[float]:
            """Create a random 768-dim vector."""
            return [random.gauss(0, 1) for _ in range(dim)]

        vec_a = make_vector()  # "cluster A"
        vec_b = make_vector()  # "cluster B" — independent random, far from A
        # vec_c is a small perturbation of vec_a — should be nearest neighbor
        vec_c = [v + random.gauss(0, 0.01) for v in vec_a]

        # Insert points
        resp = qdrant_client_http.put(
            f"/collections/{COLLECTION_NAME}/points",
            json={
                "points": [
                    {"id": 1, "vector": vec_a, "payload": {"label": "A"}},
                    {"id": 2, "vector": vec_b, "payload": {"label": "B"}},
                    {"id": 3, "vector": vec_c, "payload": {"label": "C_near_A"}},
                ]
            },
            timeout=10.0,
        )
        assert resp.status_code == 200, f"Insert failed: {resp.text}"

        # Wait briefly for indexing
        import time
        time.sleep(1)

        # Query with vec_a — nearest should be vec_c (id=3, very close to A)
        resp = qdrant_client_http.post(
            f"/collections/{COLLECTION_NAME}/points/query",
            json={
                "query": vec_a,
                "limit": 2,
                "with_payload": True,
            },
            timeout=10.0,
        )
        assert resp.status_code == 200, f"Query failed: {resp.text}"
        data = resp.json()
        points = data["result"]["points"]
        assert len(points) >= 2, f"Expected at least 2 results, got {len(points)}"

        # The nearest neighbor to vec_a should be vec_c (id=3)
        # (vec_a itself is id=1, which will be the top result with score ~1.0)
        ids_returned = [p["id"] for p in points]
        assert 1 in ids_returned, "vec_a (id=1) not in results"
        assert 3 in ids_returned, "vec_c (id=3, near A) not in results"

        # vec_c should be closer to vec_a than vec_b
        # Check ordering: id=1 (exact match) should be first, id=3 should be second
        assert points[0]["id"] == 1, f"Expected id=1 as top result, got {points[0]['id']}"
        assert points[1]["id"] == 3, f"Expected id=3 as second result, got {points[1]['id']}"

    def test_qdrant_cleanup(self, qdrant_client_http):
        """Clean up the test collection."""
        resp = qdrant_client_http.delete(f"/collections/{COLLECTION_NAME}")
        assert resp.status_code == 200
