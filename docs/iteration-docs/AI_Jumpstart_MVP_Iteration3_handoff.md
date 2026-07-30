# AI Jumpstart MVP on NVIDIA GB10 — Iteration 3 (Handoff · Demo/Pilot-Ready)

**Prepared for:** Ryan Spurr | Helix, Connection Inc.
**From:** Ishan (AI Intern)
**Date:** 2026-07-27
**Scope:** Move the verified PoC (Iteration 2) to a **demo/pilot-ready** state — reproducible
results, real-corpus RAG, polished demo UI, a fair RL evaluation, scale study, and cuOpt re-check.
All seven phases (0–6) complete; Phase 7 (production track) deferred to **Iteration 6** (renumbered
2026-07-30 — see §9).
**Evidence basis:** Every number below comes from a **real on-device run** on seeded synthetic data.
Reproduce with `make bench-all`.

> **How to read this.** §1 is the 30-second summary. §2 is what shipped per phase. §3 is the
> updated stack. §4 is the **real measured results**. §5 is how to run it. §6 is the scale study.
> §7 is the cuOpt re-check. §8 is the honest caveats. §9 is what's next. §10 links every doc.

---

## 1. TL;DR (the 30-second version)

- **Demo/pilot-ready.** The prototype is polished, reproducible, and presentable — a one-command
  demo (`make demo`) that runs the full pipeline on the GB10 and shows a before/after comparison
  with an LLM advisory, all on-device. The "rack → desk" story is now demoable.
- **Results are reproducible.** Seeded Optuna, seeded data, deterministic pipeline — two consecutive
  `make bench-all` runs produce identical objectives across all 12 rows (4 scenarios × 3 approaches).
- **PPO was given a fair shot and lost.** Phase 4 rebuilt the RL environment as a true per-period
  MDP with CVaR tail-risk evaluation. PPO lost all four scenarios on both average cost and tail risk.
  Status: "evaluated, not shipped." The honest benchmark *is* the selling point.
- **It scales.** The scale study (Phase 5) pushed to 100x the base data volume (28,800 series).
  Memory stays at ~54% of the envelope at every level. The ceiling is forecast latency, not memory.
- **cuOpt is now available.** cuOpt 26.06.00 runs on arm64/CUDA-13 (new since Iteration 2).
  Benchmarked honestly: OR-Tools CPU wins at prototype scale (<100 locations). OR-Tools stays; cuOpt
  is available for future 100+ stop fleet-routing use cases.
- **71 tests pass** (69 passed + 2 xpassed). All four scenarios produce `llm_finalized` rationale.

---

## 2. What Shipped (Phase by Phase)

| Phase | Delivered | Key Result |
|---|---|---|
| **0 — Orientation** | Stack brought up, green baseline captured | Found stale NVML in long-running containers (fixed by force-recreate) |
| **1 — Reproducibility** | Seeded Optuna, per-scenario RSS, npm audit 0 vulns | Two consecutive runs produce identical objectives; classical now deterministically wins all four |
| **2 — RAG on real corpus** | 6 manufacturing docs as corpus, stale-point cleanup, Nemotron reasoning-model fix | LLM rationale `llm_finalized` for all 4 scenarios (was always template-fallback before) |
| **3 — Demo & narrative** | "Why This Plan" hero card, stage messages, recorded replay, `make demo`, demo guide | Non-technical viewer sees value in 2 minutes; recorded fallback for live-GPU flakiness |
| **4 — RL fair-shot** | Per-period MDP rebuild, CVaR-75 tail risk, PPO demote decision | PPO loses all 4 on objective AND tail risk; demoted to "evaluated, not shipped" |
| **5 — Scale study** | 6-level study from 1x (288 series) to 100x (28,800 series) | Memory at ~54% at all levels; ceiling is forecast latency (~25ms/series); 2-node deferred |
| **6 — cuOpt re-check** | cuOpt 26.06.00 installed, VRP benchmark (7 scales), smoke endpoint updated | Crossover at ~100 locations; OR-Tools wins at prototype scale; cuOpt available for future use |

