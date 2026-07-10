# =============================================================================
# AI Jumpstart Service — LLM service (Phase 0)
# =============================================================================
# Serves NVIDIA Nemotron-3-Nano-30B-A3B FP8 via vLLM (OpenAI-compatible API).
# Target: arm64 / aarch64, CUDA 13, GB10.
#
# The vLLM image handles model download + serving. Model weights are cached
# in a volume mount to avoid re-downloading on container rebuild.
# =============================================================================

FROM vllm/vllm-openai:latest

# The model to serve — NVIDIA Nemotron 3 Nano 30B (MoE), FP8 quantized
ENV MODEL_NAME="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8"

# HuggingFace cache inside the container (volume-mounted for persistence)
ENV HF_HOME=/models/huggingface

# vLLM configuration — no custom env needed; defaults work for GB10

EXPOSE 8000

# -----------------------------------------------------------------------------
# UNIFIED-MEMORY BUDGET (GB10, ~121 GiB usable shared CPU+GPU pool)
# -----------------------------------------------------------------------------
# On the GB10 the "GPU memory" vLLM sizes against via NVML is the SAME 121 GiB
# pool used by the OS, the api container (PyTorch + nomic-embed), and Qdrant.
# --gpu-memory-utilization is a fraction of that shared pool, so it must be set
# low enough to co-exist with every other consumer or the whole device OOMs and
# wedges into an "nvidia-container-cli: gpu requires reset" state (observed once
# on 2026-07-09 with the earlier 0.6 setting + a redundant GPU container while
# running the full 4-scenario suite).
#
# Budget at 0.45:  vLLM ~54 GiB  (Nemotron 30B A3B FP8 weights ~30 GiB + KV/CUDA
# graphs) ; leaves ~67 GiB for api (PyTorch+embeddings ~4 GiB), Qdrant, the OS,
# and the suite's Polars frames (stress-large is the largest). Comfortable margin.

# Health check against the vLLM /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=600s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

# Launch vLLM server
# The base image ENTRYPOINT is ["vllm", "serve"] — CMD provides the model + flags
# --kv-cache-dtype fp8 for memory efficiency on the GB10
# --trust-remote-code required for Nemotron architecture
# --max-model-len capped to conserve memory for other services
# --gpu-memory-utilization 0.45 of the shared 121 GiB unified pool (see budget
#   note above); leaves headroom for api + Qdrant + OS. Was 0.6 (OOM-wedged the
#   GB10 on 2026-07-09); lowered per the unified-memory budget.
CMD ["nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8", \
     "--kv-cache-dtype", "fp8", \
     "--trust-remote-code", \
     "--max-model-len", "4096", \
     "--gpu-memory-utilization", "0.45", \
     "--host", "0.0.0.0", \
     "--port", "8000"]
