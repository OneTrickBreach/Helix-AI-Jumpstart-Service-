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

# Health check against the vLLM /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=600s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

# Launch vLLM server
# The base image ENTRYPOINT is ["vllm", "serve"] — CMD provides the model + flags
# --kv-cache-dtype fp8 for memory efficiency on the GB10
# --trust-remote-code required for Nemotron architecture
# --max-model-len capped to conserve memory for other services
# --gpu-memory-utilization set conservatively since GPU is shared with api+cuopt
CMD ["nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8", \
     "--kv-cache-dtype", "fp8", \
     "--trust-remote-code", \
     "--max-model-len", "4096", \
     "--gpu-memory-utilization", "0.6", \
     "--host", "0.0.0.0", \
     "--port", "8000"]