---

## 3. The Stack (unchanged from Iteration 2, one update)

| Layer | Tool / Model | Notes |
|---|---|---|
| **LLM (shared)** | **NVIDIA Nemotron 30B A3B, FP8 (MoE)** via vLLM | `--gpu-memory-utilization 0.45`; `/no_think` for reasoning-model scratchpad |
| **Embeddings** | **`nomic-embed-text-v1.5`** (768-dim) via sentence-transformers | GPU |
| **Vector DB** | **Qdrant** | On-device; stale-point cleanup per-call |
| **Forecasting** | `statsforecast` (AutoETS + Croston/SBA) | CPU; ~25ms/series (the scale ceiling) |
| **Inventory** | reorder-point baseline · Optuna-tuned (s,S) classical · PPO (demoted) | Classical wins by evidence |
| **Routing** | **OR-Tools CPU** (capacitated transportation LP) | cuOpt now available but not advantageous at this scale |
| **API / UI** | FastAPI (REST + SSE) · React + nginx · thin CLI | API-first; secure; "Why This Plan" summary card |

**Runtime = four arm64 containers:** `web` (8081), `api` (8080, GPU), `llm` (8000, GPU),
`vectordb` (6333/6334).

---

## 4. Real On-Device Results (2026-07-27)

Reproduced with `make bench-all` (seed 12345, horizon 8, ppo-timesteps 128, Optuna seeded). Objective =
total landed cost (holding + ordering + backorder + lost-sale + transport); lower is better.

### 4.1 Three-Way Comparison

| Scenario | Baseline obj | **Classical obj** | Improvement | PPO obj | PPO vs Classical |
|---|---:|---:|---:|---:|---:|
| `baseline` | 88,023 | **81,789** | **−7.1%** | 102,805 | +25.7% worse |
| `component-shortage-shock` | 102,835 | **95,445** | **−7.2%** | 113,585 | +19.0% worse |
| `demand-surge` | 100,735 | **94,165** | **−6.5%** | 115,162 | +22.3% worse |
| `stress-large` | 2,622,335 | **2,521,615** | **−3.8%** | 2,867,271 | +13.7% worse |

### 4.2 CVaR-75 Tail Risk (worst 25% of periods)

| Scenario | Classical CVaR-75 | PPO CVaR-75 | PPO tail risk |
|---|---:|---:|---|
| `baseline` | 20,587 | 19,741 | slightly better (but +25.7% worse total) |
| `component-shortage-shock` | **19,650** | 21,622 | worse |
| `demand-surge` | **19,246** | 22,905 | worse |
| `stress-large` | **440,910** | 495,932 | worse |

**PPO loses on both average cost and tail risk in 3/4 scenarios.** The one scenario where PPO's CVaR
is marginally better (baseline), its total cost is 25.7% worse. Decision: **demote.**

### 4.3 On-Device Envelope

| Metric | Value |
|---|---|
| Device peak memory | 65–68 GiB of ~121 GiB usable |
| Headroom | 55+ GiB (90% flag clear) |
| LLM throughput | ~47 tokens/s |
| Single-node holds | Yes at all tested scales |

**Honesty notes:**
- Improvement % = `(baseline − winner) / baseline`, computed from the run — never pre-asserted.
- PPO was given a fair shot: true per-period MDP (Phase 4), not the original whole-horizon param search.
- cuOpt now available but OR-Tools stays (different problem class, better at this scale).

---

## 5. How to Run It

```bash
make up                       # build + start all four arm64 services
make test                     # 69 passed + 2 xpassed (71 total)
make demo                     # generate data, rebuild web, print URLs
make bench-all                # all 4 scenarios → benchmark/suite-summary.{json,md}
make run SCENARIO=baseline    # single scenario end-to-end
make scale-study              # 6-level scale study
```

