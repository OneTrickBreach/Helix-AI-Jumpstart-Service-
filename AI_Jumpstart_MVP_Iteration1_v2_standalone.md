# AI Jumpstart MVP on NVIDIA GB10 — Iteration 1 (v2, Standalone)

**Prepared for:** Ryan | Helix, Connection Inc.
**Scope:** Pic 4, Points 1 & 2 only (Use Cases & Value Proposition; Data Elements & Data Pipeline)
**Deferred:** Point 3 (SCO scaffolding), Point 4 (Synthetic Data Set)
**Evidence basis:** Public industry research (McKinsey, Gartner, Deloitte, BCG) and the peer-reviewed RL-for-inventory literature. *This version intentionally cites no internal or confidential material; every figure is externally referenceable.*

> **How to read the numbers.** The percentages below are **published industry benchmark ranges**, not Helix measurements. Where an organization lands inside a range depends heavily on data quality and integration maturity — McKinsey/Deloitte note most firms reach satisfactory ROI in roughly **2–4 years**, not months. Use these to size the *opportunity*; actual ROI must be validated per customer.

---

## Executive Thesis

Classical Operations Research inventory heuristics — **echelon base-stock** and **(s, S) reorder-point** — are provably optimal **only under strict stationarity** (the Clark–Scarf result). Their set-points are derived from average demand-over-lead-time, so when demand becomes seasonal, correlated, or shock-prone, and when lead times grow variable, those set-points are aimed at a target that no longer exists. The well-documented result is *simultaneous* overstock and stockout — the classic failure operations leaders already recognize.

Modern spreadsheet- and reorder-point-based planning typically runs **20–30% forecast error**; AI/RL-based planning that conditions on the live system state rather than a static set-point closes much of that gap. Two honest framings keep this credible:

- **The opportunity is real and quantified.** Independent research (McKinsey) attributes **20–30% inventory reduction, 5–20% logistics-cost reduction, and 5–15% procurement-spend reduction** to AI embedded in distribution operations, plus **20–50% forecast-error reduction** and up to **65% fewer stockouts** from AI demand forecasting.
- **RL is not a magic wand.** The peer-reviewed literature is explicit that generic deep-RL does **not** universally beat well-tuned heuristics — gains concentrate in **non-stationary, high-dimensional, constraint-heavy** problems, which is exactly where legacy set-points break and where the GB10's local compute pays off.

**The value proposition:** a learned policy (we recommend **continuous-action PPO**) conditions on the full state — on-hand, in-transit pipeline, backlog at every node — and adapts as conditions shift; the static heuristic cannot. The GB10 packages this as a single secure on-premise appliance.

---

## Published ROI Benchmarks (the anchor table)

| Lever | Benchmark Range | Source (public) |
|---|---|---|
| Inventory reduction (AI in distribution ops) | **20–30%** | McKinsey |
| Inventory holding-cost reduction | **20–30%** | Gartner |
| Logistics-cost reduction | **5–20%** | McKinsey |
| Procurement-spend reduction | **5–15%** | McKinsey |
| Demand-forecast error reduction | **20–50%** | McKinsey |
| Stockout reduction | **up to ~65%** | McKinsey |
| Forecast accuracy in volatile markets | **85–95%** (vs. 60–70% traditional) | Gartner |
| Lead-time reduction (transport AI) | **~25%** | BCG |
| Days-of-inventory reduction (AI replenishment) | **~35%** | McKinsey |

> Ranges are broad by design; placement depends on data maturity and how well models integrate with existing WMS/planning systems.

---

# 1. Use Cases & Value Proposition

Each matrix maps the four supply-chain pillars to the legacy failure mode and the GB10-powered outcome. The headline range per industry is drawn from the anchor table above; it is an opportunity sizing, not a guarantee.

## 1.1 Manufacturing — *headline opportunity: 20–30% inventory, 5–15% procurement*

Inventory is a major share of a manufacturer's working capital, and the environment is BOM-driven and capacity-constrained — the conditions static set-points handle worst.

