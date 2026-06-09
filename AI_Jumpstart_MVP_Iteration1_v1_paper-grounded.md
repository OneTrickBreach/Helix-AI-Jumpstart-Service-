# AI Jumpstart MVP on NVIDIA GB10 — Iteration 1 (v1, Paper-Grounded · SOP-Aligned)

**Prepared for:** Ryan | Helix, Connection Inc.
**Scope:** Pic 4, Points 1 & 2 (Use Cases & Value Proposition; Data Elements & Data Pipeline), fine-tuned to Ryan's prototype SOP.
**Empirical basis:** *Robustness of Policy-Gradient RL for Multi-Echelon Inventory Control* (PPO vs. fixed analytical base-stock; A3C vs. tuned (s,S)).

> **Evidence integrity note.** This version cites the RL paper. The paper reports two PPO results — a single aggregate inventory-cost improvement of **+36.76%** (stationary) and **+94.20%** (non-stationary) — on **one** small benchmark (1 warehouse, 3 retailers), at **one** seed, for **inventory replenishment only** (no routing/cuOpt). The paper's own thesis is that single-environment, single-seed wins are *not* robust evidence. Treat its numbers as **reference points to inform the kickoff target margin**, not as committed prototype results. (The paper is also a *confidential reviewer copy* — keep this version internal.)

---

## Alignment to Ryan's Prototype SOP

This deliverable now serves the prototype objective: **an end-to-end SCO prototype running entirely on a GB10-class device, from synthetic data to an optimized plan.** Key SOP constraints folded in below:

- **On-device is a success condition, not an afterthought.** The whole pipeline must run inside the **128GB unified LPDDR5x** envelope (shared CPU/GPU); peak memory and solve/inference time are recorded metrics. Narrative: *a workload that used to need a rack now runs at the desk.*
- **Depth over breadth.** One example company, one product family / small SKU set, a handful of locations — see §1.6.
- **All four optimization dimensions** in scope: demand, inventory, multi-location, transportation/logistics.
- **Beat a naive baseline by a margin set at kickoff.** Baseline = **simple reorder-point (inventory) + shortest-route (logistics)**. Margin (X% cost or service-level) is set jointly at kickoff.
- **Propose, don't prescribe, the modeling.** Forecasting method, optimization formulation, and *classical solver vs. learned policy* are proposed as candidates and decided on evidence (see §2.3). PPO is our recommended learned candidate, **benchmarked head-to-head** against a strong classical solver.
- **Reproducible & re-runnable.** Synthetic dataset is seeded/documented; pipeline runs end-to-end, ideally one command.
- **3-week phasing** (see §3) with a short written + verbal handoff.

---

## Executive Thesis

Classical OR inventory heuristics — **reorder-point / base-stock / (s, S)** — are provably optimal **only under strict stationarity**. Their set-points come from average demand-over-lead-time, so under seasonality, correlation, capacity caps, and heavy-tailed lead times they aim at a target that no longer exists, producing simultaneous overstock and stockout. The paired **shortest-route** logistics heuristic ignores capacity, time windows, and live conditions.

The reference study illustrates the inventory side: against a **fixed, never-re-tuned** base-stock baseline, continuous-action **PPO**'s aggregate inventory-cost advantage widens from **+36.76%** (stationary) to **+94.20%** (non-stationary) — and the paper is explicit that *most of that widening is the legacy baseline collapsing under shocks*, partly on a rescaled cost metric, not PPO getting intrinsically smarter.

**The prototype proposition:** a learned policy conditions on the full state (on-hand, in-transit pipeline, backlog per node) and adapts as conditions shift; the naive baseline cannot. We will *prove this on-device* against the reorder-point + shortest-route baseline, and benchmark the learned policy against a strong classical solver to see whether the learned approach earns its place.

---

## Target-Margin Reference (set the actual target at kickoff)

Per SOP, the prototype's win margin is agreed at kickoff. These reference points inform that conversation — they are *not* the committed number:

| Reference (inventory cost vs. fixed legacy baseline) | Value | Caveat |
|---|---|---|
| Stationary demand | ~37% (paper Env-1) | Single toy environment, single seed |
| Non-stationary / shock-exposed | up to ~94% (paper Env-2) | Mostly *baseline collapse* vs. an un-tuned baseline; partly a rescaled metric |

> **Pitch discipline.** Against the SOP's naive reorder-point + shortest-route baseline, a meaningful win is highly plausible. Against a *re-tuned* classical solver the margin shrinks substantially (the paper says so). Set a conservative, defensible kickoff target (resilience under shock, not a flat headline %), then let the on-device benchmark report the real number.

---

# 1. Use Cases & Value Proposition (Opportunity Map)

The four target industries below are the market landscape. The 3-week prototype builds **one** of them in depth (§1.6). The final column states the evidence basis: **[P]** paper-grounded (inventory), **[E]** plausible extrapolation, **[C]** cuOpt capability not evaluated by the paper.

