# =============================================================================
# AI Jumpstart Service — LLM service (Phase 0)
# =============================================================================
# Serves NVIDIA Nemotron-3-Nano-30B-A3B FP8 via vLLM (OpenAI-compatible API).
# Target: arm64 / aarch64, CUDA 13, GB10.
#
# The vLLM image handles model download + serving. Model weights are cached
# in a volume mount to avoid re-downloading on container rebuild.
# =============================================================================

# PINNED (2026-08-03, Iteration 5 Phase 0). This was `vllm/vllm-openai:latest`,
# and it silently changed under us during Iteration 4 Phase 0: `make up` re-pulled
# it, swapped the LLM runtime to vLLM 0.26.0 mid-project, and moved the device
# memory envelope from ~65-68 GiB to ~75-76 GiB. Iteration 5 leans on the LLM
# harder than any previous iteration, so an unannounced runtime change is a
# bigger risk here.
#
# The digest below IS the runtime that is already running and verified on this
# box: the pulled v0.26.0 image carries build commit ffd46bfab212 —  identical to
# the base of the currently-running `helix-ai-jumpstart:llm-phase0`. So this pin
# records the verified state rather than changing it.
#   tag equivalent: vllm/vllm-openai:v0.26.0
# Pinned by digest, not tag, because a tag can be re-pushed.
FROM vllm/vllm-openai@sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52

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
