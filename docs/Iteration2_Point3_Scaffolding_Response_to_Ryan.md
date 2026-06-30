# AI Jumpstart MVP — Response to Ryan (Iteration 2 / Point 3 Scaffolding)

**Prepared for:** Ryan Spurr | Helix, Connection Inc.
**From:** Ishan (AI Intern)
**Date:** 2026-06-29
**Scope of this doc:** Pic 4 **Point 3 — SCO scaffolding**, viewed from the **tools & models** layer, covering the three follow-up topics from the repo review: (1) the model/tool choices and their justification, (2) a web front-end vs. CLI, and (3) before/after scenario statistics. This is a *proposal to confirm*, not a built product. The matching execution plan is in [`docs/Iteration2_Plan_of_Action.md`](Iteration2_Plan_of_Action.md).

> **How to read this:** §0 is a 30-second summary. §1 covers the models (what, why, and fit). §2 covers the web front-end vs. CLI. §3 covers the before/after statistics. §4 covers how every tool gets containerized. §5 is the short list of decisions needed to start building.

---

## 0. TL;DR (the 30-second version)

- **Models:** Each pipeline stage gets a **specific, justified tool/model**, chosen against the one hardware fact that dominates everything: the GB10 is **compute-rich but memory-bandwidth-bound (~273 GB/s)**. So we keep the *learned policy tiny* (a small MLP PPO), push the *heavy combinatorial work to the GPU* (cuOpt), and use **a single shared Nemotron ~30B MoE at FP8** (Ryan-proven) reused across all language tasks. Nothing is oversized or duplicated "because we can."
- **Vertical:** **Manufacturing** is the confirmed build-first vertical (largest, most clients, core to manufacturing challenges).
- **Web front-end:** **Yes — we build a web UI** *and* a CLI, both **thin clients of an API-first, secure backend** (so future MCP / remote-execution reuses the same APIs). The web layer is how a planner *uses* the appliance; the CLI is how we *prove and re-run* it.
- **Before/after stats:** **Yes — a Scenario Comparison view** is the centerpiece of the UI: today's SCO metrics (baseline) vs. the optimized plan, with **+/- % deltas** per metric. Every number is computed from a **real on-device run** on seeded data — never a brochure figure.
- **Containerization:** **Every component is its own arm64 container**, wired together with **`docker compose` (Compose v2)**, GPU reserved where it's needed. The existing `Dockerfile` / `compose` scaffold grows into this.
- **Honest framing:** the % improvements shown in the UI are **whatever the benchmark actually produces** vs. the naive baseline. PPO still has to *earn its place* against a well-tuned classical solver — we are not asserting it wins.

---

## 1. The Scaffolding from a Tools & Models Perspective

This section takes the scaffolding past containers/OS/compute and into the actual models: what we'd use, why, and how each fits the use cases and the available infrastructure.

### 1.1 The one constraint that drives every model choice

Per the live device probe ([`docs/environment.md`](environment.md)) and the agent rules ([`.devin/rules/helix-sco.md`](../.devin/rules/helix-sco.md)): the GB10 is **121 GiB unified memory, ~273 GB/s bandwidth, 20× ARM aarch64 cores, Blackwell GPU, CUDA 13.0, driver 580.159.03**. The binding limit is **memory bandwidth, not capacity or compute**. That single fact is the lens for every model below:

- **Learned policy → keep it small.** Inventory-control policies are lightweight MLPs (the reference paper used a 2×64 MLP). A tiny policy is bandwidth-cheap and sits trivially in budget.
- **Combinatorial routing → push to the GPU.** This is where the Blackwell compute earns its keep (cuOpt).
- **LLM → one shared, right-sized MoE.** Token generation is the most bandwidth-hungry thing we'd run. We use a **single shared NVIDIA Nemotron ~30B (MoE) at FP8** (Ryan-proven on GB10), reused across every language task, instead of multiple or oversized models — keeping weights + KV-cache in budget.

### 1.2 The model/tool stack, layer by layer

Each row: the stage, the **proposed tool/model**, **why this one**, and **how it fits the use cases + GB10 infra**. (`[arm64-verify]` = must confirm an arm64/aarch64 build during build Week 1; this is a known schedule risk, especially cuOpt.)

