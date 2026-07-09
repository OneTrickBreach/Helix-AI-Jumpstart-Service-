# Phase 6 prototype handoff

## Run the demo

```bash
make up
docker compose ps
make run SCENARIO=baseline
make bench-all
make test
```

Open `http://localhost:8081` for the planner UI. Choose a scenario and run it. The **Before**
column is the reorder-point/shortest-route baseline; **After** is the approach selected by the
measured objective with latency used only to break an objective tie. Signed deltas are computed
from those returned values. The rationale is **ADVISORY ONLY** and cannot change numeric plans or
metrics.

The complete handoff artifact is `benchmark/suite-summary.md`; its JSON companion is intended for
automation. Each scenario contains baseline, tuned-classical, and PPO rows even when PPO loses.
As of 2026-07-09, regenerate this artifact after clearing the GB10/NVML reset condition; stale
benchmark files are not Phase 6 evidence.

## Read the on-device panel honestly

- **API process peak RSS** is one process, not whole-device memory.
- **Allocation-rate proxy** is a start/end RSS delta divided by latency. It is not DRAM bandwidth.
- **Device peak memory** in the Phase 6 suite is sampled system-wide unified-memory use from
  `/proc/meminfo` during optimization plus RAG/LLM. Compare it with ~121 GiB usable, not the
  nominal 128 GB label.
- **GPU utilization** is unavailable when the GB10 in-container `nvidia-smi` query returns N/A.
  Null is the correct value.
- The ~273 GB/s figure is the known hardware bandwidth limit. The shared FP8 MoE LLM is the
  bandwidth-sensitive component; its tokens/s and memory are measured, while the suite does not
  pretend its allocation proxy is a direct bandwidth counter.

## Operational posture

cuOpt is unavailable for the present arm64/CUDA package combination, so OR-Tools CPU is the
declared fallback. Qdrant is active; LanceDB remains an unimplemented fallback because the current
index has not caused memory pressure. Only one Nemotron service is loaded. All data stays on the
device.

The two-node 256 GB route is conditional. It is not implemented unless the real `stress-large`
run reaches the single-node usable-memory limit. The current decision must come from the generated
summary after `make bench-all`; do not infer it while the GPU startup blocker remains unresolved.

This is a development PoC. Production licensing, multi-tenant isolation, HA, deployment
automation, fine-tuning, and larger-than-prototype scaling are intentionally out of scope.
