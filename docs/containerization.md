# Containerization — GB10 (arm64, CUDA 13)

> **Status:** Phase 6 four-service PoC stack, **verified live on the GB10 (2026-07-10)**. All images
> are arm64; the API and shared LLM declare GPU reservations. cuOpt/OR-Tools VRP capability is
> integrated in the `api` service (`/cuopt/*`), not a separate container. `make up` →
> `make test` (49/49) → `make bench-all` (4 scenarios) → `make run` all pass on-device.
>
> The earlier `nvml error: gpu requires reset` wedge was a **unified-memory OOM**, not a driver
> fault: vLLM's `--gpu-memory-utilization` was set too high for the shared 121 GiB pool. Fixed by
> rebalancing it (0.6 → 0.45) after a host reboot; see the memory budget below.

_Last updated: **2026-07-10**_

## Stack

| Service | Host port | GPU reserved | Role and current status |
|---|---:|---:|---|
| `web` | 8081 | No | React/Vite static UI through nginx; same-origin API proxy |
| `api` | 8080 | Yes | Secure FastAPI orchestration, embeddings, forecast, optimizers, suite, cuOpt/OR-Tools capability (`/cuopt/*`) |
| `llm` | 8000 | Yes | One shared `NVIDIA-Nemotron-3-Nano-30B-A3B-FP8` vLLM service |
| `vectordb` | 6333/6334 | No | Qdrant REST/gRPC and persisted local index |

`platform: linux/arm64` is explicit for every service. The two GPU reservations (`api`, `llm`)
share the single GB10 unified-memory device. Customer and generated data remain on-device.

## Unified-memory budget (why the LLM fraction is capped)

The GB10's "GPU memory" and system RAM are the **same ~121 GiB unified pool**. vLLM's
`--gpu-memory-utilization` is therefore a fraction of the pool shared with the OS, the `api`
container (PyTorch + nomic-embed), Qdrant, and the suite's Polars frames — not a private GPU budget.
Set too high, the whole device OOMs and wedges into `nvidia-container-cli: gpu requires reset`
(observed 2026-07-09 at `0.6` while running the full 4-scenario suite alongside a redundant GPU
container).

Current setting: **`--gpu-memory-utilization 0.45`** (≈54 GiB) in [`docker/llm/Dockerfile`](../docker/llm/Dockerfile).
The Nemotron 30B A3B FP8 weights are ~30 GiB; 0.45 fits them plus KV cache and leaves ~67 GiB for
`api` + Qdrant + OS. Verified live: steady-state 62 GiB used / 59 GiB free; full suite peaked
67–68 GiB (≥52 GiB headroom). The wedge did not recur.

## One-command operation

```bash
make up
docker compose ps
make run SCENARIO=baseline
make bench-all
make test
```

`make bench-all` deterministically regenerates all four scenario datasets, runs the existing
`run_head_to_head` pipeline for baseline/classical/PPO, then runs the advisory Qdrant + shared-LLM
stage. It writes `benchmark/suite-summary.json` and `benchmark/suite-summary.md`.

Source changes are baked into the `api` image rather than bind-mounted. Rebuild after a
source edit:

```bash
docker compose build api
docker compose up -d --no-deps api
```

## cuOpt status

cuOpt was probed on the live GB10. No compatible `cuopt-cu13` binary wheel/arm64 package was
available for this environment, so the working solver is **OR-Tools on CPU**. The fallback is
reported by the `api` service at `/cuopt/health`; it is not relabeled as GPU cuOpt. The optimized
transportation path uses a real OR-Tools capacitated LP, solved in-process inside `api`.

A separate `cuopt` GPU container was intentionally NOT added: it would only re-serve the probe the
`api` already exposes and reserve the scarce GPU for a solver that runs in-process. If a compatible
arm64 cuOpt build later lands, the `/cuopt/*` capability can be split into its own GPU service then.

## Measurement caveats

- `peak_process_rss_mb` is the API process high-water RSS only. It excludes the LLM and Qdrant.
  In the Phase 6 suite it also **saturates** after the first scenario — the suite runs all scenarios
  in one process and `ru_maxrss` is a process-lifetime high-water mark, so it is monotonic and not a
  per-scenario figure. Use the device-level column for per-scenario memory.
- `allocation_rate_gbps_proxy` is `abs(end RSS - start RSS) / latency`. It is a coarse process
  allocation-rate proxy, **not measured DRAM bandwidth**.
- The Phase 6 suite samples `/proc/meminfo` (`MemTotal - MemAvailable`) during each complete
  scenario. On this GB10 the container observes the host unified CPU/GPU pool; this is the
  device-level memory figure used against the **~121 GiB usable** flag envelope (128 GB nominal).
- The in-container `nvidia-smi` utilization/memory query returns N/A on this unified-memory stack.
  Outputs therefore retain `gpu_utilization_percent: null` with the reason instead of inventing a
  number.
- The known ~273 GB/s platform bandwidth limit is a hardware fact, not a direct suite
  measurement. The bandwidth narrative correlates the LLM's measured token rate and memory with
  that limiter and contrasts it with the small optimizer/PPO footprint.

## Verified platform baseline

- NVIDIA GB10, aarch64/arm64
- Driver 580.159.03
- CUDA runtime 13.0; toolkit 13.0.88
- Docker 29.2.1 with Compose v2
- GPU visibility previously verified from the arm64 CUDA 13 container

Current run evidence and the stress-large single-node decision live in `benchmark/suite-summary.md`
(regenerate with `make bench-all`; the file itself is gitignored). As of the 2026-07-10 live run:
all four scenarios peak 67–68 GiB of the ~121 GiB usable pool (≥52 GiB headroom), the 90% envelope
flag is clear, and **stress-large stays single-node** (no 2-node path needed). PPO lost in all four
scenarios. See `docs/DEVELOPMENT_JOURNAL.md` for the full table.
