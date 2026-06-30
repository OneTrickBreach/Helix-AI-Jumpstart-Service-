# Containerization — GB10 (arm64, CUDA 13)

> **Status:** Phase 0 baseline verified working. Multi-service stack (api, llm, vectordb) successfully running on the GB10 GPU.

_Last updated: **2026-06-30**_

---

## Environment observed (2026-06-26)

- **Docker version present:** `29.2.1` (build `a5c7197`).
- **Host:** GB10 (`helix-gb10-intern`), aarch64 / arm64, CUDA 13.

## GPU smoke test — **PASSED** ✅

**Date:** 2026-06-29  
**Command:**
```bash
docker run --rm --gpus all nvcr.io/nvidia/cuda:13.0.1-devel-ubuntu24.04 nvidia-smi
```

**Result (real output):**
```
Mon Jun 29 12:58:34 2026
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 580.159.03             Driver Version: 580.159.03      CUDA Version: 13.0     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|=========================================+========================+======================|
|   0  NVIDIA GB10                    On  |   0000000F:01:00.0 Off |                  N/A |
| N/A   40C    P8              3W /  N/A  | Not Supported          |      0%      Default |
+-----------------------------------------+------------------------+----------------------+
```

**Key facts confirmed:**
- GPU visible inside container: **NVIDIA GB10**
- Driver: **580.159.03**
- CUDA: **13.0**
- Persistence mode: On
- Image pulled successfully: arm64 variant confirmed working

---

## Phase 0 Multi-Service Status (2026-06-30)

All Phase 0 baseline containers are built and running healthy on the `helix-gb10-intern` host.

| Service | Image Basis | GPU Reserved? | Verified Port | Status / Smoke Test Result |
| :--- | :--- | :--- | :--- | :--- |
| **`api`** | `helix-ai-jumpstart:api-phase0` | Yes (`count: all`) | 8080 | **Healthy** · GPU check (nvidia-smi + CUDA 13) and `nomic-embed-text-v1.5` embeddings (768-dim) run successfully on-GPU |
| **`llm`** | `helix-ai-jumpstart:llm-phase0` | Yes (`count: all`) | 8000 | **Healthy** · `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8` served successfully via vLLM. Warmups and completion test pass on-GPU (31.48 GiB memory allocated) |
| **`vectordb`** | `qdrant/qdrant:latest` | No | 6333, 6334 | **Healthy** · Create, insert, and query vector tests pass |
| **`cuopt`** | Integrated in `api` service | Yes | (internal) | **Fell Back to OR-Tools (CPU)** · No binary wheel or arm64 package for cuopt-cu13 exists under the standard PyPI index for this platform version. Clean fallback to OR-Tools successfully solves the VRP smoke test on CPU |

### Fallback Detail (cuOpt ➔ OR-Tools)
As directed in §2, cuOpt arm64 checks were performed. The PIP packages for `cuopt-cu13` on arm64 do not support the target host environment directly. We fall back to **OR-Tools VRP Solver (CPU)** to proceed without blocking. The engine automatically reports `ortools` and solves correctly.

---

## Constraints

- **Architecture:** Images must be **arm64** — x86/amd64 images will **not** run on GB10.
- **NGC API key:** Developer NGC API key is now configured (`docker login nvcr.io` completed 2026-06-29). Production use will require an NVIDIA AI Enterprise (NVAIE) license key (per Ryan — to be addressed later).

---

## Open items for Ryan

1. ~~**Docker access:**~~ ✅ Resolved 2026-06-29 — `ishan` added to `docker` group.
2. ~~**NGC API key (dev):**~~ ✅ Resolved 2026-06-29 — developer key configured.
3. **NVAIE license key:** production/enterprise NGC pulls will need an NVIDIA AI Enterprise license key (Ryan noted this is a later concern).
4. **Product shape:** confirm whether the container is the **shippable product** (runs offline on the customer's GB10) or just a **dev convenience** — this drives how the Dockerfile and compose stack evolve.