## 1.1 Manufacturing
| Pillar | Pain Point | Legacy Failure Mode (Villain) | GB10-Powered Outcome | Basis |
|---|---|---|---|---|
| **Demand** | Lumpy, correlated component demand up the BOM | Reorder-point tuned to mean demand-over-lead-time; misfires on shifts | PPO conditions on full multi-echelon state | **[P]** |
| **Capacity** | Finite line/plant throughput; surge bottlenecks | Heuristic assumes unconstrained replenishment | Capacity-bounded learned policy | **[P]** |
| **Routing & Logistics** | Multi-tier inbound + finished-goods distribution | Shortest-route ignores caps/time windows | cuOpt / MILP route optimization | **[C]** |
| **Costs** | Joint holding + ordering + backorder across echelons | Per-tier optimization blows up a tier over | Joint discounted-cost minimization | **[P]** |

## 1.2 Retail
| Pillar | Pain Point | Legacy Failure Mode (Villain) | GB10-Powered Outcome | Basis |
|---|---|---|---|---|
| **Demand** | Seasonality, promotions, cross-store correlation | Static set-points never re-aligned to the live season | PPO tracks shifting, correlated demand | **[P]** |
| **Capacity** | DC / shelf / backroom limits | Reorder-point ignores ceilings → over-orders | Capacity-aware policy | **[P]** |
| **Routing & Logistics** | Replenishment cadence, last-mile | Fixed schedules / shortest-route | cuOpt dynamic routing | **[C]** |
| **Costs** | Markdowns + lost-sales stockouts | Mean-tuned policy over/under-shoots at once | Joint cost min w/ lost-sales penalty | **[P]** |

## 1.3 Wholesale & Logistics
| Pillar | Pain Point | Legacy Failure Mode (Villain) | GB10-Powered Outcome | Basis |
|---|---|---|---|---|
| **Demand** | Bullwhip-amplified, bursty B2B orders | Base-stock smooths to a rarely-hit mean | PPO responds to live pipeline state | **[E]** |
| **Capacity** | Warehouse + fleet capacity caps | Unconstrained heuristic over-orders | Capacity-bounded policy | **[P]** |
| **Routing & Logistics** | Large-scale multi-stop / multi-lane | Manual / shortest-route at scale | **cuOpt** GPU route optimization — core lever | **[C]** |
| **Costs** | Holding vs. transport trade-off | Tier-by-tier misses network trade-off | Network-wide joint cost min | **[P/C]** |

## 1.4 Hospitals
| Pillar | Pain Point | Legacy Failure Mode (Villain) | GB10-Powered Outcome | Basis |
|---|---|---|---|---|
| **Demand** | Census/case-mix, seasonal surges, critical low-volume items | Static par levels blind to surges | PPO adapts par levels to live census | **[E]** |
| **Capacity** | Storage, perishables, cold-chain | Heuristic ignores expiry/storage caps | Constraint-aware policy | **[P/E]** |
| **Routing & Logistics** | Intra-system distribution | Fixed par-restock rounds | cuOpt internal distribution | **[C]** |
| **Costs** | Holding + critical-item stockout penalty | Under-protects against rare critical shortages | Shortage-weighted policy (**service level NOT claimed from paper**) | **[P]** |

## 1.6 Prototype Scope Selection (depth over breadth)

