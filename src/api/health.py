"""
AI Jumpstart Service — API health endpoint (Phase 0).

Minimal FastAPI server providing:
- GET /health  — GPU/CUDA status, service readiness
- Mounts the embeddings and cuOpt/fallback routers

This is the single entrypoint for the `api` container.
"""

import subprocess
import os

from fastapi import FastAPI

app = FastAPI(
    title="Helix AI Jumpstart API",
    description="Secure API-first SCO prototype",
    version="0.3.0",
)


def _run_cmd(cmd: list[str]) -> tuple[bool, str]:
    """Run a subprocess, return (success, output)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15
        )
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)


@app.get("/health")
def health():
    """Health check — verifies GPU visibility and CUDA version inside the container."""
    # nvidia-smi check
    smi_ok, smi_out = _run_cmd(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])
    # nvcc version check
    nvcc_ok, nvcc_out = _run_cmd(["nvcc", "--version"])

    cuda_version = None
    if nvcc_ok:
        for line in nvcc_out.splitlines():
            if "release" in line.lower():
                # e.g. "Cuda compilation tools, release 13.0, V13.0.88"
                parts = line.split("release")
                if len(parts) > 1:
                    cuda_version = parts[1].split(",")[0].strip()

    gpu_name = None
    driver_version = None
    if smi_ok and smi_out:
        parts = smi_out.split(",")
        gpu_name = parts[0].strip() if len(parts) > 0 else None
        driver_version = parts[1].strip() if len(parts) > 1 else None

    return {
        "status": "ok",
        "gpu_visible": smi_ok,
        "gpu_name": gpu_name,
        "driver_version": driver_version,
        "cuda_version": cuda_version,
        "nvcc_available": nvcc_ok,
    }


# ---------------------------------------------------------------------------
# Mount sub-routers
# ---------------------------------------------------------------------------
from src.api.embeddings import router as embeddings_router  # noqa: E402

app.include_router(embeddings_router, prefix="/embeddings", tags=["embeddings"])

# Import cuopt/fallback router
from src.api.cuopt_smoke import router as cuopt_router  # noqa: E402

app.include_router(cuopt_router, prefix="/cuopt", tags=["cuopt"])

from src.api.pipeline import router as pipeline_router  # noqa: E402

app.include_router(pipeline_router, tags=["pipeline"])
