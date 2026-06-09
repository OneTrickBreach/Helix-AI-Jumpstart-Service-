# AI Jumpstart MVP on NVIDIA GB10 — Iteration 1

**Prepared for:** Ryan | Helix, Connection Inc.
**Scope:** Pic 4, Points 1 & 2 only (Use Cases & Value Proposition; Data Elements & Data Pipeline)
**Deferred to later iterations:** Point 3 (SCO scaffolding), Point 4 (Synthetic Data Set)
**Empirical basis:** *Robustness of Policy-Gradient RL for Multi-Echelon Inventory Control* (PPO vs. fixed analytical base-stock baseline; A3C vs. tuned (s,S) baseline)

> **Evidence integrity note (read first).** This paper reports exactly **two** PPO results — a single aggregate inventory-cost improvement of **+36.76%** (stationary) and **+94.20%** (non-stationary) — measured on **one** small benchmark (1 warehouse, 3 retailers), at **one** random seed. It does **not** break improvement down by supply-chain pillar, and it covers **inventory replenishment only** (no routing, no cuOpt). The paper's own thesis is that single-environment, single-seed wins are *not* robust evidence. Every industry- or pillar-level number in this document is therefore an **illustrative extrapolation, not a measured result**, and is labeled as such. Use the headline band to frame the *story*; do not present granular per-pillar percentages as validated.

---

## Executive Thesis

Classic Operations Research inventory heuristics — **echelon base-stock** and **(s, S) reorder-point** — are provably optimal *only under strict stationarity*. Their set-points are calibrated against a single statistic (mean demand-over-lead-time) and **nothing else**. The moment a supply chain becomes non-stationary — seasonality, correlated demand, capacity bottlenecks, heavy-tailed lead times, lost sales — those set-points are no longer aimed at the right target, and the policy degrades.

The reference study quantifies this. Against a **fixed, never-re-tuned** base-stock baseline, a **continuous-action PPO** agent's aggregate inventory-cost advantage **widens from +36.76% (stationary) to +94.20% (non-stationary)**. The paper is explicit on the mechanism: *most of that widening is the legacy baseline collapsing under shocks*, not PPO becoming intrinsically smarter. It also notes the Env-2 cost metric itself changed (added lost-sales penalties, widened bounds), so the 94.20% is partly a rescaling artifact, not a clean "94% of spend saved."

**The value proposition:** PPO conditions its replenishment decisions on the *full system state* (on-hand, in-transit pipeline, backlog at every node), so when conditions shift, it adapts; the static heuristic cannot. The GB10 makes this deployable as a single secure on-premise appliance.

---

## Headline ROI Band (the only paper-grounded figure)

There is one defensible number to anchor the pitch — an **aggregate inventory-cost** band, applied to inventory replenishment, framed as resilience:

| Operating Regime | PPO-vs-fixed-legacy Inventory-Cost Gap | What it actually means |
|---|---|---|
| **Stationary / stable demand** | **~37%** (paper: Env-1) | PPO's structural edge: it reacts to full pipeline state, not just inventory position. |
| **Non-stationary / shock-exposed** | **up to ~94%** (paper: Env-2) | Mostly the *fixed* legacy baseline collapsing under caps + shocks. This is **disruption-avoided cost**, not steady-state savings, and partly reflects a changed cost metric. |

> **Pitch discipline.** Lead with the *resilience* story ("your static policy breaks when conditions move; ours adapts"), not a flat savings claim. Two honesty guardrails: (a) the upper bound is measured against a baseline that was *deliberately never re-tuned* — against a re-tuned heuristic the paper says the margin "would shrink substantially"; (b) all figures come from one toy environment, so treat them as directional, not contractual.

---

# 1. Use Cases & Value Proposition

The matrices below map the four supply-chain pillars to the legacy failure mode and the GB10-powered outcome. The final column states the **evidence basis** rather than a fabricated percentage, so the deck stays honest under scrutiny.