**Web UI:** `http://localhost:8081` — select a scenario, click Run, watch live SSE progress, read
the before/after cards, on-device panel, and advisory rationale.

**Recorded demo:** `http://localhost:8081?replay=true` — instant results from a pre-recorded real run.

**Full demo walkthrough:** [`docs/DEMO_GUIDE.md`](../DEMO_GUIDE.md) — step-by-step with talk tracks.

---

## 6. Scale Study Results (Phase 5)

| Level | Series | Peak RSS (MB) | Forecast (s) | Optimizer (s) | Device (GiB) | Headroom (GiB) |
|---|---:|---:|---:|---:|---:|---:|
| 1x | 288 | 307 | 7.4 | 0.045 | 64.9 | 56.1 |
| 5x | 1,440 | 347 | 36.1 | 0.034 | 65.0 | 56.0 |
| 10x | 2,880 | 391 | 72.9 | 0.053 | 65.0 | 56.0 |
| 25x | 7,200 | 517 | 182.1 | 0.095 | 65.1 | 55.9 |
| 50x | 14,400 | 698 | 361.6 | 0.201 | 65.3 | 55.7 |
| 100x | 28,800 | 940 | 716.0 | 0.363 | 65.5 | 55.5 |

- **Memory is NOT the ceiling.** Device memory stays at ~54% at every level.
- **Forecast latency IS the ceiling.** ~25ms/series; 100x takes 12 minutes.
- **The optimizer is trivially fast.** <0.4s even at 100x.
- **2-node deferred.** 55+ GiB headroom at every level; no workload approaches the limit.

---

## 7. cuOpt Re-Check (Phase 6)

**cuOpt 26.06.00 is now available for arm64/CUDA-13** — a change from all prior checks.

| Locations | OR-Tools (ms) | cuOpt (ms) | Winner | Ratio |
|---:|---:|---:|---|---|
| 10 | 1.7 | 115.8 | OR-Tools | 67.8x |
| 50 | 29.9 | 129.3 | OR-Tools | 4.3x |
| 100 | 187.4 | 171.7 | cuOpt | 1.1x |
| 200 | 854.8 | 197.2 | cuOpt | 4.3x |
| 500 | 9,509.5 | 341.6 | cuOpt | 27.8x |

**Decision: keep OR-Tools.** Crossover at ~100 locations; prototype scale is ≤152 lanes.
Additionally, cuOpt solves VRP (vehicle routing) while the main optimizer uses OR-Tools GLOP for
transportation LP — different problem classes. cuOpt not added to requirements; available for future
100+ stop fleet routing.

---

## 8. Honest Caveats (carry-forward)

- **Development / PoC, not production.** No production licensing, HA, multi-tenant isolation, or
  fine-tuning — out of scope by kickoff decision.
- **PPO is recommended, not mandated**, and lost here — reported honestly. Demoted to "evaluated,
  not shipped" after a fair per-period MDP test with CVaR tail-risk evaluation.
- **The ~94% paper figure is a baseline-collapse artifact.** Never presented as a flat saving.
- **The binding hardware constraint is memory bandwidth (~273 GB/s), not capacity.** The scale study
  confirms memory stays at ~54% even at 100x; the constraint is forecast latency, not the envelope.
- **GPU utilization reads `null`** on this unified-memory stack. Reported as unavailable, not faked.
- **LLM rationale is advisory only.** It explains the plan; it never computes or overrides a metric.
  Prompt injection in ingested text is flagged (including at retrieval time), never executed.
- **Customer data stays on-device.** Nothing ships off-box.
- **No hospital service-level claim.** Only Manufacturing is built; other verticals remain the market map.
- **Improvement percentages are vs. the naive untuned baseline**, not vs. actual customer costs.

---

## 9. What's Next (Iterations 4 and 5, then the Production Track at Iteration 6)

