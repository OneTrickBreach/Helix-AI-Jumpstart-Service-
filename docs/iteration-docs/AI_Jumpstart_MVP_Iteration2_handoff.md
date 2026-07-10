# AI Jumpstart MVP on NVIDIA GB10 — Iteration 2 (Handoff · On-Device Prototype)

**Prepared for:** Ryan Spurr | Helix, Connection Inc.
**From:** Ishan (AI Intern)
**Date:** 2026-07-10
**Scope:** Pic 4, Points 3 & 4 (SCO scaffolding + full synthetic dataset) — **built, containerized, and
verified end-to-end on the GB10.** Where Iteration 1 was the *proposal* (use cases, data elements,
tool rationale), Iteration 2 is the *working prototype*.
**Evidence basis:** Every number below comes from a **real on-device run** on seeded synthetic data.
No brochure figures, no hard-coded percentages. Reproduce with `make bench-all`.

> **How to read this.** §1 is the 30-second summary. §2 is what shipped. §3 is the stack. §4 is the
> **real measured results** (the before/after and the honest PPO outcome). §5 is how to run it.
> §6 is the honest caveats. §7 is what's next. §8 links every supporting doc.

---

## 1. TL;DR (the 30-second version)

- **It runs at the desk.** A four-service, API-first supply-chain-optimization prototype runs
  **entirely on one GB10** (arm64, 121 GiB unified memory) — seeded synthetic Manufacturing data →
  ingest → forecast → optimize (baseline vs. tuned-classical vs. PPO) → advisory RAG rationale →
  a planner web UI with an honest before/after view.
