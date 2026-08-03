# Helix AI Jumpstart — Handoff Reference

> **Status:** Iteration 3 complete (2026-07-27). Demo/pilot-ready. All phases (0–6) verified on-device.
> `make test` → **69 passed + 2 xpassed** (71 total). Tuned classical wins all four scenarios.

_Last updated: **2026-07-27** (Iteration 3 finalization)_

## Quick start

```bash
make up                       # build + start all four arm64 services (GPU on api/llm)
make test                     # full regression suite (71 tests on-device)
make demo                     # generate data, rebuild web, print URLs
make bench-all                # all four scenarios → benchmark/suite-summary.{json,md}
make run SCENARIO=baseline    # single scenario end-to-end plan + metrics
```

Open **`http://localhost:8081`** for the planner UI. Pick a scenario and run it. The **Before**
column is the reorder-point/shortest-route baseline; **After** is the approach selected by the
measured objective. Signed deltas are computed from those returned values. The rationale is
**ADVISORY ONLY** and cannot change numeric plans or metrics.

For a pre-recorded real run (no GPU needed): **`http://localhost:8081?replay=true`**

For the full demo walkthrough with talk tracks: [`docs/DEMO_GUIDE.md`](DEMO_GUIDE.md).

## Current results (2026-07-27, seed 12345)

| Scenario | Baseline obj | Classical obj | Improvement | PPO | Winner |
|---|---:|---:|---:|---|---|
| `baseline` | 88,023 | **81,789** | **−7.1%** | lost (102,805) | classical |
| `component-shortage-shock` | 102,835 | **95,445** | **−7.2%** | lost (113,585) | classical |
| `demand-surge` | 100,735 | **94,165** | **−6.5%** | lost (115,162) | classical |
| `stress-large` | 2,622,335 | **2,521,615** | **−3.8%** | lost (2,867,271) | classical |

**PPO** was given a fair shot (Phase 4: per-period MDP, CVaR-75 tail-risk eval) and **lost all four
on both objective and tail risk**. Status: "evaluated, not shipped." Kept visible in the benchmark
for transparency.

## On-device envelope

| Metric | Value |
|---|---|
| Device peak memory | 65–68 GiB of ~121 GiB usable (55+ GiB headroom) |
| 90% envelope flag | Clear at all tested scales (up to 100x / 28,800 series) |
| LLM throughput | ~47 tokens/s (Nemotron 30B FP8) |
| Scale ceiling | Forecast latency (~25ms/series), not memory |
| Single-node holds | Yes — 2-node path deferred, not needed |

## Read the on-device panel honestly

- **API process peak RSS** is one process, not whole-device memory.
- **Allocation-rate proxy** is a start/end RSS delta divided by latency. It is not DRAM bandwidth.
- **Device peak memory** is sampled system-wide unified-memory use from `/proc/meminfo`. Compare
  with ~121 GiB usable, not the nominal 128 GB label.
- **GPU utilization** is unavailable when the GB10 in-container `nvidia-smi` query returns N/A.
  Null is the correct value.
- The ~273 GB/s figure is the known hardware bandwidth limit. The shared FP8 MoE LLM is the
  bandwidth-sensitive component; the suite does not pretend its allocation proxy is a direct
  bandwidth counter.

## Solver status

- **Main optimizer:** OR-Tools GLOP (capacitated transportation LP in `select_ortools_lanes`).
- **cuOpt 26.06.00:** now available for arm64/CUDA-13 (verified 2026-07-27). Solves VRP, not LP —
  different problem class. VRP crossover at ~100 locations; OR-Tools wins at prototype scale (≤152
  lanes). cuOpt not added to requirements — remains optional for future 100+ stop fleet routing.
- **Smoke endpoint:** `/cuopt/health` and `/cuopt/solve` use cuOpt if installed, OR-Tools fallback
  otherwise. Updated for cuOpt 26.x API.

## Operational posture

This is a **development PoC** (confirmed at kickoff). Production licensing, multi-tenant isolation,
HA, deployment automation, fine-tuning, and larger-than-prototype scaling are intentionally out of
scope (see Phase 7 / Iteration 6 — the production track, renumbered 2026-07-30 when Iterations 4
(dataset transparency) and 5 (conversational what-if) were inserted ahead of it).

All data stays on the device. The LLM rationale is advisory only — it explains the plan; it never
computes or overrides a metric. Prompt injection in ingested text is flagged (including at retrieval
time), never executed.

## Key documents

- [`DEMO_GUIDE.md`](DEMO_GUIDE.md) — full demo walkthrough with talk tracks
- [`DEVELOPMENT_JOURNAL.md`](DEVELOPMENT_JOURNAL.md) — chronological truth ledger
- [`iteration-docs/AI_Jumpstart_MVP_Iteration3_handoff.md`](iteration-docs/AI_Jumpstart_MVP_Iteration3_handoff.md) — Iteration 3 handoff
- [`Iteration3_Plan_of_Action.md`](Iteration3_Plan_of_Action.md) — the phase-by-phase build blueprint
- [`containerization.md`](containerization.md) — arm64 four-service stack details
- [`environment.md`](environment.md) — live GB10 device specs