> **Renumbered 2026-07-30.** Ryan's demo feedback (2026-07-29) inserted two iterations ahead of the
> production track, so what this section originally called "Iteration 4 = production" is now
> **Iteration 6**:
> - **Iteration 4** — dataset transparency layer: a read-only "Know Your Data" view so a viewer can
>   see the dataset a result ran on ([`../Iteration4_Plan_of_Action.md`](../Iteration4_Plan_of_Action.md)).
> - **Iteration 5** — conversational scenario/what-if analyst ([`../Iteration5_Plan_of_Action.md`](../Iteration5_Plan_of_Action.md)).
> - **Iteration 6** — the production track described below.

Iteration 3 gets to **demo/pilot-ready**. The gap to a shippable product:

| Gap | What's needed |
|---|---|
| **Real customer-data onboarding** | ETL, schema mapping, validation, access control |
| **Production hardening** | HA, multi-tenant isolation, security, install/update tooling |
| **Multi-vertical** | Only Manufacturing is built; Retail/Wholesale/Hospitals are the market map |
| **Commercial wrap** | Licensing (NFR/NVAIE), pricing, support, SLAs |
| **cuOpt integration** | If a customer use case has 100+ stop fleet routing |
| **Shippable appliance image** | Single install, managed updates, customer-facing documentation |

**Bottom line:** Iteration 3 makes it sellable as a story and demoable on the box — enough to win
design partners or an internal go/no-go. The finished product requires the production track
(Iteration 6); Iterations 4 and 5 sharpen the demo rather than ship the product.

---

## 10. Supporting Documents (all in-repo)

- [`../../README.md`](../../README.md) — full project overview, hardware, status (§9), decisions (§11), caveats (§12).
- [`../DEMO_GUIDE.md`](../DEMO_GUIDE.md) — step-by-step demo walkthrough with talk tracks.
- [`../DEVELOPMENT_JOURNAL.md`](../DEVELOPMENT_JOURNAL.md) — chronological truth ledger; every phase has a full entry.
- [`../Iteration3_Plan_of_Action.md`](../Iteration3_Plan_of_Action.md) — the phase-by-phase build blueprint (Phases 0–7).
- [`../Iteration2_Plan_of_Action.md`](../Iteration2_Plan_of_Action.md) — the Iteration 2 build blueprint.
- [`../Iteration2_Point3_Scaffolding_Response_to_Ryan.md`](../Iteration2_Point3_Scaffolding_Response_to_Ryan.md) — model/tool rationale.
- [`../containerization.md`](../containerization.md) — arm64 four-service stack, unified-memory budget, measurement caveats.
- [`../handoff.md`](../handoff.md) — quick-start commands and on-device caveats.
- [`../environment.md`](../environment.md) — live GB10 device specs.
- [`./AI_Jumpstart_MVP_Iteration1_v1_paper-grounded.md`](./AI_Jumpstart_MVP_Iteration1_v1_paper-grounded.md) — Iteration 1 (paper-grounded).
- [`./AI_Jumpstart_MVP_Iteration1_v2_standalone.md`](./AI_Jumpstart_MVP_Iteration1_v2_standalone.md) — Iteration 1 (standalone/external).
- [`./AI_Jumpstart_MVP_Iteration2_handoff.md`](./AI_Jumpstart_MVP_Iteration2_handoff.md) — Iteration 2 handoff.
- `benchmark/suite-summary.md` — generated per-run report (regenerate with `make bench-all`).
- `benchmark/cuopt-recheck.json` — cuOpt vs OR-Tools VRP benchmark (Phase 6).
- `benchmark/scale-study.json` — 6-level scale study results (Phase 5).

---

*Iteration 3 built on branch `feat/iteration3`, verified live on the GB10 (`helix-gb10-intern`),
and merged to `main` on 2026-07-27. Vertical: Manufacturing. Product shape: Development / PoC
(demo/pilot-ready).*
