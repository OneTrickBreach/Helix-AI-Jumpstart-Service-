# =============================================================================
# AI Jumpstart Service — api container (Phase 0)
# =============================================================================
# Target hardware: NVIDIA GB10 (Grace Blackwell), arm64 / aarch64, CUDA 13.
# Base image MUST be arm64 — x86 images will not run on GB10.
#
# This Dockerfile builds the `api` service: a FastAPI server that also hosts
# the embeddings model (nomic-embed-text-v1.5 via sentence-transformers, GPU).
# Using the DEVEL variant so nvcc is available for CUDA 13 verification.
# =============================================================================

FROM nvcr.io/nvidia/cuda:13.0.1-devel-ubuntu24.04

# Avoid interactive prompts during package install
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# -----------------------------------------------------------------------------
# System dependencies
# -----------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# Python dependencies
# Pin arm64-compatible packages only.
# -----------------------------------------------------------------------------
COPY requirements-api.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements-api.txt

# -----------------------------------------------------------------------------
# Application code
# -----------------------------------------------------------------------------
COPY src/ ./src/
COPY tests/ ./tests/

# The embeddings model will be downloaded on first use and cached in this volume
ENV HF_HOME=/models/huggingface
ENV SENTENCE_TRANSFORMERS_HOME=/models/sentence-transformers

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["python3", "-m", "uvicorn", "src.api.health:app", "--host", "0.0.0.0", "--port", "8080"]