**Legend — Evidence basis:**
- **[P] Paper-grounded (inventory):** mechanism is directly supported by the PPO inventory result.
- **[E] Extrapolation:** plausible benefit, *not* measured in this paper.
- **[C] cuOpt capability:** GB10 routing optimization — a real product capability, but **not** evaluated in this paper; needs its own benchmark.

## 1.1 Manufacturing

Inventory routinely represents **20–60% of total assets** for a manufacturer (per the paper's intro), so policy gains are material. Manufacturing is BOM-driven and capacity-constrained — the conditions the legacy heuristics handle worst.

| Pillar | Pain Point | Legacy Failure Mode (the Villain) | GB10-Powered Outcome | Evidence Basis |
|---|---|---|---|---|
| **Demand** | Lumpy, correlated component demand propagating up the BOM | Base-stock tuned to mean demand-over-lead-time; misfires on regime shifts | PPO conditions on full multi-echelon state and adapts order quantities per node | **[P]** core mechanism |
| **Capacity** | Finite line/plant throughput; bottlenecks under surge | Analytical heuristic assumes unconstrained replenishment; recommends infeasible orders when capped | Capacity-bounded PPO planning | **[P]** Env-2 tests bottleneck caps |
| **Routing & Logistics** | Multi-tier inbound + finished-goods distribution | Static lane/route rules | cuOpt GPU route optimization | **[C]** separate benchmark needed |
| **Costs** | Holding + ordering + backorder, jointly across echelons | Local per-tier optimization; a locally sensible move blows up a tier over | PPO minimizes *joint* discounted cost across the chain | **[P]** this is the paper's objective |

## 1.2 Retail

Retail is the closest real-world analog to the study's hard environment (Env-2): **seasonal demand, cross-node correlation, partial lost sales**. This is where the fixed baseline collapsed and PPO's measured gap reached 94.20%.

| Pillar | Pain Point | Legacy Failure Mode (the Villain) | GB10-Powered Outcome | Evidence Basis |
|---|---|---|---|---|
| **Demand** | Seasonality, promotions, demand correlated across stores | Static set-points never re-tuned to the live season | PPO tracks shifting profile and correlated movement across nodes | **[P]** Env-2 = seasonal + correlated |
| **Capacity** | DC / shelf / backroom limits | Reorder-point ignores capacity ceilings → over-orders | Capacity-aware PPO | **[P]** capacity-cap mechanism |
| **Routing & Logistics** | Replenishment cadence, last-mile, store clustering | Fixed delivery schedules | cuOpt dynamic routing | **[C]** not in this paper |
| **Costs** | Markdowns from overstock; lost-sales stockouts | Mean-tuned policy over- and under-shoots simultaneously | Joint cost min including lost-sales penalty | **[P]** Env-2 adds lost-sales penalty |

## 1.3 Wholesale & Logistics

The routing-and-capacity-heavy vertical. **Caution:** the routing value here rests on cuOpt, which this paper does *not* evaluate — present routing claims as a separate capability, not as backed by the 36–94% figures.

| Pillar | Pain Point | Legacy Failure Mode (the Villain) | GB10-Powered Outcome | Evidence Basis |
|---|---|---|---|---|
| **Demand** | Bullwhip-amplified, bursty B2B orders | Base-stock smooths to a mean the order stream rarely hits | PPO responds to live pipeline state | **[E]** plausible; not the paper's topology |
| **Capacity** | Warehouse throughput + fleet caps | Unconstrained heuristic orders what the network can't move | Capacity-bounded PPO | **[P]** cap mechanism |
| **Routing & Logistics** | Large-scale multi-stop, multi-lane optimization | Manual / static routing | **cuOpt** GPU route optimization — the core lever here | **[C]** headline capability, unquantified by this paper |
| **Costs** | Holding vs. transport trade-off | Tier-by-tier optimization misses the network trade-off | Network-wide joint cost min | **[P/E]** inventory side [P]; transport side [C] |

## 1.4 Hospitals

A "stockout" of a clinical supply is a **service-level / patient-safety failure**, not just a cost line. **Important honesty flag:** the paper's PPO environment does **not** measure service level (it reads "n/a"); the only service-level evidence in the paper is the A3C agent, which came out **slightly worse** than the heuristic on the hard environment. So we **cannot** claim a service-level win from this paper — service level must be validated separately before any hospital pitch.

| Pillar | Pain Point | Legacy Failure Mode (the Villain) | GB10-Powered Outcome | Evidence Basis |
|---|---|---|---|---|
| **Demand** | Census/case-mix driven, seasonal surges, low-volume critical items | Static par levels tuned to average census; blind to surges | PPO adapts par levels to live census + seasonal signal | **[E]** plausible; SL unproven |
| **Capacity** | Limited storage, perishables, cold-chain | Heuristic ignores expiry and storage caps | Constraint-aware PPO | **[P]** cap mechanism; **[E]** for expiry |
| **Routing & Logistics** | Intra-system distribution across sites/floors | Fixed par-restock rounds | cuOpt internal distribution | **[C]** not in this paper |
| **Costs** | Holding + critical-item stockout penalty | Mean-tuned policy under-protects against rare critical shortages | PPO weights shortage penalty as a first-class signal | **[P]** for cost; **service level NOT claimed** |

## 1.5 Cross-Industry Summary (Pitch Matrix)

One honest band, applied to **inventory cost only**, with fit and the biggest caveat surfaced per industry.

| Industry | Best-Fit GB10 Lever | Inventory-Cost Band (illustrative) | Strongest Caveat to Disclose |
|---|---|---|---|
| Manufacturing | PPO (inventory) + cuOpt (routing) | ~37% stable → up to ~94% under shock | Routing benefit (cuOpt) is unquantified by the paper |
| Retail | PPO — closest analog to Env-2 | ~37% stable → up to ~94% under shock | Upper bound is vs. a *never-re-tuned* baseline |
| Wholesale & Logistics | cuOpt (routing) + PPO (inventory) | Inventory side only; routing separate | Core routing value rests on cuOpt, not this paper |
| Hospitals | PPO (shortage-weighted) | ~37% stable → up to ~94% under shock | **No service-level win is supported; must be re-tested** |

---

# 2. Data Elements & Data Pipeline

## 2.1 Data Elements to Ingest

Mapped to the supply-chain pillars and to the model's state representation (the MDP state packs **on-hand inventory, in-transit pipeline, and backlog at every node**).

| Category | Specific Raw Elements | Pillar Served | Feeds (Model Component) |
|---|---|---|---|
| **Network topology** | Node list (suppliers, plants, DCs, warehouses, retailers/sites), echelon structure, lane/route graph | All | State-space definition |
| **Inventory state** | On-hand by SKU/node, in-transit pipeline, outstanding orders, backlog/backorders | Demand, Costs | MDP state vector |
| **Demand history** | Sales / POS / consumption transactions, order history, seasonality & promo calendars, patient census (hospitals) | Demand | Demand model + RAG context |
| **Lead times** | Per-lane lead-time history and variability/distributions | Capacity, Routing | Transition dynamics |
| **Capacity & constraints** | Supplier capacity caps, plant/line throughput, storage limits, vehicle/fleet capacity, expiry/cold-chain rules | Capacity | Action-space constraints |
| **Cost parameters** | Holding, ordering (fixed+variable), backorder/lost-sales/stockout penalty, transport cost | Costs | Cost signal |
| **Service targets** | Service-level / fill-rate targets, criticality tiers (esp. hospitals) | Costs, Demand | Objective weighting |
| **Routing data** | Lane distances/times, time windows, vehicle attributes | Routing & Logistics | cuOpt inputs |
| **Unstructured context** | Supplier contracts, SOPs, planner notes, product master/BOM docs | All | Vector DB / RAG corpus |

## 2.2 Conceptual Data Pipeline (On-GB10, Fully Local)

Per Pic 3, the customer plugs raw data into the GB10 appliance and the stack runs locally — **no data leaves the device** (the data-sovereignty selling point). The **128GB unified memory** lets the vector DB, local LLM, and RL engine share one address space, reducing CPU↔GPU copy overhead.

> **Capacity realism flag:** 128GB is generous for an appliance but *not* unlimited once a useful local LLM, a vector index, and an RL workload coexist. Model size, index footprint, and whether PPO is *trained* on-device vs. *served* (with periodic offline re-training) are real sizing constraints to resolve in the architecture iteration — not assume away.

```
[Customer Raw Data]
        |
        v
(1) Ingestion & Normalization  -->  structured into MDP state representation
        |                           (on-hand / in-transit / backlog per node)
        +-----------------------------------------------+
        v                                               v
(2) Vector DB (embeddings)                   (4) Empirical AI Modeling -- PPO
    unstructured docs, historical                 on Blackwell GPU via CUDA;
    patterns, contracts, SOPs                     cuOpt for routing (separate)
        |                                               |
        v                                               v
(3) LLM + RAG  <-- retrieves context -->      Policy outputs: per-echelon
    natural-language planner interface,        order quantities (+ routing
    scenario lookup, decision rationale        via cuOpt), adapted to live state
        +---------------------------->  [Optimized SCO Recommendations] <-------+
```

**Stage detail:**

1. **Ingestion & Normalization** — Raw client data is structured into the model's state representation (inventory position, pipeline, backlog per node, plus demand/lead-time/capacity/cost fields). Runs on the 20-core ARM CPU.
2. **Vector DB embedding** — Unstructured/historical context (supplier docs, SOPs, prior demand regimes) is embedded into a local vector database in unified memory — the institutional-memory layer.
3. **LLM + RAG** — A locally hosted LLM queries the vector DB to (a) give planners a natural-language interface, (b) retrieve analogous historical scenarios, and (c) produce human-readable rationale. The LLM **contextualizes**; it does **not** make the inventory decision.
4. **Empirical AI Modeling (PPO)** — The structured state feeds the **continuous-action PPO** engine on the Blackwell GPU via CUDA; **cuOpt** handles routing as a separate optimizer. PPO emits per-echelon order quantities as a continuous vector (not a coarse discretized grid) and adapts as dynamics shift. *Architectural scope only — reward signals, cost functions, and state-space matrices are deferred to a later iteration.*

---

## Scope Boundary & Honest Caveats (for the deck's appendix)

- **Continuous-action PPO is the recommended engine — and the discretization matters.** The paper's discrete-action A3C agent actually *lost* (−21.79%) on the hard environment. "RL" alone is not the answer; the continuous action head plus full-state conditioning carry the result. We standardize on PPO.
- **The ~94% is disruption-avoided cost vs. a never-re-tuned baseline, on a changed cost metric.** Against a re-tuned heuristic the paper says the margin would shrink substantially. Pitch resilience, not a flat savings figure.
- **Single-benchmark evidence.** All numbers come from one 1-warehouse/3-retailer environment at one seed. The paper's whole point is that this is not robust evidence — real per-industry validation is required before contractual ROI claims.
- **Known PPO risk to disclose proactively.** PPO showed a right-tail of high-cost shock episodes it had not learned to hedge. A risk-aware (e.g. CVaR-weighted) evaluation, and best-checkpoint selection to handle PPO's late-training instability, belong in the Point 3 scaffolding work.
- **Routing/cuOpt is unproven by this paper.** It is a real GB10 capability but needs its own benchmark; do not borrow the 36–94% figures for it.
- **Hospitals: no service-level claim is supported.** The only SL evidence in the paper is mildly negative (A3C). Validate before any clinical pitch.
- **Next iterations:** Point 3 (SCO scaffolding) and Point 4 (Synthetic Data Set) — not addressed here by design.
