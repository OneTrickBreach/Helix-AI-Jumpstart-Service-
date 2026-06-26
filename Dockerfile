# =============================================================================
# AI Jumpstart Service — Container SCAFFOLD (placeholder, not a built product)
# =============================================================================
# Target hardware: NVIDIA GB10 (Grace Blackwell), arm64 / aarch64, CUDA 13.
# Base image MUST be arm64 — x86 images will not run on GB10.
#
# This Dockerfile is intentionally minimal. It exists to prove out GPU
# containerization and to give the build a starting point. No dependencies are
# installed yet: the dependency layer is deliberately left blank until the
# build phase begins (Points 3 & 4 — SCO scaffolding + synthetic dataset).
# =============================================================================

FROM nvcr.io/nvidia/cuda:13.0.1-runtime-ubuntu24.04

WORKDIR /app

# -----------------------------------------------------------------------------
# DEPENDENCIES GO HERE once Points 3/4 begin.
#   - Pin arm64-compatible packages only.
#   - Prefer NGC containers / wheels for PyTorch, RAPIDS, TensorRT-LLM, cuOpt.
#   - Do NOT add speculative pip installs before the build scope is set.
# Example (DO NOT UNCOMMENT until deps are decided at kickoff):
#   # COPY requirements.txt .
#   # RUN pip install --no-cache-dir -r requirements.txt
# -----------------------------------------------------------------------------
