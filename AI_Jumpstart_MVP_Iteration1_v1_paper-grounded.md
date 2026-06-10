# AI Jumpstart MVP on NVIDIA GB10 — Iteration 1 (v1, Paper-Grounded · SOP-Aligned)

**Prepared for:** Ryan | Helix, Connection Inc.
**Scope:** Pic 4, Points 1 & 2 (Use Cases & Value Proposition; Data Elements & Data Pipeline), fine-tuned to Ryan's prototype SOP and the Dell Pro Max GB10 hardware spec.
**Empirical basis:** *Robustness of Policy-Gradient RL for Multi-Echelon Inventory Control* (PPO vs. fixed analytical base-stock; A3C vs. tuned (s,S)).

> **Evidence integrity note.** This version cites the RL paper. The paper reports two PPO results — aggregate inventory-cost improvement of **+36.76%** (stationary) and **+94.20%** (non-stationary) — on **one** small benchmark (1 warehouse, 3 retailers), **one** seed, **inventory only** (no routing/cuOpt). Its own thesis is that single-environment, single-seed wins are *not* robust evidence. Treat its numbers as **reference points for the kickoff target margin**, not committed prototype results. (Also a *confidential reviewer copy* — keep this version internal.)

---

## Alignment to Ryan's Prototype SOP

This deliverable serves the prototype objective: **an end-to-end SCO prototype running entirely on a GB10-class device, from synthetic data to an optimized plan.**

- **On-device is a success condition.** The whole pipeline must run inside the confirmed **128 GB unified LPDDR5X** envelope (see Hardware below); peak memory, memory-bandwidth pressure, and solve/inference time are recorded. Narrative: *a workload that used to need a rack now runs at the desk — literally a 1.31 kg, ~240 W unit.*
- **Depth over breadth.** One company, one product family / small SKU set, a handful of locations — see §1.6.
- **All four dimensions:** demand, inventory, multi-location, transportation/logistics.
- **Beat a naive baseline by a margin set at kickoff.** Baseline = **reorder-point (inventory) + shortest-route (logistics)**.
- **Propose, don't prescribe** the modeling (§2.3). PPO is the recommended learned candidate, benchmarked head-to-head against a strong classical solver.
- **Reproducible & re-runnable** — seeded/documented synthetic data; ideally one command.
- **3-week phasing** (§3) with a short written + verbal handoff.

---

## Confirmed Hardware (per Ryan's Dell Pro Max with GB10 spec, Jun 2026)

The prototype targets the **Dell Pro Max with GB10** — Dell's OEM build of the NVIDIA GB10 Grace Blackwell platform (internal sibling of the DGX Spark). Identical units ship from **Lenovo, HP, Asus, and Acer**, so the packaged solution is **not Dell-locked**.

| Spec | Value | Why it matters here |
|---|---|---|
| SoC | GB10 Grace Blackwell (TSMC 3nm) | Fixed, unified CPU+GPU compute |
| CPU | 20-core Arm v9.2 (10× X925 + 10× A725) | ARM64 toolchain target (Week 1) |
| GPU | Blackwell, 6,144 CUDA cores, 5th-gen Tensor | cuOpt + PPO acceleration |
| AI compute | up to 1 PFLOP sparse FP4 (~1,000 TOPS) | Compute-rich |
| **Memory** | **128 GB LPDDR5X unified, ~273 GB/s (256-bit)** | **Budget *and* the real bottleneck — see flag** |
| CPU–GPU link | NVLink-C2C (~5× PCIe Gen5) | Cheap CPU↔GPU handoff across the pipeline |
| Networking | ConnectX-7: 2× 200 GbE QSFP + 10 GbE RJ45 | Enables 2-node clustering |
| Storage | up to 4 TB NVMe (Gen4), SED-encrypted | Dataset + model cache; data stays on-device |
| Local models | inference ≤ ~200B params; fine-tune ≤ ~70B (single node) | Sizes the local RAG LLM |
| Form / power | 150×150×51 mm, ~1.31 kg, ~240 W USB-C | The literal "rack → desk" story |
| Software | DGX OS 7 (Ubuntu 24.04), CUDA 13.x, PyTorch / RAPIDS / TensorRT-LLM via NGC, NIM | Week-1 toolchain (confirm with `nvcc --version`, `nvidia-smi`) |