| Pillar | Pain Point | Legacy Failure Mode (the Villain) | GB10-Powered Outcome |
|---|---|---|---|
| **Demand** | Lumpy, correlated component demand propagating up the BOM | Base-stock tuned to mean demand-over-lead-time; misfires on regime shifts | PPO conditions on full multi-echelon state; adapts order quantities per node |
| **Capacity** | Finite line/plant throughput; surge bottlenecks | Analytical heuristic assumes unconstrained replenishment; recommends infeasible orders | Capacity-bounded PPO planning within hard caps |
| **Routing & Logistics** | Multi-tier inbound + finished-goods distribution | Static lane/route rules | cuOpt GPU route optimization (logistics-cost lever: 5–20%) |
| **Costs** | Holding + ordering + backorder, jointly across echelons | Local per-tier optimization; locally sensible decisions blow up a tier over | PPO minimizes joint discounted cost across the chain |

## 1.2 Retail — *headline opportunity: 20–50% forecast-error cut, up to 65% fewer stockouts*

Retail's seasonality, promotions, and cross-store correlation are precisely the non-stationary conditions where AI forecasting and adaptive replenishment show the largest published gains, and where SKU proliferation has outrun spreadsheet planning.

| Pillar | Pain Point | Legacy Failure Mode (the Villain) | GB10-Powered Outcome |
|---|---|---|---|
| **Demand** | Seasonality, promotions, demand correlated across stores | Static set-points never re-aligned to the live season | PPO tracks shifting profile and correlated movement across nodes |
| **Capacity** | DC / shelf / backroom limits | Reorder-point ignores capacity ceilings → over-orders | Capacity-aware PPO allocation |
| **Routing & Logistics** | Replenishment cadence, last-mile, store clustering | Fixed delivery schedules unresponsive to swings | cuOpt dynamic routing and replenishment timing |
| **Costs** | Markdowns from overstock; lost-sales stockouts | Mean-tuned policy over- and under-shoots simultaneously | Joint cost minimization including lost-sales penalty |

## 1.3 Wholesale & Logistics — *headline opportunity: 5–20% logistics cost, ~25% lead-time*

The routing-and-capacity-heavy vertical, where the cuOpt route-optimization capability is the headline lever alongside inventory policy.

| Pillar | Pain Point | Legacy Failure Mode (the Villain) | GB10-Powered Outcome |
|---|---|---|---|
| **Demand** | Bullwhip-amplified, bursty B2B order patterns | Base-stock smooths to a mean the order stream rarely hits | PPO responds to live pipeline state; dampens bullwhip |
| **Capacity** | Warehouse throughput + fleet capacity caps | Unconstrained heuristic orders what the network can't move | Capacity-bounded PPO planning |
| **Routing & Logistics** | Large-scale multi-stop, multi-lane optimization | Manual / static routing; cannot re-solve at scale | **cuOpt** GPU route optimization — the core lever here |
| **Costs** | Holding vs. transport trade-off | Tier-by-tier optimization misses the network trade-off | Network-wide joint cost minimization |

## 1.4 Hospitals — *headline opportunity: stockout + waste reduction; service level the priority metric*

A stockout of a clinical supply is a **service-level / patient-safety** failure, not just a cost line. The priority outcome here is service level and waste reduction, with cost secondary. **Honesty flag:** service-level gains from RL are problem-specific and must be validated per site before any clinical commitment — the literature shows RL service-level wins are real but not automatic.

| Pillar | Pain Point | Legacy Failure Mode (the Villain) | GB10-Powered Outcome |
|---|---|---|---|
| **Demand** | Census/case-mix driven, seasonal surges, low-volume critical items | Static par levels tuned to average census; blind to surges | PPO adapts par levels to live census + seasonal signal |
| **Capacity** | Limited storage, perishables, cold-chain | Heuristic ignores expiry and storage caps | Constraint-aware PPO reduces waste and expiry |
| **Routing & Logistics** | Intra-system distribution across sites/floors | Fixed par-restock rounds | cuOpt-optimized internal distribution |
| **Costs** | Holding + critical-item stockout (safety) penalty | Mean-tuned policy under-protects against rare critical shortages | PPO weights shortage penalty as a first-class signal |

## 1.5 Cross-Industry Summary (Pitch Matrix)

| Industry | Best-Fit GB10 Lever | Primary Published Benchmark | Strongest Caveat to Disclose |
|---|---|---|---|
| Manufacturing | PPO (inventory) + cuOpt (routing) | 20–30% inventory; 5–15% procurement | Gains depend on data/WMS integration maturity |
| Retail | PPO (best fit for seasonal/correlated demand) | 20–50% forecast-error cut; up to 65% fewer stockouts | SKU/data readiness is the gating factor |
| Wholesale & Logistics | cuOpt (routing) + PPO (inventory) | 5–20% logistics cost; ~25% lead-time | Routing value scales with network size/complexity |
| Hospitals | PPO (shortage-weighted) | Stockout + waste reduction | Service-level gains must be validated per site |

