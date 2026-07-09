# Containerization — GB10 (arm64, CUDA 13)

> **Status:** Phase 6 four-service PoC stack. All images are arm64; the API and shared LLM
> declare GPU reservations. cuOpt/OR-Tools VRP capability is integrated in the `api` service
> (`/cuopt/*`), not a separate container. Last live startup attempt on 2026-07-09 was blocked
> by `nvidia-container-cli: nvml error: gpu requires reset`.

_Last updated: **2026-07-09**_

## Stack

| Service | Host port | GPU reserved | Role and current status |
|---|---:|---:|---|
| `web` | 8081 | No | React/Vite static UI through nginx; same-origin API proxy |
| `api` | 8080 | Yes | Secure FastAPI orchestration, embeddings, forecast, optimizers, suite, cuOpt/OR-Tools capability (`/cuopt/*`) |
| `llm` | 8000 | Yes | One shared `NVIDIA-Nemotron-3-Nano-30B-A3B-FP8` vLLM service |
| `vectordb` | 6333/6334 | No | Qdrant REST/gRPC and persisted local index |

`platform: linux/arm64` is explicit for every service. The two GPU reservations (`api`, `llm`)
share the single GB10 unified-memory device. Customer and generated data remain on-device.

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

Current run evidence and the stress-large single-node decision belong in
`benchmark/suite-summary.md` after a successful `make bench-all`. As of 2026-07-09, that real suite
run is still blocked by the GB10/NVML reset state; see `docs/DEVELOPMENT_JOURNAL.md`.
