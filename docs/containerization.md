# Containerization — GB10 (arm64, CUDA 13)

> **Status:** Container *scaffold* only. No application image is built yet — there
> is no application code (Points 3 & 4 not started). This document records the
> GPU-in-container verification attempt and the constraints that govern it.

_Last updated: **2026-06-29**_

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

### Resolution history
- 2026-06-26: BLOCKED — `ishan` not in `docker` group, not in sudoers.
- 2026-06-29: Ryan ran `sudo usermod -aG docker ishan`. Smoke test now passes.

---

## Pinned base image

- **Runtime (scaffold Dockerfile):** `nvcr.io/nvidia/cuda:13.0.1-runtime-ubuntu24.04`
- **Smoke test (devel, includes `nvidia-smi`/toolkit):** `nvcr.io/nvidia/cuda:13.0.1-devel-ubuntu24.04`

Both must be the **arm64 / aarch64** variants for GB10.

---

## Constraints

- **Architecture:** Images must be **arm64** — x86/amd64 images will **not** run on GB10.
- **NGC API key:** Developer NGC API key is now configured (`docker login nvcr.io`
  completed 2026-06-29). Production use will require an NVIDIA AI Enterprise (NVAIE)
  license key (per Ryan — to be addressed later).
- **Scaffold, not a product:** the `Dockerfile` is a **placeholder** with no dependency
  installs. It will gain real deps only once the build scope is set at kickoff
  (Points 3 & 4). It is **not a shippable/built image** today.

---

## Open items for Ryan

1. ~~**Docker access:**~~ ✅ Resolved 2026-06-29 — `ishan` added to `docker` group.
2. ~~**NGC API key (dev):**~~ ✅ Resolved 2026-06-29 — developer key configured.
3. **NVAIE license key:** production/enterprise NGC pulls will need an NVIDIA AI
   Enterprise license key (Ryan noted this is a later concern).
4. **Product shape:** confirm whether the container is the **shippable product**
   (runs offline on the customer's GB10) or just a **dev convenience** — this drives
   how the Dockerfile and compose stack evolve.
