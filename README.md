# AI Jumpstart MVP — Supply Chain Optimization on NVIDIA GB10

> **What this is:** An end-to-end supply-chain-optimization (SCO) prototype designed to run **entirely on a single GB10-class device** (Dell Pro Max with GB10 / NVIDIA DGX Spark sibling), from seeded synthetic data to an optimized plan. Built at **Helix, Connection Inc.** The pitch in one line: *a workload that used to need a rack now runs at the desk.*

> **How to use this file (humans + AI agents):** Read it all once. For the current build, jump to **[§9 Current Status](#9-current-status--iteration-2-prototype)**, **[§11 Confirmed Decisions](#11-confirmed-kickoff-decisions)**, and [`docs/handoff.md`](docs/handoff.md).

---

## Read First — Repo Hygiene & Source Notes

- **The RL paper used here is the authors' own paper** (Singh & Biswas, *Robustness of Policy-Gradient RL for Multi-Echelon Inventory Control*), authored under the authors' own names, with public code at `github.com/singhdivyank/multi-echelon-rl-inventory`. It is **shareable** and safe to commit.
- **`...v1_paper-grounded.md`** grounds its ROI reference numbers in that paper. It is fine to share internally / with Ryan. For **customer- or public-facing** material, prefer **`...v2_standalone.md`** — not for confidentiality reasons, but because broad public industry benchmarks (McKinsey/Gartner/BCG) are evidentially stronger than a single-benchmark study (one toy environment, one seed). The paper's own thesis is that single-environment wins aren't robust evidence.
- Customer data, when this ships, **stays on the device** (SED-encrypted NVMe). Never exfiltrate client data off-box; that is a core product promise.

A suggested `.gitignore` is in **[§10](#10-repository-structure)**.

---

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Business Context & Product Vision](#2-business-context--product-vision)
3. [Target Hardware (GB10 / Dell Pro Max)](#3-target-hardware-gb10--dell-pro-max)
4. [Project SOP (Ryan's authoritative framing)](#4-project-sop-ryans-authoritative-framing)
5. [Modeling & Technical Stack](#5-modeling--technical-stack)
6. [Data Elements & Pipeline](#6-data-elements--pipeline)
7. [Use-Case / Opportunity Map](#7-use-case--opportunity-map)
8. [Prototype Scope (depth over breadth)](#8-prototype-scope-depth-over-breadth)
9. [Current Status — Iteration 3 complete](#9-current-status--iteration-3-complete-demopilot-ready)
10. [Repository Structure](#10-repository-structure)
11. [Confirmed Kickoff Decisions](#11-confirmed-kickoff-decisions)
12. [Honest Caveats & Guardrails (carry-forward)](#12-honest-caveats--guardrails-carry-forward)
13. [Getting Started / Next Steps](#13-getting-started--next-steps)
14. [Glossary](#14-glossary)
15. [Source Materials / Provenance](#15-source-materials--provenance)

---

## 1. Project Overview

The goal is to "AI-fy" the supply chain end to end and package it as a sellable appliance. Helix (a Connection Inc. team) intends to sell an **"AI Jumpstart Service" preloaded on GB10 hardware**: a customer plugs their raw data into the device, and the on-device AI app handles their supply-chain optimization **locally and securely** — no cloud, data never leaves the box.

- **Roles:** Project built by the Helix AI intern (Ishan); manager/sponsor: **Ryan Spurr**.
- **Iteration model:** The work is phased (see Pic 4). **Iteration 1 = Points 1 & 2 only** (Use Cases & Value Proposition; Data Elements & Data Pipeline). Points 3 (SCO scaffolding) and 4 (Synthetic Dataset) are later.
- **The prototype** (per Ryan's SOP) is a 3-week accelerated build proving the full pipeline runs on-device and beats a naive baseline.

**Supply-chain pillars in scope (Pic 1):** demand · capacity · routing & logistics · costs.
**Target industries (Pic 1):** Manufacturing · Retail · Wholesale & Logistics · Hospitals.

---

## 2. Business Context & Product Vision

- **Flow (Pic 3/4):** `Customer Data → AI Jumpstart Service → GB10 device`. Sold packaged inside the hardware.
- **OEMs (Pic 1):** GB10 ships from multiple vendors — **Dell** (units in hand), plus **Lenovo, HP, Asus, Acer** (identical product). The solution is **not Dell-locked**.
- **Clustering:** A deployment can be **1× or 2× GB10 nodes** (the whiteboard's "1x / 2x GB10"). Two nodes pool to 256 GB (see §3).
- **Core success condition:** the full prototype runs on-device within the GB10's **128 GB nominal / ~121 GiB usable** unified-memory envelope, backed by a device-level measurement.

---

## 3. Target Hardware (GB10 / Dell Pro Max)

**Dell Pro Max with GB10** — OEM build of the NVIDIA GB10 Grace Blackwell platform (internal sibling of NVIDIA DGX Spark). Compute is fixed by the GB10 Superchip; OS/libraries are NVIDIA's standard DGX environment. *(Source: Ryan's spec sheet, compiled from public NVIDIA/Dell/reviewer docs, Jun 2026. Confirm on-device with `nvcc --version` and `nvidia-smi`.)*

| Spec | Value | Why it matters |
|---|---|---|
| SoC | GB10 Grace Blackwell (TSMC 3nm) | Fixed, unified CPU+GPU |
| CPU | 20-core Arm v9.2 (10× Cortex-X925 + 10× Cortex-A725) | **ARM64** toolchain target |
| GPU | Blackwell, 6,144 CUDA cores, 5th-gen Tensor Cores | cuOpt + PPO acceleration |
| AI compute | up to 1 PFLOP sparse FP4 (~1,000 TOPS) | Compute-rich |
| **Memory** | **128 GB LPDDR5X unified, ~273 GB/s, 256-bit bus** | **Budget AND the real bottleneck** |
| CPU–GPU link | NVLink-C2C (~5× PCIe Gen5) | Cheap CPU↔GPU handoffs |
| Networking | ConnectX-7: 2× 200 GbE QSFP + 10 GbE RJ45 | Enables 2-node clustering |
| Storage | up to 4 TB NVMe (Gen4), SED hardware encryption | Local data + model cache |
| Local model capacity | inference ≤ ~200B params; fine-tune ≤ ~70B (single node) | Sizes the local RAG LLM |
| Form / power | 150×150×51 mm, ~1.31 kg, ~240 W USB-C PD | The literal "rack → desk" story |

**Software stack (preinstalled via DGX OS 7 / NGC):** DGX OS 7 (~7.2.x, Ubuntu 24.04 LTS), Linux 6.11 NVIDIA Base OS, GPU driver R580 branch, **CUDA Toolkit 13.x**, cuDNN, NCCL, **TensorRT / TensorRT-LLM**, **RAPIDS**, NVIDIA Container Toolkit (Docker), **NGC catalog + NVIDIA NIM** inference microservices, PyTorch via NGC containers. Work is portable to DGX cloud/data-center.

> **cuOpt update (2026-07-27):** cuOpt 26.06.00 is now available for arm64/CUDA-13 (`pip install cuopt-cu13`).
> VRP benchmark: OR-Tools CPU wins below ~100 locations (our scale); cuOpt GPU wins at 200+.
> The main optimizer uses OR-Tools GLOP for transportation LP (a different problem class than cuOpt's VRP).
> OR-Tools stays as the lane-routing engine. See [Phase 6 in the journal](docs/DEVELOPMENT_JOURNAL.md).

### Clustering (2-node)
Two units bond over a single **200G QSFP56 passive DAC cable** (0.5 m, NVIDIA-approved, e.g. `Q56-200G-CU0-5`), point-to-point **RoCE/RDMA**, **NCCL** collectives, MPI on the CPU side, configured via **NVIDIA Sync "Cluster Assistant"**. Result: one logical node with **256 GB pooled memory, up to 8 TB storage, models up to ~400B params.** A separate out-of-band mgmt network (10 GbE RJ45 / Wi-Fi) is still needed (the DAC carries data only). **NVIDIA officially supports 2 nodes over the direct cable; 3+ requires a 200/400 GbE switch.**

### 🔴 Bandwidth honesty flag (most important hardware fact)
The device is **compute-rich but bandwidth-modest**: **~273 GB/s** unified-memory bandwidth is the binding limiter — not the 1 PFLOP compute or the 128 GB capacity. Memory-bandwidth-bound work (large-LLM token generation, big RL batches) feels this first.
**Implication for us:** the **RL policy network is tiny** (inventory-control policies are lightweight MLPs — the reference PPO used a 2×64 MLP), so the learned optimizer sits trivially within budget. The real memory/bandwidth pressure is the **local LLM + vector index** — right-size the NIM-served LLM accordingly.

### Hardware & Environment (live device)
The spec table above is the *target* platform. For the **actual values measured on the
device this repo runs on**, see [`docs/environment.md`](docs/environment.md) — it is
generated from the live GB10 (`helix-gb10-intern`) and date-stamped (probed **2026-06-26**).
Re-run the probe commands listed there to refresh it.

**Containerization:** GPU-in-container status, the pinned arm64 CUDA 13 base image, and constraints are tracked in [`docs/containerization.md`](docs/containerization.md).

Agent guardrails (bandwidth-vs-capacity, cuOpt-from-NGC, PPO-must-earn-its-place, the ~94%
caveat, etc.) are auto-loaded from [`.devin/rules/helix-sco.md`](.devin/rules/helix-sco.md).

---

## 4. Project SOP (Ryan's authoritative framing)

**Objective:** Build an end-to-end SCO prototype that runs entirely on a GB10-class device, from synthetic data generation to an optimized plan. "Runs fully on-device within the 128 GB envelope" is a core success condition.

**Scope guardrails:**
- One example company, one product family / small SKU set, a handful of locations — **depth over breadth**.
- Optimization must span **all four dimensions**: demand, inventory, multi-location, transportation/logistics.
- **Propose** technical choices (forecasting method, optimization formulation, classical solver vs. learned policy); the framework **must not prescribe** them.

**Measurable outcomes (set target numbers at kickoff):**
- Runs fully on-device within 128 GB; **peak memory and solve/inference time recorded**.
- **Beats a naive baseline** by a defined margin — X% cost reduction or service-level gain vs. a **simple reorder-point + shortest-route** heuristic.
- Synthetic dataset is **seeded/reproducible and documented**.
- Pipelines run **end-to-end re-runnably (ideally one command)**.
- A short **written + verbal handoff** at the end.

**Phased delivery (accelerated 3 weeks; guideline, speed favored):**

| Week | Focus | Checkpoint |
|---|---|---|
| **1 — Scope, data, environment** | Pin company/decision/metrics. Generate seeded synthetic data (demand w/ seasonality, inventory positions, locations, lanes, costs, lead times). Stand up the device; confirm the toolchain runs on **ARM64** (DGX OS 7/Ubuntu 24.04, CUDA 13.x, PyTorch via NGC; pull & verify **cuOpt**). | Data + baseline heuristic in place |
| **2 — Pipelines + optimization** | Build `ingest → forecast → optimize → output`; implement optimization across all four dimensions. First full run producing a plan, then iterate. | End-to-end run beating baseline on ≥1 metric |
| **3 — Benchmark, harden, hand off** | Benchmark on-device (memory, **bandwidth**, latency, GPU vs CPU util, where Blackwell actually helps). Stress larger scenarios — escalate to the **2-node 256 GB cluster** to find limits. Document assumptions/results; present. | Final demo + writeup |

---

## 5. Modeling & Technical Stack

**Engine layers (Pic 5):** Vector DB (vector) · LLM + RAG · Empirical AI Modeling.

**Three-tier optimization design (do not conflate these tiers):**
| Tier | Inventory | Routing/Transport | Role |
|---|---|---|---|
| **Naive baseline (target to beat)** | reorder-point / base-stock | shortest-route | The SOP's baseline; what we must beat by a set margin |
| **Strong classical solver** | tuned (s,S) | MILP / **cuOpt** | The honest comparison — a well-tuned classical that does NOT collapse |
| **Learned policy** | **continuous-action PPO** | (optional learned) | Recommended learned candidate; must justify itself vs. both above |

**Stance (reconciling "lead with PPO" vs SOP "don't prescribe"):** PPO is the **recommended learned candidate**, but the framework proposes options and lets **on-device evidence decide** (cost/service AND latency/memory). PPO has to beat the naive baseline *and* earn its place against the strong classical solver.

**Scaffolding options to confirm at kickoff:**
| Decision | Candidate options | Recommended start |
|---|---|---|
| Forecasting | Statistical (ETS/ARIMA, Croston for intermittent) · ML (gradient-boosted) · deep (temporal) | Seasonal statistical baseline first; add ML if it earns it |
| Inventory opt | reorder-point/base-stock (baseline) · tuned (s,S) (classical) · **PPO** (learned) | PPO vs. tuned base-stock |
| Routing | shortest-route (baseline) · MILP/**cuOpt** (classical) · learned | cuOpt |
| Classical vs learned | run both; decide on evidence | head-to-head benchmark |

**LLM + RAG role:** Provides a planner-facing natural-language interface, scenario retrieval, and human-readable rationale. **It contextualizes; it does NOT make the inventory/routing decision.** Serve via NIM, right-sized for bandwidth headroom.

---

## 6. Data Elements & Pipeline

**Data elements (synthetic, seeded, documented):** network topology (nodes/echelons/lanes); inventory state (on-hand, in-transit pipeline, outstanding orders, backlog per node); demand history (seasonal/trend/noise, promo calendar); per-lane lead times + variability; capacity & constraints (supplier caps, storage, vehicle/fleet); cost parameters (holding, ordering, backorder/lost-sales penalty, transport); routing data (distances/times, time windows, vehicle attrs); service targets (fill-rate, criticality tiers); unstructured context (supplier docs, SOPs, notes) for the RAG corpus.

**Pipeline (one command, on-device):**
```
[Seeded Synthetic Data Generator]            # reproducible; documented
        |
        v
(1) Ingest & Normalize  -> structured state (on-hand / in-transit / backlog per node)   [ARM CPU]
        |
        +--> (2) Vector DB (embeddings) <--retrieves--> (3) NIM LLM + RAG  [planner Q&A + rationale]
        |
        v
(4) Forecast  -> demand signal (method TBD)                                              [CPU/GPU]
        |
        v
(5) Optimize across 4 dims: demand - inventory - multi-location - transport              [Blackwell GPU]
        |    baseline: reorder-point + shortest-route   (beat this)
        |    classical: MILP / cuOpt + tuned base-stock
        |    learned:   continuous-action PPO
        v
[Optimized Plan]  + [Recorded: peak mem, bandwidth use, solve/inference latency, GPU vs CPU util]
```

---

## 7. Use-Case / Opportunity Map

Full per-industry × per-pillar matrices live in the deliverable docs (`/docs`). Summary:
- **Manufacturing** — BOM-driven, capacity-constrained; inventory is a large share of assets.
- **Retail** — seasonality + cross-store correlation + lost sales; best fit for the learned-policy story.
- **Wholesale & Logistics** — routing-heavy; cuOpt is the headline lever; bullwhip dynamics.
- **Hospitals** — service level / patient safety is the priority metric (NOT just cost). **No service-level RL win is currently substantiated — must be validated per site.**

The four industries are the **market landscape**; the prototype builds **one** in depth (§8).

---

## 8. Prototype Scope (depth over breadth)

| Dimension | Recommended choice (confirm at kickoff) |
|---|---|
| Example company | One mid-market distributor/retailer of a single product family |
| SKU set | One product family / ~5–20 SKUs |
| Locations | 1 supplier/DC → 3–5 regional stores/sites |
| Demand | Seasonal + noisy synthetic history |
| Inventory | On-hand, in-transit, backlog per node |
| Multi-location | Allocation across DC + sites |
| Transport | Lanes with lead times, capacity, cost |

Rationale: a retail/distribution example exercises **all four dimensions** cleanly and sits comfortably inside a single 128 GB node. The 2-node 256 GB cluster is reserved for Week-3 scale stress.

---

## 9. Current Status — Iteration 3 complete (demo/pilot-ready)

**Iteration 3 (Phases 0–6) is complete and verified on-device (2026-07-27).** The prototype is
demo/pilot-ready: reproducible results, real-corpus RAG, a polished web UI with a "Why This Plan"
summary, a recorded demo fallback, a fair RL evaluation, a scale study, and an honest cuOpt
re-check. Phase 7 (production track) is deferred to **Iteration 6** (see §13 for the roadmap).

- `make up` builds and starts the four arm64 services: `web`, `api`, `llm`, and `vectordb`.
- `make demo` generates data, rebuilds the web UI, and prints the demo URLs.
- `make test` — **69 passed, 2 xpassed** (71 total).
- `make bench-all` runs all four scenarios through baseline, classical, PPO, and advisory RAG/LLM.

**Real results (seed 12345, horizon 8, ppo-timesteps 128, Optuna seeded — fully reproducible):**

| Scenario | Baseline obj | Classical obj | Improvement | PPO obj | PPO outcome |
|---|---:|---:|---:|---:|---|
| `baseline` | 88,023 | **81,789** | **−7.1%** | 102,805 | lost |
| `component-shortage-shock` | 102,835 | **95,445** | **−7.2%** | 113,585 | lost |
| `demand-surge` | 100,735 | **94,165** | **−6.5%** | 115,162 | lost |
| `stress-large` | 2,622,335 | **2,521,615** | **−3.8%** | 2,867,271 | lost |

- **Tuned classical wins all four scenarios.** Seeded Optuna ensures deterministic results.
- **PPO was given a fair shot** (Phase 4: per-period MDP rebuild, CVaR tail-risk eval) and **lost all
  four on both objective and CVaR-75 tail risk**. Demoted to "evaluated, not shipped." Kept visible
  in the benchmark for transparency.
- **RAG advisory** grounded on 6 real manufacturing documents (supplier agreements, SOPs, playbooks)
  with retrieval-time injection scanning and Qdrant stale-point cleanup. LLM rationale surfaces as
  `llm_finalized` for all four scenarios.
- **On-device envelope:** peak memory ~65–68 GiB of ~121 GiB usable (55+ GiB headroom). Single-node
  holds at all tested scales up to 100x (28,800 series). LLM ~47 tokens/s.
- **cuOpt 26.06.00 now available** for arm64/CUDA-13 (verified 2026-07-27). VRP benchmark shows
  crossover at ~100 locations — OR-Tools CPU wins at prototype scale (≤152 lanes). OR-Tools stays
  as the lane-routing engine; cuOpt available for future 100+ stop fleet routing.
- **Scale ceiling** is forecast latency (~25ms/series), not memory. The optimizer is trivially fast
  (<0.4s at 100x). Memory stays at ~54% of envelope at all levels.

**Demo:** open `http://localhost:8081` for the live planner UI, or `http://localhost:8081?replay=true`
for a pre-recorded real run. See [`docs/DEMO_GUIDE.md`](docs/DEMO_GUIDE.md) for the full walkthrough.

See [`docs/handoff.md`](docs/handoff.md), [`docs/containerization.md`](docs/containerization.md),
[`docs/iteration-docs/`](docs/iteration-docs/) (the per-iteration handoff deliverables), and the
generated `benchmark/suite-summary.md` (regenerate with `make bench-all`) for the measured results.

---

## 10. Repository Structure

**Current (actual layout, condensed):**
```
README.md                                            # this file — stays at repo ROOT (GitHub landing page)
.gitignore                                           # keeps heavy/binary artifacts out of git
.devin/                                              # project rules / continuation guardrails
Dockerfile                                           # arm64 API image (includes cuOpt/OR-Tools capability)
docker-compose.yml                                   # four-service PoC stack
Makefile                                             # one-command build/test/run/bench entrypoints
benchmark/                                           # generated benchmark artifacts; do not trust stale runs
configs/                                             # runtime/scenario config
data/
  generator/                                         # seeded synthetic data generator
  scenarios/                                         # baseline, shock, surge, stress-large configs
  generated/                                         # regenerated scenario data
docs/
  iteration-docs/                                    # polished per-iteration handoff deliverables
    AI_Jumpstart_MVP_Iteration1_v1_paper-grounded.md # Iteration 1 — shareable internally (paper-based)
    AI_Jumpstart_MVP_Iteration1_v2_standalone.md     # Iteration 1 — shareable externally (public sources)
    AI_Jumpstart_MVP_Iteration2_handoff.md           # Iteration 2 — on-device prototype handoff (real results)
    AI_Jumpstart_MVP_Iteration3_handoff.md           # Iteration 3 — demo/pilot-ready handoff
  Iteration2_Plan_of_Action.md                       # Iteration 2 build blueprint (phases 0–6)
  Iteration2_Point3_Scaffolding_Response_to_Ryan.md  # Iteration 2 model/tool rationale
  Iteration3_Plan_of_Action.md                       # Iteration 3 build blueprint (phases 0–7)
  DEMO_GUIDE.md                                      # step-by-step demo walkthrough
  containerization.md                                # current arm64/four-service stack notes
  handoff.md                                         # quick-start commands and on-device caveats
  environment.md                                     # live GB10 device specs
  DEVELOPMENT_JOURNAL.md                             # chronological truth ledger
docker/
  llm/                                               # vLLM/Nemotron service image
  web/                                               # nginx static web image
refs/
  multi_echelon_rl_inventory_paper.pdf               # authors' own paper (shareable; code on GitHub)
  master_prompt.md                                   # Iteration-1 task definition (Points 1 & 2)
  Dell_Pro_Max_GB10_Specification.pdf                # Ryan's hardware spec (source for §3)
  whiteboards/
    Pic 1.jpeg ... Pic 5.jpeg                        # source whiteboard photos
src/
  api/                                                # FastAPI API incl. integrated cuOpt/OR-Tools capability (/cuopt/*)
  bench/                                              # profiler and Phase 6 all-scenario suite
  cli/                                                # thin API-first scenario-comparison CLI
  forecast/                                           # demand forecast
  ingest/                                             # raw/generated data -> structured state
  optimize/
    baseline/                                         # reorder-point + shortest-route
    classical/                                        # tuned classical optimizer, OR-Tools fallback
    learned/                                          # PPO candidate
  pipeline/                                           # API-reused run_head_to_head orchestration
  rag/                                                # Qdrant + local LLM advisory layer
tests/                                               # backend/unit/API regression tests
web/                                                 # React/Vite planner UI
```
> Keep generated scenario data and benchmark outputs reproducible from seed. Do not commit large
> model weights or stale benchmark artifacts as if they were current evidence.
> External code for the paper: `github.com/singhdivyank/multi-echelon-rl-inventory` (PPO/A3C envs, configs, training). Useful reference when building `src/optimize/learned`.

**`.gitignore` (at repo root):**
```
# generated data + benchmark reports: regenerate from seed / `make bench-all`
data/**/generated/
benchmark/*.json  benchmark/*.csv  benchmark/*.md
.env
# model weights / artifacts
*.ckpt  *.pt  *.onnx
# python
__pycache__/  *.pyc  .venv/  venv/
# web
web/node_modules/  web/dist/  web/*.tsbuildinfo
# os
.DS_Store
```
> The paper, whiteboards, and master prompt ARE committed. Large PDFs/images can move to Git LFS if size becomes an issue.

---

## 11. Confirmed Kickoff Decisions

Ryan confirmed these on 2026-06-30:

| Decision | Confirmed direction |
|---|---|
| Vertical | Manufacturing |
| Outcome framing | Real improvement vs. baseline plus resilience under worst-case shock; no pre-asserted percentage |
| Product shape | Development / Proof-of-Concept, not production |
| LLM | One shared NVIDIA Nemotron ~30B MoE at FP8 |
| Embeddings | `nomic-ai/nomic-embed-text-v1.5`, 768 dimensions |
| Vector store | Qdrant; LanceDB only if memory pressure requires it |
| NVAIE | Not required for development; NFR available if a gate is hit |
| Interface | Secure API first; CLI and web remain thin clients |
| Single vs. two node | Single node unless a measured ~121 GiB usable-memory limit is hit; two nodes remain the escalation route |

No kickoff decision authorizes a claimed win margin: each scenario reports its real run.
Fine-tuning, production licensing/hardening, and the two-node implementation remain out of scope.

---

## 12. Honest Caveats & Guardrails (carry-forward)

An agent continuing this work MUST preserve these — they are the difference between a defensible prototype and an overclaiming one:
- **PPO is recommended, not mandated.** Classical vs. learned is decided on on-device evidence.
- **RL is not a guaranteed win.** Published work shows generic deep-RL does not universally beat well-tuned heuristics; gains concentrate in non-stationary, high-dimensional, constrained problems.
- **The paper is single-benchmark / single-seed evidence.** Its own thesis is that such wins are not robust. Use its numbers only as reference points.
- **The ~94% figure is baseline-collapse + rescaled-metric, vs. an un-tuned baseline.** Never present it as flat steady-state savings.
- **The binding hardware constraint is memory bandwidth (~273 GB/s), not capacity.**
- **cuOpt is not preinstalled** and is unproven by the paper — pull from NGC, verify on ARM64, benchmark separately.
- **Hospitals: no service-level win is substantiated** — validate per site before any clinical claim.
- **Data sovereignty:** customer data stays on-device; do not design anything that ships it off-box.
- **Evidence basis:** the paper is shareable, but it's single-benchmark/single-seed evidence — use it for internal grounding, prefer v2's public benchmarks for external pitches.

---

## 13. Getting Started / Running the Prototype

**If you are resuming work (human or AI agent), start here:**

```bash
make up                        # build + start all four arm64 services
make test                      # 69 passed + 2 xpassed (71 total)
make demo                      # generate data, rebuild web, print URLs
```

Then open **`http://localhost:8081`** for the live planner UI, or **`http://localhost:8081?replay=true`**
for a pre-recorded real run. See [`docs/DEMO_GUIDE.md`](docs/DEMO_GUIDE.md) for the full demo
walkthrough including talk tracks.

**Other useful commands:**
```bash
make bench-all                 # run all 4 scenarios → benchmark/suite-summary.{json,md}
make run SCENARIO=baseline     # single scenario end-to-end
make scale-study               # run the 6-level scale study
make rag SCENARIO=...          # RAG advisory for a single scenario
make cli SCENARIO=...          # thin CLI over the same API
```

**Roadmap (current numbering).** Ryan's demo feedback (2026-07-29) inserted two iterations ahead of
the production track, so what earlier docs called "Iteration 4 = production" is now **Iteration 6**:

| Iteration | Content | State |
|---|---|---|
| 1 | Use cases / value prop; data elements & pipeline | ✅ Done |
| 2 | SCO scaffolding + synthetic dataset (working on-device prototype) | ✅ Done (`main`, 2026-07-10) |
| 3 | Productization, demo polish, honest RL fair-shot | ✅ Done (`main`, 2026-07-27) |
| **4** | **Dataset transparency layer** — a read-only "Know Your Data" view so a viewer can see the dataset a result ran on | 🎯 In progress |
| 5 | Conversational scenario/what-if analyst — grounded natural-language Q&A over the plan | 📝 Planned |
| 6 | Production / GA — real customer-data onboarding, hardening, multi-tenant isolation, licensing, packaging | ⏳ Not started |

**If continuing development:** read [`docs/Iteration4_Plan_of_Action.md`](docs/Iteration4_Plan_of_Action.md)
for the current build, and [`docs/Iteration3_Plan_of_Action.md`](docs/Iteration3_Plan_of_Action.md) §4
for the honest gap between this demo/pilot-ready prototype and a shippable product. The production
track (Iteration 6) is where real customer-data onboarding, hardening, multi-tenant isolation,
licensing, and packaging land.

**Definition of done (achieved):** one command (`make demo`) regenerates data and produces an
optimized plan, fully on-device within the 121 GiB envelope, beating the naive baseline in all four
scenarios, with peak memory / latency / resource profiles recorded, a polished demo UI, and a
complete handoff.

---

## 14. Glossary

- **GB10 / Grace Blackwell Superchip** — NVIDIA's unified CPU+GPU SoC; the target device.
- **Unified memory** — single coherent CPU+GPU memory pool (128 GB here); avoids host↔device copies.
- **MEIS / multi-echelon inventory** — jointly optimizing stock across tiers (supplier→DC→sites).
- **Echelon base-stock / (s,S) / reorder-point** — classical OR replenishment heuristics; optimal only under stationarity (Clark–Scarf).
- **Non-stationary** — demand/lead-time dynamics that drift (seasonality, shocks); where static set-points misfire.
- **PPO** — Proximal Policy Optimization; the recommended learned (RL) policy. Continuous action head = one order quantity per echelon.
- **cuOpt** — NVIDIA GPU route/optimization library (NOT preinstalled here).
- **RAG** — Retrieval-Augmented Generation; LLM answers grounded in retrieved context from the vector DB.
- **NIM** — NVIDIA Inference Microservices; how the local LLM is served.
- **NGC** — NVIDIA GPU Cloud catalog (containers/models).
- **NCCL / RoCE / DAC** — collective comms / RDMA-over-Ethernet / direct-attach-copper cable; the 2-node clustering path.
- **CVaR** — Conditional Value-at-Risk; risk-aware eval to catch the PPO shock-tail (a Point-3 concern).
- **Service level / fill rate** — fraction of demand met on time; the priority metric for Hospitals.

---

## 15. Source Materials / Provenance

- **Whiteboards `Pic_1..5.jpeg`** — Pic 1: supply-chain pillars + target industries + OEMs. Pic 2/4: hardware/architecture + customer-data→service→GB10 flow. Pic 3: high-level product flow. Pic 4: the four iteration points. Pic 5: tech stack (Vector DB, LLM+RAG, Empirical AI Modeling).
- **`multi_echelon_rl_inventory_paper.pdf`** — the authors' own paper (Singh & Biswas); PPO/A3C on multi-echelon inventory, stationary (Env-1) vs non-stationary (Env-2). Source of the v1 reference figures. **Shareable**; public code at `github.com/singhdivyank/multi-echelon-rl-inventory`.
- **`Dell_Pro_Max_GB10_Specification.pdf`** — Ryan's hardware spec (Jun 2026); source for §3.
- **`refs/master_prompt.md`** — Iteration-1 task definition (Points 1 & 2).
- **Ryan's SOP (Teams)** — prototype objective, scope guardrails, measurable outcomes, 3-week plan; source for §4.
- **Public ROI sources (v2)** — McKinsey, Gartner, BCG, Deloitte (AI in supply chain / distribution operations).

---

*Last updated: Iteration 3 complete (2026-07-27). Keep this README current as the single source of truth — update §9 and §11 as decisions are made and code lands.*
