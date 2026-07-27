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
9. [Current Status — Iteration 2 prototype](#9-current-status--iteration-2-prototype)
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

> ⚠️ **cuOpt is NOT in the preinstalled list.** Pull it from NGC and verify it runs on ARM64 early in Week 1. Treat as a schedule risk.

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

## 9. Current Status — Iteration 2 prototype

**Phases 0–6 built:** the API-first Manufacturing PoC covers deterministic synthetic data,
ingest/forecast, baseline and tuned-classical optimization, the PPO candidate, Qdrant-backed RAG
through one shared Nemotron 30B FP8 service, secure API endpoints, truthful SSE progress, a thin
CLI, the web comparison view, and an all-scenario on-device benchmark suite.

- `make up` builds and starts the four arm64 services: `web`, `api`, `llm`, and `vectordb`;
  GPU reservations are declared for `api` and `llm`.
- `make run SCENARIO=baseline` regenerates seeded input and emits an on-device baseline plan.
- `make bench-all` regenerates and runs all four scenarios through baseline, classical, PPO, and
  the advisory RAG/LLM stage, writing `benchmark/suite-summary.json` and `.md`.
- PPO remains visible whether it wins or loses. The tuned-classical result is the prototype's
  evidence-based default when it wins.
- cuOpt is unavailable for this arm64/CUDA combination; the explicitly reported fallback is
  OR-Tools on CPU. The cuOpt/OR-Tools capability is served in-process by `api` at `/cuopt/*`
  (no separate container), matching how routing is actually solved.
- Process RSS and the allocation-rate proxy are labeled honestly. Suite-level memory is sampled
  from the device/host unified pool; GPU utilization remains `null` when the GB10 probe reports N/A.

**Latest live-run status (2026-07-17): Iteration 3 Phase 2 complete and verified on-device.**
`make up` → `make test` (**56 passed, 2 xfail**) → `make bench-all` (all four scenarios) → `make rag` all pass on
the GB10. Real results (seed 12345, horizon 8, ppo-timesteps 128, Optuna seeded — reproducible):

- **Winners by evidence:** tuned classical wins **all four** scenarios: `baseline` (obj 88 022 → 81 789,
  −7.1%), `component-shortage-shock` (102 835 → 95 445, −7.2%), `demand-surge` (100 735 → 94 165,
  −6.5%), `stress-large` (2 622 335 → 2 521 615, −3.8%). With the Optuna search now seeded (Phase 1),
  classical deterministically finds params that beat the naive baseline in every scenario.
- **PPO lost in all four scenarios** (higher cost, highest latency/memory) — reported honestly, not
  hidden. Tuned classical is the evidence-based default.
- **RAG advisory** now grounded on a real on-disk document corpus (6 supplier/SOP/playbook documents)
  with retrieval-time injection scanning and Qdrant stale-point cleanup. LLM rationale surfaces as
  `llm_finalized` (not template fallback) for all four scenarios.
- **On-device envelope:** device peak memory ~67 GiB of the ~121 GiB usable pool (≥53 GiB headroom
  in every scenario); 90% flag clear. **stress-large stays single-node; the 2-node path is not
  needed.** Shared LLM ~47 tokens/s.

> The earlier `nvml error: gpu requires reset` wedge was a unified-memory OOM (the LLM's
> `--gpu-memory-utilization` was set too high for the shared 121 GiB pool). Fixed by rebalancing it
> to `0.45` after a host reboot; the wedge has not recurred.

See [`docs/handoff.md`](docs/handoff.md), [`docs/containerization.md`](docs/containerization.md),
[`docs/iteration-docs/`](docs/iteration-docs/) (the Iteration 1 + 2 handoff deliverables), and the
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
  Iteration2_Plan_of_Action.md                       # Iteration 2 build blueprint (phases 0–6)
  Iteration2_Point3_Scaffolding_Response_to_Ryan.md  # Iteration 2 model/tool rationale
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

## 13. Getting Started / Next Steps

**If you are resuming in an IDE (human or AI agent), start here:**

**Week 1 — first concrete actions:**
1. **Stand up the toolchain on ARM64.** Confirm `nvcc --version` (CUDA 13.x) and `nvidia-smi` (R580 driver) on DGX OS 7 / Ubuntu 24.04. Prefer NGC containers for PyTorch/RAPIDS/TensorRT-LLM.
2. **Verify cuOpt** is obtainable from NGC and runs on this ARM64 box. (Schedule risk — do this before relying on it.)
3. **Scaffold the proposed repo structure** (§10). Create `run.sh`/`Makefile` as the one-command entrypoint stub.
4. **Build the seeded synthetic data generator** (`/data/generator`): demand with seasonality/trend/noise, inventory positions, 1 DC + 3–5 sites, lanes with lead times + capacity + costs. Fix and document the seed; make regeneration deterministic.
5. **Implement the naive baseline** (`/src/optimize/baseline`): reorder-point (inventory) + shortest-route (logistics). This is the number to beat and must exist before optimization work.
6. **Confirm kickoff decisions** in §11 with Ryan; record the chosen target margin and on-device targets in `/configs`.

**Then Week 2** = build `ingest → forecast → optimize → output`, implement all four dimensions, get a full run beating baseline on ≥1 metric. **Week 3** = benchmark on-device (incl. bandwidth + GPU/CPU split), stress to the 2-node cluster, document + present.

**Definition of done (prototype):** one command regenerates data and produces an optimized plan, fully on-device within 128 GB, beating the naive baseline by the agreed margin, with peak memory / bandwidth / latency recorded and a short writeup + demo.

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

*Last updated during Iteration 3 Phase 3 (2026-07-17). Keep this README current as the single source of truth — update §9 and §11 as decisions are made and code lands.*