**Clustering (maps to the whiteboard's "2× GB10").** Two units bond over a single 200G QSFP56 DAC cable — point-to-point RoCE/RDMA, NCCL collectives, NVIDIA Sync "Cluster Assistant" — into one logical node: **256 GB pooled memory, up to 8 TB storage, models up to ~400B params.** NVIDIA officially supports **2 nodes** over the direct cable; **3+ requires a 200/400 GbE switch.** This is our Week-3 headroom for stressing larger scenarios.

> **Bandwidth honesty flag (important).** The device is **compute-rich but bandwidth-modest**: ~273 GB/s unified-memory bandwidth is the limiter, not the 1 PFLOP figure or the 128 GB capacity. Memory-bandwidth-bound work (large-LLM token generation, big RL batches) feels this first. Good news for *our* workload: the RL **policy network is tiny** — the reference PPO used a 2×64 MLP — so it sits trivially within budget. The real memory/bandwidth pressure is the **local LLM + vector index**; right-size the NIM-served LLM accordingly.

---

## Target-Margin Reference (set the actual target at kickoff)

Per SOP, the win margin is agreed at kickoff. These reference points inform that conversation — not the committed number:

| Reference (inventory cost vs. fixed legacy baseline) | Value | Caveat |
|---|---|---|
| Stationary demand | ~37% (paper Env-1) | Single toy environment, single seed |
| Non-stationary / shock-exposed | up to ~94% (paper Env-2) | Mostly *baseline collapse* vs. an un-tuned baseline; partly a rescaled metric |

> **Pitch discipline.** Against the SOP's naive reorder-point + shortest-route baseline a meaningful win is plausible; against a *re-tuned* classical solver the margin shrinks substantially (the paper says so). Set a conservative kickoff target (resilience under shock, not a flat headline %); let the on-device benchmark report the real number.

---

# 1. Use Cases & Value Proposition (Opportunity Map)

The four target industries are the market landscape. The 3-week prototype builds **one** in depth (§1.6). Final column: evidence basis — **[P]** paper-grounded (inventory), **[E]** plausible extrapolation, **[C]** cuOpt capability not evaluated by the paper.

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
| **Example company** | One mid-market distributor/retailer of a single product family |
| **SKU set** | One product family / small SKU set (~5–20 SKUs) |
| **Locations** | A handful — e.g., 1 supplier/DC → 3–5 regional stores/sites |
| **Demand** | Seasonal + noisy history (closest analog to the paper's hard environment) |
| **Inventory** | Multi-echelon positions: on-hand, in-transit, backlog per node |
| **Multi-location** | Allocation across DC + sites |
| **Transportation/logistics** | Lanes between nodes with lead times, capacity, and cost |

> A retail/distribution example exercises **all four dimensions** cleanly, and its seasonal, correlated demand is where the learned-policy story is strongest. This single-node scope sits comfortably inside 128 GB; the 2-node cluster is reserved for Week-3 scale stress. Final pick is set at kickoff (Week 1).

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
        +--> (2) Vector DB (embeddings) <--retrieves--> (3) NIM-served local LLM + RAG  [planner Q&A + rationale]
        |
        v
(4) Forecast  --> demand signal (method TBD, §2.3)                                        [CPU / GPU]
        |
        v
(5) Optimize across 4 dimensions: demand • inventory • multi-location • transport         [Blackwell GPU]
        |   - Naive baseline: reorder-point + shortest-route  (target to beat)
        |   - Strong classical: MILP / cuOpt + tuned base-stock
        |   - Learned candidate: continuous-action PPO
        v
[Optimized Plan]  +  [Recorded: peak unified-memory, memory-bandwidth use, solve/inference latency, GPU vs CPU util]
```

- **Vector DB + LLM + RAG** give planners a natural-language interface and decision rationale; they **contextualize**, they do **not** make the inventory/routing decision. The LLM is **NIM-served** and right-sized to leave bandwidth headroom.
- The chain targets a **single re-runnable command** within the **128 GB** budget; NVLink-C2C keeps CPU↔GPU handoffs cheap.

## 2.3 Scaffolding Options to Confirm at Kickoff (propose, don't prescribe)

| Decision | Candidate options | Recommended starting point |
|---|---|---|
| **Forecasting** | Statistical (ETS/ARIMA, Croston for intermittent) · ML (gradient-boosted) · deep (temporal) | Seasonal statistical baseline first; add ML if it earns it |
| **Inventory optimization** | Reorder-point / base-stock (baseline) · tuned (s,S) (classical) · **PPO** (learned) | PPO as learned candidate vs. tuned base-stock |
| **Routing/transport** | Shortest-route (baseline) · MILP / **cuOpt** (classical) · learned | cuOpt for routing |
| **Classical vs. learned** | Run both; decide on cost/service **and** on-device latency/memory | Benchmark head-to-head |

> **Toolchain note:** CUDA 13.x, PyTorch, RAPIDS, and TensorRT-LLM are preinstalled via the DGX/NGC stack. **cuOpt is *not* in the preinstalled list** — pull it from NGC and verify on-device early in Week 1. This is the honest reconciliation of "don't prescribe" with the PPO lead: PPO must **beat the naive baseline** *and* **justify itself against a strong classical solver** on-device — including the paper's known PPO shock-tail risk (a Week-3 stress target).

---

# 3. Measurable Outcomes & Phased Plan

## 3.1 Success Metrics (set target values at kickoff)

| Outcome | Metric | Target |
|---|---|---|
| On-device feasibility | Peak unified-memory fits in **128 GB** (single node) with headroom | _set at kickoff_ |
| Memory bandwidth | Sustained vs. ~273 GB/s ceiling; flag bandwidth-bound stages | recorded |
| Speed | Solve/inference latency per plan | _set at kickoff_ |
| Hardware story | GPU vs CPU utilization; where Blackwell actually helps | documented |
| Scale headroom | Largest scenario on 1 node; demonstrate 2-node **256 GB** cluster if exceeded | recorded |
| Quality | % cost reduction **or** service-level gain vs. reorder-point + shortest-route | _X% set at kickoff_ |
| Reproducibility | Seeded dataset; documented | yes/no |
| Re-runnability | End-to-end, ideally one command | yes/no |
| Handoff | Short written + verbal | delivered |

## 3.2 Three-Week Plan (accelerated)

| Week | Focus | Checkpoint |
|---|---|---|
| **1** | Scope, data, environment — pin company/decision/metrics; generate seeded synthetic data; stand up the unit and confirm the **ARM64 toolchain** (DGX OS 7 / Ubuntu 24.04, CUDA 13.x, PyTorch via NGC; pull & verify **cuOpt** from NGC) | Data + baseline heuristic in place |
| **2** | Pipelines + optimization — build ingest→forecast→optimize→output; implement all four dimensions; first full run, then iterate | End-to-end run beating baseline on ≥1 metric |
| **3** | Benchmark, harden, hand off — on-device benchmark (memory, **bandwidth**, latency, GPU vs CPU); stress larger scenarios, escalating to the **2-node 256 GB cluster** to find limits; document; present | Final demo + writeup |

---

## Appendix — Honest Caveats

- **PPO is the recommended learned candidate, not a mandate** — per SOP, classical vs. learned is decided on evidence.
- **The ~94% reference is vs. an un-tuned baseline on a rescaled metric** — pitch resilience, set a conservative kickoff target.
- **Single-benchmark evidence; validate per scenario** (the paper's own thesis).
- **Known PPO shock-tail risk** → Week-3 stress target; consider risk-aware (CVaR) evaluation in Point 3 scaffolding.
- **Routing/cuOpt unproven by the paper** *and* not preinstalled — benchmark separately, pull from NGC.
- **Hospitals: no service-level win supported by the paper** — validate per site.
- **The binding constraint is memory *bandwidth* (~273 GB/s), not capacity.** The RL policy is tiny; the local LLM + vector index drive sizing. The 2-node cluster (256 GB) is the escape hatch for scale, up to 2 nodes before a switch is required.
- **Deferred:** Point 3 (full SCO scaffolding) and Point 4 (full dataset spec) beyond the kickoff-level proposals above.