- **The numbers are real and honest.** Across four scenarios, **tuned classical wins three** and the
  **naive baseline wins the shock scenario** (the tuned solver couldn't beat it — reported as-is).
  **PPO lost in all four** — kept visible, not hidden. Every metric is computed from an on-device run.
- **It fits the box with room to spare.** Peak device memory was **67–68 GiB of ~121 GiB usable**
  (≥52 GiB headroom) in every scenario, including the largest. **Single node holds; no 2-node cluster
  needed** at prototype scale.
- **Everything is containerized, arm64, `docker compose` v2.** One shared Nemotron 30B FP8 LLM,
  `nomic-embed` embeddings, Qdrant vector store — the Ryan-proven stack. Secure API-first; the web UI
  and CLI are thin clients of the same endpoints.
- **Status:** Phases 0–6 complete; `make up` → `make test` (49/49) → `make bench-all` → `make run`
  all pass on-device. This is a **Development / PoC**, not production (as confirmed at kickoff).

---

## 2. What Shipped (Iteration 1 proposal → Iteration 2 build)

| Phase | Delivered | Verified |
|---|---|---|
| **0 — Environment & containers** | arm64 CUDA-13 stack; GPU-in-container; Nemotron LLM served; `nomic-embed` embeddings; Qdrant; cuOpt arm64 checked → **OR-Tools CPU fallback** | GPU visible in container; smoke tests pass |
| **1 — Seeded synthetic data** | Manufacturing generator: supplier→plant/line→DC→customer, **BOM / multi-tier components**, lumpy correlated demand, capacity limits, per-lane lead times/cost, cost params, service targets. 4 scenarios incl. worst-case shocks. Deterministic by seed | Byte-identical regeneration; schema documented |
| **2 — Secure API + baseline** | **API-first** FastAPI (API-key auth, validation); GPU ingestion; `statsforecast` forecasting; reorder-point + shortest-route baseline; resource profiler | `make run` emits a plan + metrics + resource profile |
| **3 — Strong classical + learned** | Optuna-tuned (s,S); OR-Tools routing LP; multi-echelon Gym env + **PPO** (Stable-Baselines3); head-to-head harness picks the winner **by evidence** | `make bench` emits the 3-way comparison |
| **4 — RAG advisory** | Scenario/plan corpus embedded into Qdrant; **shared Nemotron** rationale; retrieval-cited; **labeled ADVISORY ONLY**; prompt-injection flagging (incl. retrieval-time) | `/rag/rationale` returns a grounded, cited rationale |
| **5 — Front-ends** | React/Vite/Tailwind web **Scenario Comparison** UI + thin CLI, both over the same secure API; **truthful SSE** progress; nginx injects the API key server-side (never in the browser) | Live before/after in the browser; key absent from bundle |
| **6 — Benchmark, harden, hand off** | All-scenario suite (`make bench-all`) with device-level memory sampling + honest envelope flag; this handoff | **Live run 2026-07-10** (see §4) |

---

## 3. The Stack (confirmed at kickoff, built as agreed)

| Layer | Tool / model | Notes |
|---|---|---|
| **LLM (shared)** | **NVIDIA Nemotron 30B A3B, FP8 (MoE)** via vLLM | One model, reused for all language tasks; `--gpu-memory-utilization 0.45` of the shared pool |
| **Embeddings** | **`nomic-embed-text-v1.5`** (768-dim) via sentence-transformers | GPU |
| **Vector DB** | **Qdrant** (LanceDB fallback unused — no memory pressure) | On-device |
| **Forecasting** | `statsforecast` (AutoETS + Croston/SBA for lumpy demand) | CPU |
| **Inventory** | reorder-point baseline · Optuna-tuned (s,S) classical · PPO learned | benchmark decides |
| **Routing** | **OR-Tools CPU** (capacitated transportation LP) | cuOpt had no arm64/CUDA-13 build; honest fallback, served at `api:/cuopt/*` |
| **API / UI** | FastAPI (REST + SSE) · React + nginx · thin CLI | API-first; secure; single logic path |

**Runtime = four arm64 containers:** `web` (8081), `api` (8080, GPU), `llm` (8000, GPU),
`vectordb` (6333/6334). GPU is reserved only on `api` and `llm`, which share the single GB10.

---

## 4. Real On-Device Results (2026-07-10)

Reproduced with `make bench-all` (seed 12345, horizon 8, ppo-timesteps 128, top-k 5). Objective =
total landed cost (holding + ordering + backorder + lost-sale + transport); lower is better.

### 4.1 Before (naive baseline) → After (best by evidence)

| Scenario | Baseline obj | **Winner** | Winner obj | Improvement | PPO obj | PPO outcome |
|---|---:|---|---:|---:|---:|---|
| `baseline` | 88 022.76 | tuned classical | **80 519.15** | **−8.5%** | 102 804.72 | lost |
| `component-shortage-shock` | 102 834.79 | **naive baseline** | 102 834.79 | **0.0%** (tuned couldn't beat it) | 113 584.86 | lost |
| `demand-surge` | 100 735.04 | tuned classical | **95 913.47** | **−4.8%** | 115 161.75 | lost |
| `stress-large` | 2 622 323.05 | tuned classical | **2 495 179.74** | **−4.8%** | 2 867 262.51 | lost |

**Honesty notes (these are the point):**
- **PPO lost in all four scenarios.** It was also the slowest (e.g. 21.9 s on `stress-large` vs 0.27 s
  for tuned classical) and the heaviest. Per the SOP, the learned policy had to *earn* its place
  against a well-tuned classical solver — here it did not. Tuned classical is the shipped default.
- **`component-shortage-shock` shows no improvement**, and the UI/handoff say so plainly. Under a
  zero-supply shock, lost sales are gated by *supply*, not by inventory policy, so a tuned (s,S)
  converges to the baseline. This is exactly the kind of result we refuse to dress up.
- Improvement % = `(baseline − winner) / baseline`, computed from the run — never pre-asserted.

### 4.2 On-device envelope (the "runs at the desk" story, measured)

| Scenario | Device peak memory | Headroom vs ~121 GiB | 90% flag | LLM tokens/s |
|---|---:|---:|---|---:|
| `baseline` | 67.43 GiB | 53.57 GiB | clear | 47.1 |
| `component-shortage-shock` | 67.42 GiB | 53.58 GiB | clear | 46.9 |
| `demand-surge` | 67.32 GiB | 53.68 GiB | clear | 46.7 |
| `stress-large` | 68.10 GiB | 52.90 GiB | clear | 46.6 |

- **Single node holds** with ≥52 GiB headroom everywhere. The **2-node 256 GB path is not needed**
  at prototype scale (it remains the documented escalation route, unimplemented).
- Device memory is sampled system-wide from `/proc/meminfo` (the container observes the host unified
  pool). The dominant consumer is the shared FP8 LLM; the optimizer/PPO footprints are tiny.

---

## 5. How to Run It (one command per step)

```bash
make up                       # build + start all four arm64 services (GPU on api/llm)
make test                     # full regression suite (49/49 on-device)
make bench-all                # all four scenarios → benchmark/suite-summary.{json,md}
make run SCENARIO=baseline    # single scenario end-to-end plan + metrics
```

Then open **`http://localhost:8081`** for the planner UI: pick a scenario, Run, watch live SSE
progress, and read the before/after cards, the on-device panel, and the ADVISORY-ONLY rationale.
`make cli SCENARIO=...` does the same through the CLI over the same API.

---

## 6. Honest Caveats (carry-forward + Iteration-2 specifics)

- **Development / PoC, not production.** No production licensing, HA, multi-tenant isolation, or
  fine-tuning — out of scope by kickoff decision.
- **The binding hardware constraint is memory bandwidth (~273 GB/s), not capacity.** The suite's
  bandwidth commentary is an architectural inference correlated with the LLM's measured tokens/s and
  memory — **not** a direct DRAM-bandwidth measurement.
- **Memory must be budgeted on the unified pool.** GPU and system RAM are the same ~121 GiB. The LLM
  fraction is capped at `0.45` for exactly this reason; over-setting it OOM-wedged the GPU once
  (2026-07-09) and was fixed by rebalancing.
- **`peak_process_rss_mb` is the API process only** and, in the suite, saturates after the first
  scenario (process-lifetime high-water mark). The **device-level** memory column is the per-scenario
  figure; the report says so.
- **GPU utilization reads `null`** on this unified-memory stack (in-container `nvidia-smi` returns
  N/A). We report it as unavailable rather than fabricate a number.
- **cuOpt fallback is OR-Tools (CPU).** No arm64/CUDA-13 cuOpt build was available; the routing solve
  is a real OR-Tools LP in-process, honestly labeled.
- **The LLM rationale is advisory only** — it explains the plan; it never computes or overrides a
  metric. Prompt injection in ingested text is flagged (including at retrieval time), never executed.
- **PPO is recommended, not mandated**, and lost here — reported honestly.
- **Customer data stays on-device.** Nothing ships off-box.

---

## 7. What's Next (Iteration 3 candidates)

- **Merged to `main`** — the `feat/iteration2-scaffolding-and-poa` branch is merged (2026-07-10).
- **RAG on a real corpus** — the advisory layer currently grounds on a synthesized scenario/plan
  corpus; wiring in real supplier docs / SOPs / planner notes is the natural next step.
- **Forecasting challenger** — add the LightGBM / deep challenger *only if it beats* the statistical
  baseline (same earn-its-place discipline as PPO).
- **Scale study** — push `stress-large` further to actually find the single-node limit and exercise
  the 2-node path, if a larger-than-prototype workload is in scope.
- **Production track** — licensing (NFR/NVAIE), hardening, and Helix-DC scale-up, separate from this
  PoC.

---

## 8. Supporting Documents (all in-repo)

- [`../../README.md`](../../README.md) — full project overview, hardware, status (§9), decisions (§11), caveats (§12).
- [`../DEVELOPMENT_JOURNAL.md`](../DEVELOPMENT_JOURNAL.md) — chronological truth ledger; the 2026-07-10 entry has the full result table and the review findings.
- [`../Iteration2_Plan_of_Action.md`](../Iteration2_Plan_of_Action.md) — the phase-by-phase build blueprint (phases 0–6 checked off).
- [`../Iteration2_Point3_Scaffolding_Response_to_Ryan.md`](../Iteration2_Point3_Scaffolding_Response_to_Ryan.md) — the model/tool rationale and before/after design.
- [`../containerization.md`](../containerization.md) — the arm64 four-service stack, unified-memory budget, and measurement caveats.
- [`../handoff.md`](../handoff.md) — quick-start commands and how to read the on-device panel honestly.
- [`../environment.md`](../environment.md) — live GB10 device specs.
- [`./AI_Jumpstart_MVP_Iteration1_v1_paper-grounded.md`](./AI_Jumpstart_MVP_Iteration1_v1_paper-grounded.md) · [`./AI_Jumpstart_MVP_Iteration1_v2_standalone.md`](./AI_Jumpstart_MVP_Iteration1_v2_standalone.md) — the Iteration 1 proposals this build realizes.
- `benchmark/suite-summary.md` — the generated per-run report (regenerate with `make bench-all`).

---

*Iteration 2 built on branch `feat/iteration2-scaffolding-and-poa`, verified live on the GB10
(`helix-gb10-intern`) and merged to `main` on 2026-07-10. Vertical: Manufacturing.
Product shape: Development / PoC.*