| Pipeline stage | Proposed tool / model | Why this choice | Fit to use case + GB10 infra |
|---|---|---|---|
| **Ingest / normalize** | **GPU ingestion** (sentence-transformers / cuDF) for docs/images; Polars for small tabular | GPU ingestion of text/images/PDFs is 100×–1000× faster than CPU (Ryan's guidance); tabular SCO data is tiny | Structures raw client data + builds the RAG corpus on-GPU; tabular state stays cheap on CPU |
| **Forecasting (baseline)** | `statsforecast` (ETS/ARIMA) + Croston/SBA for intermittent | Seasonal statistical baseline first — explainable, near-zero memory, must be beaten before anything fancier | Retail seasonality, hospital intermittent critical items; pure-CPU, arm64-clean |
| **Forecasting (challenger)** | LightGBM (gradient-boosted) | Adds cross-series/feature learning *only if it earns it* vs. the statistical baseline | Manufacturing/retail with promo & calendar features; CPU, small footprint |
| **Forecasting (optional deep)** | `neuralforecast` (N-HiTS / TiDE) | Considered only if GBM under-performs on long seasonal horizons; small models | GPU-accelerated but intentionally small to respect bandwidth |
| **Inventory — baseline** | Reorder-point / base-stock (NumPy) | This is the **SOP's "villain" baseline we must beat** | All four verticals; trivial compute |
| **Inventory — strong classical** | Tuned (s,S) via simulation-optimization (Optuna) | The *honest* comparison — a well-tuned classical that does **not** collapse | Prevents over-claiming; this is the bar PPO must clear |
| **Inventory — learned candidate** | **Continuous-action PPO** via Stable-Baselines3 (PyTorch, CUDA 13) over a custom multi-echelon Gym env | Recommended learned candidate per the paper; tiny MLP policy → bandwidth-cheap | Non-stationary/shock-exposed demand is where it *may* win; reference code: `github.com/singhdivyank/multi-echelon-rl-inventory` |
| **Routing — baseline** | Shortest-route (OR-Tools / NetworkX) | The logistics half of the naive baseline to beat | All verticals; CPU |
| **Routing — strong classical** | **NVIDIA cuOpt** (GPU VRP/LP) `[arm64-verify]` | This is where Blackwell compute pays off; multi-tier inbound + finished-goods routing for Manufacturing | Multi-stop/multi-lane routing with caps + time windows; GPU-accelerated, pulled from NGC. Falls back to OR-Tools (CPU VRP) without blocking |
| **Vector DB** | **Qdrant** (fallback **LanceDB**, disk-based) | Self-hosted, on-device, no cloud — fits data-sovereignty; both Ryan-proven on GB10 | Embeds supplier docs / SOPs / planner notes for RAG; switch to LanceDB if in-memory footprint bites |
| **Embeddings** | **`nomic-embed-text-v1.5`** (768-dim) via sentence-transformers | Ryan-proven on GB10; small, strong retrieval embeddings | Powers RAG retrieval; runs on GPU, modest memory |
| **LLM (advisory/RAG + summaries)** | **single shared NVIDIA Nemotron ~30B (MoE), FP8** | Ryan-proven on GB10 (fast, strong on RAG); MoE + FP8 keep it in budget; **advisory only — it explains, it does not decide** | One model reused across all language tasks (rationale, summaries, UI text) to minimize weights + KV-cache |
| **Optimization orchestration** | FastAPI service (Python) | Single async surface that runs ingest→forecast→optimize→output and streams progress | Backend for both the CLI and the web UI |
| **Web API ↔ UI** | FastAPI (REST + SSE) ↔ React | Clean separation; SSE streams long run progress to the browser | See §2 |

### 1.3 Why this set fits the *use cases* (not just the hardware)

- **Manufacturing (the confirmed build-first vertical):** BOM-driven, capacity-constrained, lumpy + correlated component demand up the BOM — the **capacity-aware classical vs. learned** comparison matters, and multi-tier inbound + finished-goods distribution is a natural **cuOpt** lever. Forecasting leans on statistical + GBM with calendar/BOM features.
- **Retail / Wholesale (adjacent, later):** seasonal + bursty demand is also a strong fit for the **PPO vs. tuned-(s,S)** head-to-head and cuOpt routing.
- **Hospitals (adjacent, later):** intermittent critical items → **Croston/SBA**; we continue to make **no service-level win claim** (per the rules) until validated per site.

### 1.4 The honest reconciliation (carried forward from Iteration 1)

- **PPO is the recommended learned candidate, not a mandate.** It must beat the naive baseline **and** justify itself against the tuned classical solver on-device. In the source paper a *retuned (s,S) beat A3C on the harder environment* — we will not pretend otherwise.
- The paper's **~37%–94%** figures are **reference points for the kickoff target margin only** — the ~94% is largely baseline-collapse on a rescaled metric vs. an un-tuned baseline, never a flat steady-state saving.
- **cuOpt is not preinstalled** and its arm64 build must be verified early (schedule risk); fall back to OR-Tools (CPU VRP) without blocking. The LLM/embeddings/vector-DB stack is Ryan-proven on GB10.

---

## 2. Web Front-End vs. CLI

**Yes — we build a web front-end *and* a CLI — but the real point is the layer beneath both: an API-first, secure backend.** Per the directive, **every major feature is a secure API**; the CLI, the web UI, and future **MCP / remote-execution** are all just clients of the *same* APIs (no per-interface logic). The two front-ends serve different masters:

| Layer | Audience | Purpose |
|---|---|---|
| **Web UI** | The planner / the demo audience / a customer | Configure a scenario, run it, *see* the before/after result and rationale |
| **CLI / one-command runner** | Us (engineering) + the SOP's reproducibility requirement | `make run` regenerates seeded data and produces a plan end-to-end, on-device, re-runnably |

**Proposed web stack (all arm64-containerized):**

- **Frontend:** React + Vite + TypeScript, TailwindCSS, shadcn/ui, Lucide icons, **Recharts/Tremor** for the metric dashboards.
- **Backend:** **FastAPI** (async) exposing REST + **SSE** (live run progress), orchestrating the ingest→forecast→optimize→output pipeline and the optimizer/LLM/vector-DB services.
- **Why this stack:** it's the modern, well-supported default; it containerizes cleanly on arm64; and FastAPI lets the *same* Python pipeline power the API that the CLI and web both consume (no duplicate logic).
- **API-first & secure:** real authN/authZ, input validation, and secrets handling — **not just app-level security** — so the same APIs can safely back MCP/remote execution later.

**Important:** the web UI is a *thin* interface over the real engine — it does not become the product's brain. The optimization decisions still come from the modeling layer in §1; the UI presents them.

---

## 3. Before/After Scenario Statistics in the UI

**Yes — this is the centerpiece of the UI.** The main screen is a **Scenario Comparison** that puts today's SCO metrics next to the proposed optimized outcome with signed % improvements:

```
┌──────────────────────────────────────────────────────────────────────┐
│  Scenario: "Plant + 4 suppliers — component-shortage shock"  [ Run ▶ ] │
├───────────────────────────────┬──────────────────────────────────────┤
│  BEFORE (today's SCO)         │  AFTER (proposed optimized plan)       │
│  — naive baseline             │  — classical / PPO (best on-device)    │
├───────────────────────────────┼──────────────────────────────────────┤
│  Total cost        $X         │  $Y            ▼ XX.X%   (green)       │
│  Holding cost      $…         │  $…            ▼ …                      │
│  Stockouts / fill  …%         │  …%            ▲ +X.X pts              │
│  Transport cost    $…         │  $…            ▼ …                      │
│  Inventory (days)  …          │  …             ▼ …                      │
├───────────────────────────────┴──────────────────────────────────────┤
│  On-device: peak mem … GB | bandwidth … GB/s | solve time … s | GPU%  │
│  Rationale (LLM/RAG, advisory): "Plan shifts safety stock toward …"    │
└──────────────────────────────────────────────────────────────────────┘
```

**What "before" and "after" mean concretely:**

- **Before** = the **naive baseline** (reorder-point + shortest-route) run on the same seeded scenario — i.e., "what today's typical SCO setup produces."
- **After** = the **optimized plan** (the best of tuned-classical / PPO, decided by the benchmark) on the *same* data.
- **Delta** = `(after − before) / before`, shown per metric with direction + color (cost down = good/green; fill-rate up = good/green).

**Metrics shown:** total cost, holding cost, ordering cost, backorder/lost-sales, transport cost, fill-rate / service level, days-of-inventory — plus the **on-device panel** (peak unified memory, sustained bandwidth, solve/inference latency, GPU vs CPU util) so the "runs at the desk" story is visible, not just claimed.

**Integrity guardrails (important):**

- Every number is produced by an **actual run on-device** against seeded, documented data — **no hard-coded or brochure percentages** in the UI.
- The comparison is **baseline vs. optimized on identical inputs**, so the delta is honest.
- The LLM rationale panel is clearly labeled **advisory** — it explains the plan, it does not generate the numbers.
- Target margins remain **set at kickoff**; the UI reports the *realized* delta, whatever it is.

---

## 4. Containerization Posture

In line with the directive to containerize everything that gets built, the architecture is **multi-container from day one**, all **arm64**, GPU reserved only where needed. The current `Dockerfile` + `docker-compose.yml` scaffold (already verified to see the GB10 GPU — see [`docs/containerization.md`](containerization.md)) grows into:

| Service | Image basis | GPU? | Role |
|---|---|---|---|
| `web` | node-build → nginx (arm64) | no | Serves the React UI |
| `api` | CUDA 13 runtime + Python (arm64) | yes | FastAPI: pipeline + forecasting + PPO inference + orchestration |
| `cuopt` | NVIDIA cuOpt (NGC) `[arm64-verify]` | yes | GPU routing/LP solver (fallback OR-Tools, CPU) |
| `llm` | **NVIDIA Nemotron ~30B (MoE) FP8** | yes | Single shared LLM for all language tasks |
| `vectordb` | Qdrant (fallback LanceDB) | no | RAG vector store |

All wired by **`docker compose` (Compose v2)**, GPU via `deploy.resources.reservations.devices` (already stubbed). One-command bring-up is the goal. Full build sequence is in the Plan of Action.

---

## 5. Confirmed Decisions (Ryan, 2026-06-30)

The items previously open are now decided; the build proceeds without blocking:

| # | Decision | Confirmed |
|---|---|---|
| 1 | **Vertical** | **Manufacturing** (largest, most clients, core to manufacturing challenges) |
| 2 | **Target-margin framing** | **% improvement vs. baseline** (clients want a number) **+ resilience under worst-case shock** (war/COVID/inflation) — both from real runs |
| 3 | **Product shape** | **Dev / Proof-of-Concept**, not production; stand up fast on GB10, scale to Helix DC later — do not over-harden |
| 4 | **LLM** | **NVIDIA Nemotron ~30B (MoE) FP8**, single shared model; Nemotron Ultra for production on dual-H100+ |
| 5 | **Embeddings / Vector DB** | **nomic-embed-text-v1.5** (768-dim) + **Qdrant** (fallback LanceDB) |
| 6 | **Licensing** | NVAIE not needed for dev; **NFR NVAIE** available if gated |
| 7 | **Interfaces** | **API-first**: web + CLI (+ future MCP) all consume the same secure APIs |
| 8 | **Tooling** | **Docker Compose v2**; **GPU-accelerated ingestion** |

The build follows [`docs/Iteration2_Plan_of_Action.md`](Iteration2_Plan_of_Action.md).

---

### Appendix — Carried-forward caveats (unchanged guardrails)

- PPO is recommended, **not** categorically superior; it earns its place vs. a tuned classical solver.
- The ~94% figure is baseline-collapse + rescaled metric vs. an un-tuned baseline — never shown as flat savings.
- Memory **bandwidth (~273 GB/s)** is the binding constraint, not the 128 GB capacity.
- cuOpt is not preinstalled — **verify arm64 early** (schedule risk); fall back to OR-Tools (CPU VRP) without blocking.
- **No hospital service-level win** is claimed until validated per site.
- Customer data **stays on-device** — nothing in this design ships data off-box.