---

# 2. Data Elements & Data Pipeline

## 2.1 Data Elements to Ingest

| Category | Specific Raw Elements | Pillar Served | Feeds (Model Component) |
|---|---|---|---|
| **Network topology** | Node list (suppliers, plants, DCs, warehouses, retailers/sites), echelon structure, lane/route graph | All | State-space definition |
| **Inventory state** | On-hand by SKU/node, in-transit pipeline, outstanding orders, backlog/backorders | Demand, Costs | Policy state vector |
| **Demand history** | Sales / POS / consumption transactions, order history, seasonality & promo calendars, patient census (hospitals) | Demand | Demand model + RAG context |
| **Lead times** | Per-lane lead-time history and variability/distributions | Capacity, Routing | Transition dynamics |
| **Capacity & constraints** | Supplier capacity caps, plant/line throughput, storage limits, vehicle/fleet capacity, expiry/cold-chain rules | Capacity | Action-space constraints |
| **Cost parameters** | Holding, ordering (fixed+variable), backorder/lost-sales/stockout penalty, transport cost | Costs | Cost/objective signal |
| **Service targets** | Service-level / fill-rate targets, criticality tiers (esp. hospitals) | Costs, Demand | Objective weighting |
| **Routing data** | Lane distances/times, time windows, vehicle attributes | Routing & Logistics | cuOpt inputs |
| **Unstructured context** | Supplier contracts, SOPs, planner notes, product master/BOM docs | All | Vector DB / RAG corpus |

## 2.2 Conceptual Data Pipeline (On-GB10, Fully Local)

Per Pic 3, the customer plugs raw data into the GB10 appliance and the stack runs locally — **no data leaves the device** (the data-sovereignty selling point). The **128GB unified memory** lets the vector DB, local LLM, and RL engine share one address space, reducing CPU↔GPU copy overhead.

> **Capacity realism flag:** 128GB is generous for an appliance but not unlimited once a useful local LLM, a vector index, and an RL workload coexist. Model size, index footprint, and whether PPO is *trained* on-device vs. *served* (with periodic offline re-training) are sizing constraints to resolve in the architecture iteration.

```
[Customer Raw Data]
        |
        v
(1) Ingestion & Normalization  -->  structured state representation
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

1. **Ingestion & Normalization** — Raw client data is structured into the policy's state representation (inventory position, pipeline, backlog per node, plus demand/lead-time/capacity/cost fields). Runs on the 20-core ARM CPU.
2. **Vector DB embedding** — Unstructured/historical context (supplier docs, SOPs, prior demand regimes) is embedded into a local vector database in unified memory — the institutional-memory layer.
3. **LLM + RAG** — A locally hosted LLM queries the vector DB to (a) give planners a natural-language interface, (b) retrieve analogous historical scenarios, and (c) produce human-readable rationale. The LLM **contextualizes**; it does **not** make the inventory decision.
4. **Empirical AI Modeling (PPO)** — The structured state feeds the **continuous-action PPO** engine on the Blackwell GPU via CUDA; **cuOpt** handles routing as a separate optimizer. PPO emits per-echelon order quantities as a continuous vector (not a coarse discretized grid) and adapts as dynamics shift. *Architectural scope only — reward signals, cost functions, and state-space matrices are deferred to a later iteration.*

---

## Scope Boundary & Honest Caveats (appendix)

- **Continuous-action PPO is the recommended engine.** Published work shows PPO with continuous action spaces performs well on seasonal-demand and service-level objectives; coarse discretized action spaces underperform under smoothly shifting demand.
- **RL is not a guaranteed win.** Generic deep-RL does not universally beat well-tuned heuristics; the advantage concentrates in non-stationary, high-dimensional, constrained problems. Implementation maturity matters.
- **Benchmarks are industry ranges, not Helix results.** Most organizations realize ROI over 2–4 years; placement in each range depends on data quality and WMS/planning integration. Validate per customer.
- **Routing (cuOpt) is a distinct capability** from inventory policy and should be benchmarked on its own.
- **Hospitals: service-level gains require per-site validation** before any clinical commitment.
- **Next iterations:** Point 3 (SCO scaffolding) and Point 4 (Synthetic Data Set) — not addressed here by design.
