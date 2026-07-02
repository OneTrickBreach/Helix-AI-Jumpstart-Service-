"""
AI Jumpstart Service — Test configuration (Phase 0).

Shared fixtures for Phase 0 smoke tests. Tests hit the service endpoints
via HTTP, so they work both inside the api container and from the host.
"""

import os
import pytest
import httpx
from pathlib import Path

# ---------------------------------------------------------------------------
# Service URLs — configurable via env vars for host vs. container execution
# ---------------------------------------------------------------------------
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8080")
LLM_BASE = os.environ.get("LLM_BASE_URL", "http://llm:8000")
QDRANT_BASE = os.environ.get("QDRANT_BASE_URL", "http://vectordb:6333")

# When running from host, use localhost ports
if os.environ.get("TEST_FROM_HOST", ""):
    LLM_BASE = "http://localhost:8000"
    QDRANT_BASE = "http://localhost:6333"
    API_BASE = "http://localhost:8080"


def _api_key() -> str | None:
    if os.environ.get("HELIX_API_KEY"):
        return os.environ["HELIX_API_KEY"]
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("HELIX_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


@pytest.fixture(scope="session")
def api_client():
    """HTTP client pointing at the api service."""
    with httpx.Client(base_url=API_BASE, timeout=60.0) as client:
        yield client


@pytest.fixture(scope="session")
def api_headers():
    key = _api_key()
    assert key, "HELIX_API_KEY must be configured for protected API tests"
    return {"X-API-Key": key}


@pytest.fixture(scope="session")
def llm_client():
    """HTTP client pointing at the llm (vLLM) service."""
    with httpx.Client(base_url=LLM_BASE, timeout=120.0) as client:
        yield client


@pytest.fixture(scope="session")
def qdrant_client_http():
    """HTTP client pointing at the Qdrant service."""
    with httpx.Client(base_url=QDRANT_BASE, timeout=30.0) as client:
        yield client
