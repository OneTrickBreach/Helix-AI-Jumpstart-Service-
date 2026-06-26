# Containerization — GB10 (arm64, CUDA 13)

> **Status:** Container *scaffold* only. No application image is built yet — there
> is no application code (Points 3 & 4 not started). This document records the
> GPU-in-container verification attempt and the constraints that govern it.

_Last updated: **2026-06-26**_

---

## Environment observed (2026-06-26)

- **Docker version present:** `29.2.1` (build `a5c7197`).
- **Host:** GB10 (`helix-gb10-intern`), aarch64 / arm64, CUDA 13.

## GPU smoke test — **BLOCKED**

The GPU-in-container smoke test **could not be run**. This is **not a GPU failure** —
it is a host-access (permissions) block.

- **What happened:** `docker info` and the smoke-test `docker run` both failed with:
  ```
  permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
  ```
- **Why:** the user `ishan` is **not in the `docker` group** (`groups=ishan,users`) and
  is **not in sudoers** on this box. The Docker socket is `srw-rw---- root docker`, and
  the `docker` group currently has no members. So neither direct nor `sudo` access works.
- **Resolution required:** admin (Ryan) must grant docker-group access (see Open items).

### Intended test command (run once access is granted)

```bash
docker run --rm --gpus all nvcr.io/nvidia/cuda:13.0.1-devel-ubuntu24.04 nvidia-smi
```

Expected on success: `nvidia-smi` prints the GB10 Blackwell GPU and CUDA 13 driver
details from inside the container. **Record the real output here when it runs.**

---

## Pinned base image

- **Runtime (scaffold Dockerfile):** `nvcr.io/nvidia/cuda:13.0.1-runtime-ubuntu24.04`
- **Smoke test (devel, includes `nvidia-smi`/toolkit):** `nvcr.io/nvidia/cuda:13.0.1-devel-ubuntu24.04`

Both must be the **arm64 / aarch64** variants for GB10.

---

## Constraints

- **Architecture:** Images must be **arm64** — x86/amd64 images will **not** run on GB10.
- **NGC API key:** cuOpt and other NGC images require an **NGC API key**, which is
  **not yet configured**. Pulls of gated NGC content will fail until it is provided.
- **Scaffold, not a product:** the `Dockerfile` is a **placeholder** with no dependency
  installs. It will gain real deps only once the build scope is set at kickoff
  (Points 3 & 4). It is **not a shippable/built image** today.

---

## Open items for Ryan

1. **Docker access:** add `ishan` to the `docker` group (e.g. `sudo usermod -aG docker ishan`,
   then re-login) so the GPU smoke test can be run without sudo.
2. **NGC API key:** provide / confirm an NGC API key so cuOpt and other gated NGC
   images can be pulled and verified on arm64.
3. **Product shape:** confirm whether the container is the **shippable product**
   (runs offline on the customer's GB10) or just a **dev convenience** — this drives
   how the Dockerfile and compose stack evolve.
