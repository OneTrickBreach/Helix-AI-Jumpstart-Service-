# AI Jumpstart MVP — Supply Chain Optimization on NVIDIA GB10

> **What this is:** An end-to-end supply-chain-optimization (SCO) prototype designed to run **entirely on a single GB10-class device** (Dell Pro Max with GB10 / NVIDIA DGX Spark sibling), from seeded synthetic data to an optimized plan. Built at **Helix, Connection Inc.** The pitch in one line: *a workload that used to need a rack now runs at the desk.*

> **How to use this file (humans + AI agents):** Read it all once. If you are an AI coding agent resuming work, jump to **[§9 Current Status](#9-current-status--iteration-1)**, **[§11 Open Decisions](#11-open-decisions-for-kickoff)**, and **[§13 Next Steps](#13-getting-started--next-steps)** — that is where the project currently stands and what to do next. Everything above those is the context you need to not break the established direction or re-introduce already-fixed mistakes (see **[§12 Caveats](#12-honest-caveats--guardrails-carry-forward)**).

---

## ⚠️ Read First — Repo Hygiene & Source Notes

- **The RL paper used here is the team's own class submission** (Singh & Biswas, *Robustness of Policy-Gradient RL for Multi-Echelon Inventory Control*, CS 5180, Northeastern), authored under the authors' own names, with public code at `github.com/singhdivyank/multi-echelon-rl-inventory`. It is **shareable** and safe to commit. *(Note: do NOT circulate the separate anonymized NeurIPS reviewer-copy of the same study, and don't de-anonymize that submission if it's still under review — that file is confidential; this class version is not.)*
- **`...v1_paper-grounded.md`** grounds its ROI reference numbers in that class paper. It is fine to share internally / with Ryan. For **customer- or public-facing** material, prefer **`...v2_standalone.md`** — not for confidentiality reasons, but because broad public industry benchmarks (McKinsey/Gartner/BCG) are evidentially stronger than a single class-project benchmark (one toy environment, one seed). The paper's own thesis is that single-environment wins aren't robust evidence.
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
9. [Current Status — Iteration 1](#9-current-status--iteration-1)
10. [Repository Structure](#10-repository-structure)
11. [Open Decisions for Kickoff](#11-open-decisions-for-kickoff)
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
- **Core success condition:** "Runs fully on-device within the 128 GB unified-memory envelope" is itself a headline outcome, not an afterthought.

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

## 9. Current Status — Iteration 1

**DONE ✅ (documentation only — no code yet):**
- **Iteration 1, Points 1 & 2 delivered** in two versions:
  - `docs/AI_Jumpstart_MVP_Iteration1_v1_paper-grounded.md` — **shareable internally / with Ryan.** Uses the team's class-paper figures (PPO +36.76% stationary → +94.20% non-stationary) as **target-margin reference points** (not as committed results). For external pitches, prefer v2 (stronger evidence base).
  - `docs/AI_Jumpstart_MVP_Iteration1_v2_standalone.md` — **SHAREABLE.** Same structure, grounded only in public sources (McKinsey/Gartner/BCG/Deloitte) + peer-reviewed RL literature; no paper dependency.
- Both docs include: SOP alignment, confirmed GB10 hardware spec, prototype scope, data elements + pipeline, scaffolding options, measurable-outcomes table, 3-week plan, and an honest-caveats appendix.
- **Corrections already made (do NOT regress these):**
  - Removed fabricated per-pillar percentages; the paper provides ONE aggregate inventory-cost number, on ONE toy benchmark, ONE seed.
  - Separated cuOpt/routing as a capability NOT evaluated by the paper.
  - Removed the unsupported hospital service-level claim.
  - Reframed the ~94% as "disruption-avoided cost vs. an un-tuned baseline on a rescaled metric," not flat savings.
  - Corrected the hardware constraint from "128 GB capacity" to "**~273 GB/s bandwidth**"; noted the RL policy is tiny and the LLM/index is the real load.

**NOT STARTED ⛔ (the actual build):**
- Point 3 (full SCO scaffolding spec) and Point 4 (full synthetic-dataset spec) beyond kickoff-level proposals.
- **All code:** synthetic data generator, ingest, forecast, optimizers (baseline/classical/learned), RAG layer, end-to-end one-command runner, benchmarking harness.
- Device standup / ARM64 toolchain verification / cuOpt-on-NGC verification.
- Kickoff target numbers (the "X%" margin, memory/latency targets) — not yet set.

---

## 10. Repository Structure

**Current (actual layout):**
```
README.md                                            # this file — stays at repo ROOT (GitHub landing page)
.gitignore                                           # keeps heavy/binary artifacts out of git
.claude/                                             # tooling config (untouched)
docs/
  AI_Jumpstart_MVP_Iteration1_v1_paper-grounded.md   # shareable internally (class-paper based)
  AI_Jumpstart_MVP_Iteration1_v2_standalone.md       # shareable externally (public sources)
refs/
  multi_echelon_rl_inventory_paper.pdf               # team's class paper (shareable; code on GitHub)
  master_prompt.md                                   # Iteration-1 task definition (Points 1 & 2)
  Dell_Pro_Max_GB10_Specification.pdf                # Ryan's hardware spec (source for §3)
  whiteboards/
    Pic 1.jpeg ... Pic 5.jpeg                        # source whiteboard photos
data/                                                # scaffolded — empty (.gitkeep)
  generator/            # seeded synthetic data generation (documented seeds)
  scenarios/            # scenario configs (small -> stress)
src/                                                 # scaffolded — empty (.gitkeep)
  ingest/               # raw -> structured state (on-hand/in-transit/backlog per node)
  forecast/             # demand forecasting (method TBD; start statistical)
  optimize/
    baseline/           # reorder-point + shortest-route (the target to beat)
    classical/          # MILP / cuOpt + tuned (s,S)
    learned/            # continuous-action PPO
  rag/                  # vector DB + NIM-served LLM (advisory only)
  pipeline/             # end-to-end runner -> ONE command
benchmark/                                           # scaffolded — empty (.gitkeep): peak mem, ~273 GB/s bandwidth, latency, GPU vs CPU util
configs/                                             # scaffolded — empty (.gitkeep): seeds, targets, hardware/runtime config
```
> The `src/`, `data/`, `benchmark/`, and `configs/` trees are **scaffolded but empty** (`.gitkeep` placeholders) — the build has not started (see §9, §13). Still to add when the build lands: `run.sh`/`Makefile` (one-command entrypoint) and `requirements`/env (ARM64-aware deps; prefer NGC containers).
> External code for the paper: `github.com/singhdivyank/multi-echelon-rl-inventory` (PPO/A3C envs, configs, training). Useful reference when building `src/optimize/learned`.

**`.gitignore` (at repo root):**
```
# generated data: regenerate from seed instead of committing
data/**/generated/
# model weights / artifacts
*.ckpt  *.pt  *.onnx
# python
__pycache__/  *.pyc  .venv/  venv/
# os
.DS_Store
```
> The class paper, whiteboards, and master prompt ARE committed. Large PDFs/images can move to Git LFS if size becomes an issue.

---

## 11. Open Decisions for Kickoff

These are intentionally unset (the SOP says "set together at kickoff"):
1. **The example company / product family / exact locations** (recommendation in §8).
2. **The win margin** — X% cost reduction or service-level gain vs. reorder-point + shortest-route.
3. **On-device targets** — peak-memory ceiling (within 128 GB), solve/inference latency target.
4. **Forecasting method** — start statistical, or go straight to ML/deep?
5. **Whether the learned policy is PPO only, or PPO + a learned router.**
6. **Single-node demo vs. 2-node cluster as the headline** (affects whether cluster setup moves into Week 1–2).
7. **LLM size for RAG** (≤ ~200B inference single-node, but bandwidth-bound — pick conservatively).
8. **Whether any fine-tuning is in scope** (≤ ~70B single-node cap).

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
- **Evidence basis:** the class paper is shareable, but it's single-benchmark/single-seed academic evidence — use it for internal grounding, prefer v2's public benchmarks for external pitches.

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
- **`multi_echelon_rl_inventory_paper.pdf`** — the team's own class paper (Singh & Biswas, CS 5180, Northeastern); PPO/A3C on multi-echelon inventory, stationary (Env-1) vs non-stationary (Env-2). Source of the v1 reference figures. **Shareable**; public code at `github.com/singhdivyank/multi-echelon-rl-inventory`. *(Distinct from the anonymized NeurIPS reviewer copy of the same study — that one is confidential and should not be circulated.)*
- **`Dell_Pro_Max_GB10_Specification.pdf`** — Ryan's hardware spec (Jun 2026); source for §3.
- **`refs/master_prompt.md`** — Iteration-1 task definition (Points 1 & 2).
- **Ryan's SOP (Teams)** — prototype objective, scope guardrails, measurable outcomes, 3-week plan; source for §4.
- **Public ROI sources (v2)** — McKinsey, Gartner, BCG, Deloitte (AI in supply chain / distribution operations).

---

*Last updated at end of Iteration 1 (documentation complete; build not yet started). Keep this README current as the single source of truth — update §9 and §11 as decisions are made and code lands.*