| Dimension | Prototype Choice (recommended; confirm at kickoff) |
|---|---|
| **Example company** | One mid-market distributor/retailer of a single product family (concrete, demo-friendly) |
| **SKU set** | One product family / small SKU set (e.g., ~5–20 SKUs) |
| **Locations** | A handful — e.g., 1 supplier/DC → 3–5 regional stores/sites |
| **Demand** | Seasonal + noisy history (closest analog to the paper's hard environment) |
| **Inventory** | Multi-echelon positions: on-hand, in-transit, backlog per node |
| **Multi-location** | Allocation across the DC + sites |
| **Transportation/logistics** | Lanes between nodes with lead times, capacity, and cost |

> A retail/distribution example is recommended because it exercises **all four dimensions** cleanly and its seasonal, correlated demand is exactly where the learned-policy story is strongest. Final company/SKU/locations are pinned at kickoff (SOP Week 1).

---

# 2. Data Elements & End-to-End Pipeline

## 2.1 Data Elements (synthetic, seeded, documented)

| Category | Specific Raw Elements | Dimension Served |
|---|---|---|
| **Network topology** | Nodes (supplier/DC/sites), echelon structure, lane graph | Multi-location |
| **Inventory state** | On-hand by SKU/node, in-transit pipeline, outstanding orders, backlog | Inventory |
| **Demand history** | Seeded synthetic series with seasonality/trend/noise, promo calendar | Demand |
| **Lead times** | Per-lane lead-time draws + variability | Inventory, Transport |
| **Capacity & constraints** | Supplier caps, storage limits, vehicle/fleet capacity | Inventory, Transport |
| **Cost parameters** | Holding, ordering, backorder/lost-sales penalty, transport cost | Costs (all dims) |
| **Routing data** | Lane distances/times, time windows, vehicle attributes | Transport |
| **Service targets** | Fill-rate / service-level targets, criticality tiers | Demand, Costs |
| **Unstructured context** | Supplier docs, SOPs, planner notes | Vector DB / RAG corpus |

## 2.2 Pipeline (ingest → forecast → optimize → output; one command, on-device)

```
[Seeded Synthetic Data Generator]   <-- reproducible; documented
        |
        v
(1) Ingest & Normalize  --> structured state (on-hand / in-transit / backlog per node)   [ARM CPU]
        |
        +--> (2) Vector DB (embeddings) <--retrieves--> (3) LLM + RAG  [planner Q&A + rationale]
        |
        v
(4) Forecast  --> demand signal (method TBD, §2.3)                                         [CPU/GPU]
        |
        v
(5) Optimize across 4 dimensions: demand • inventory • multi-location • transport          [Blackwell GPU]
        |   - Naive baseline: reorder-point + shortest-route  (target to beat)
        |   - Strong classical: MILP / cuOpt + tuned base-stock
        |   - Learned candidate: continuous-action PPO
        v
[Optimized Plan]  +  [Recorded metrics: peak unified-memory, solve/inference latency, GPU vs CPU util]
```

- **Vector DB + LLM + RAG** provide a planner-facing natural-language interface and decision rationale; they **contextualize**, they do **not** make the inventory/routing decision.
- The entire chain targets a **single re-runnable command** and must stay within the **128GB** budget.

## 2.3 Scaffolding Options to Confirm at Kickoff (propose, don't prescribe)

| Decision | Candidate options | Recommended starting point |
|---|---|---|
| **Forecasting** | Statistical (ETS/ARIMA, Croston for intermittent) · ML (gradient-boosted) · deep (temporal) | Seasonal statistical baseline first; add ML if it earns it |
| **Inventory optimization** | Reorder-point / base-stock (baseline) · tuned (s,S) (classical) · **PPO** (learned) | PPO as learned candidate vs. tuned base-stock |
| **Routing/transport** | Shortest-route (baseline) · MILP / **cuOpt** (classical) · learned | cuOpt for routing |
| **Classical vs. learned** | Run both; decide on cost/service **and** on-device latency/memory | Benchmark head-to-head |

> This is the honest reconciliation of the SOP ("don't prescribe") with the PPO lead: PPO is the recommended *learned* candidate, but it has to **beat the naive baseline** and **justify itself against a strong classical solver** on-device — including the paper's known PPO shock-tail risk (a Week-3 stress target).

---

# 3. Measurable Outcomes & Phased Plan

## 3.1 Success Metrics (set target values at kickoff)

| Outcome | Metric | Target |
|---|---|---|
| On-device feasibility | Peak unified-memory; fits in 128GB w/ headroom | _set at kickoff_ |
| Speed | Solve/inference latency per plan | _set at kickoff_ |
| Hardware story | GPU vs CPU utilization; where Blackwell actually helps | documented |
| Quality | % cost reduction **or** service-level gain vs. reorder-point + shortest-route | _X% set at kickoff_ |
| Reproducibility | Seeded dataset; documented | yes/no |
| Re-runnability | End-to-end, ideally one command | yes/no |
| Handoff | Short written + verbal | delivered |

## 3.2 Three-Week Plan (accelerated)

| Week | Focus | Checkpoint |
|---|---|---|
| **1** | Scope, data, environment — pin company/decision/metrics; generate seeded synthetic data (seasonal demand, inventory, locations, lanes, costs, lead times); confirm ARM64 toolchain | Data + baseline heuristic in place |
| **2** | Pipelines + optimization — build ingest→forecast→optimize→output; implement all four dimensions; first full run, then iterate | End-to-end run beating baseline on ≥1 metric |
| **3** | Benchmark, harden, hand off — on-device benchmark (memory/latency/GPU vs CPU); stress larger scenarios to find limits; document; present | Final demo + writeup |

---

## Appendix — Honest Caveats

- **PPO is the recommended learned candidate, not a mandate.** Per SOP, classical vs. learned is decided on evidence; continuous action head + full-state conditioning are why PPO leads the learned options.
- **The ~94% reference is vs. an un-tuned baseline on a rescaled metric** — pitch resilience, set a conservative kickoff target.
- **Single-benchmark evidence; validate per scenario** (the paper's own thesis).
- **Known PPO shock-tail risk** → Week-3 stress target; consider risk-aware (CVaR) evaluation in Point 3 scaffolding.
- **Routing/cuOpt unproven by the paper** — benchmark separately.
- **Hospitals: no service-level win supported by the paper** — validate per site.
- **On-device budget is real engineering** — model size + index + RL workload must coexist in 128GB; resolve train-on-device vs. serve-with-offline-retrain at kickoff.
- **Deferred:** Point 3 (full SCO scaffolding) and Point 4 (full dataset spec) beyond the kickoff-level proposals above.