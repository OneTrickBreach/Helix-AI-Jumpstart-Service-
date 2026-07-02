"""API-key auth dependency for protected PoC endpoints."""

from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException, status


API_KEY_ENV = "HELIX_API_KEY"


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Require the caller to present the API key configured in the environment."""
    expected = os.environ.get(API_KEY_ENV)
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{API_KEY_ENV} is not configured",
        )
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
