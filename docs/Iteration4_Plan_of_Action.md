# Iteration 4 — Plan of Action: Dataset Transparency Layer

**Prepared for:** Ryan Spurr | Helix, Connection Inc.
**From:** Ishan (AI Intern)
**Authority:** Ryan delegated a full free hand ("proceed unless you have issues"). Scope and technical
calls below are made by Ishan and documented here; Ryan is informed, not gating.
**Predecessor:** Iteration 3 (demo/pilot-ready) — built, verified on-device, merged to `main` 2026-07-27;
demoed live to Ryan 2026-07-29 over Tailscale.
**Origin:** Ryan's demo feedback, ask #1 — *"the site shows results, but there's no idea of the dataset
it ran on. Give people a way to see it, so clearly that a child could look at it and go 'ohh, that's my
dataset.'"*
**Objective:** make the **input side** of the pipeline as visible, legible, and trustworthy as the output
side already is — without adding a single fabricated number.

> **Ryan's sequencing instruction:** baby steps. Ship this, show him, get feedback, *then* start
> Iteration 5 (the conversational what-if layer). This plan is scoped to stop cleanly at that review.

---

## 0. Read-First: what Iteration 4 is and is NOT

**IS:** a read-only, deterministic **"Know Your Data"** view — derived live from the actual generated
files on disk, rendered so a non-technical viewer understands the network, the products, the demand, the
lanes, the costs, and *what makes this scenario different* inside two minutes.

**IS NOT:**
- Not the chatbot / what-if engine → that is **Iteration 5** (separate plan, starts after Ryan's review).
- Not real customer-data onboarding / ETL → that is **Iteration 6** (the old "Iteration 4 = production"
  track, renumbered; see §5).
- Not new optimizer, forecast, or RL work. Results, winners, and objectives are untouched this iteration.
- Not an LLM feature. **The dataset view contains zero LLM-generated text** (see §1, decision 4).

### 🔴 Roadmap renumbering (do this first — Phase 0)
Ryan's two asks displace the production track. The roadmap is now:

| Iteration | Content | State |
|---|---|---|
| 1 | Use cases / value prop; data elements & pipeline | ✅ Done |
| 2 | SCO scaffolding + synthetic dataset (working on-device prototype) | ✅ Done (`main`, 2026-07-10) |
| 3 | Productization, demo polish, honest RL fair-shot | ✅ Done (`main`, 2026-07-27) |
| **4** | **Dataset transparency layer (this plan)** | 🎯 **Starting now** |
| 5 | Conversational scenario/what-if analyst (Ryan ask #2) | 📝 Planned, directional |
| 6 | Production / GA: real customer-data onboarding, hardening, multi-vertical, commercial wrap | ⏳ Not started |

Docs that still say "Iteration 4 = production" and must be corrected in Phase 0: `README.md` §13,
`docs/Iteration3_Plan_of_Action.md` §4 + Phase 7, `docs/iteration-docs/AI_Jumpstart_MVP_Iteration3_handoff.md`
§9, and the `DEVELOPMENT_JOURNAL.md` project-snapshot block.

### Carry-forward guardrails (unchanged, non-negotiable)
- PPO is *recommended, not mandated*. Iteration 3 verdict stands: **evaluated, not shipped** — lost all
  four scenarios on objective **and** CVaR-75. It stays visible in the benchmark, not hidden.
- The naive/untuned baseline is the legitimate target to beat. A **tuned** classical solver does **not**
  collapse — on this device it wins all four. Do not write or say otherwise.
- The **~94% paper figure is a baseline-collapse + rescaled-metric artifact**. Never a flat saving.
- Improvement percentages are **vs. the naive baseline**, not vs. a customer's actual costs.
- Binding hardware constraint is memory **bandwidth (~273 GB/s)**, not the 128 GB capacity.
- No hospital service-level claim. Data stays on-device. Prompt injection is flagged, never executed.
- The LLM advisory boundary is absolute: it **explains** numbers, it never computes or overrides one.
- Every number traces to a real on-device run or a real file on disk. No fabrication, ever.

### 🔴 New guardrail introduced by this iteration
**A beautiful dataset page invites the viewer to assume the data is real.** It is not — it is seeded
synthetic Manufacturing data. Therefore:
- A persistent, unmissable provenance badge on every dataset screen: **"Synthetic demo dataset · seed
  12345 · generated on-device · not customer data."**
- Zero hardcoded counts anywhere in the API or UI. Every figure is read from
  `data/generated/<scenario>/` at request time, and a test enforces reconciliation against the
  pipeline's own ingest row counts.

---

## 1. Decisions made under delegated authority

| # | Decision | Call | Rationale |
|---|---|---|---|
| 1 | **Where it lives** | Same SPA, separate **view** reached by a header button ("View the dataset"), linkable via `?view=dataset` | Ryan said "same page or new page, your call." A distinct view keeps the results screen uncluttered but stays one bookmarkable URL — matching the existing `?replay=true` pattern. |
| 2 | **Routing library** | **No `react-router`.** URL-param view switching in `App.tsx` | One extra view does not justify a router dependency, a bundle increase, or nginx SPA-rewrite changes. Revisit at 3+ views. |
| 3 | **Where aggregation happens** | **Server-side, in the API.** Browser receives a pre-aggregated JSON overview | `stress-large` is 44,928 demand rows + 15,808 lane-period rows. Shipping raw CSV to the browser would be slow, fragile, and pointless. Polars already loads these in the API. |
| 4 | **LLM involvement** | **None.** All prose on the dataset view is deterministic template text derived from real values | Three reasons: (a) it must be instant and identical every load, (b) it keeps the ADVISORY-ONLY boundary clean — no LLM text ever sits next to raw input data unlabeled, (c) an LLM describing a dataset is a hallucination surface with zero upside here. LLM interpretation of the data is **Iteration 5's** job, where it is explicitly labeled and grounded. |
| 5 | **Naming** | Module `src/dataset/overview.py`, endpoint `GET /dataset/overview`, payload key `dataset_overview` | The repo already uses "profile"/"profiler" for **resource** profiling (`src/bench/profiler.py`, `resource_profiles`, `peak_process_rss_mb`). Calling this a "dataset profile" would collide semantically in code, tests, and conversation. |
| 6 | **Scenario legibility** | Include a plain-English **scenario diff card** ("what is broken in this scenario vs. baseline") in this iteration | Half of Ryan's ask #2 ("what do these scenarios even mean?") is answered by *describing the data*, not by a chatbot. It is cheap here and it makes his review of ask #1 much stronger. **Boundary:** static description only — no interactive/custom scenarios (that is Iteration 5). If Ryan reads this as scope creep, it is the one item to cut. |
| 7 | **Raw-data access** | Optional per-table **CSV download** through the authenticated proxy | Cheapest possible trust move for a technical viewer, and it reinforces "the data is right here on the box." Zero new auth surface — nginx already injects the key server-side. |
| 8 | **Replay parity** | The dataset view must work in `?replay=true` mode from a captured overview snapshot | The recorded demo is the safety net for live-GPU flakiness. A fallback that loses half the walkthrough is not a fallback. |

---

## 2. EXECUTION PROTOCOL — read before running any phase (AGENT)

This plan is built to be executed **one phase per session**, not all at once.

- Execute **exactly ONE phase per run.** Do its tasks, hit its Definition of Done, then **STOP.**
- **Do NOT begin the next phase** until Ishan explicitly says go. The starter prompt names the phase.
- At every STOP checkpoint you MUST, in order:
  1. **Brutal-truth review** — re-examine everything you did against the guardrails and the *actual
     on-device behavior* (not your own build report). Assume something is wrong and go find it; fix any
     real defect before proceeding. This practice has repeatedly caught real bugs on this project (fake
     routing, hardcoded tie-breaks, fake SSE progress, retrieval-time injection gap).
  2. **Commit** with a clear message.
  3. **Add a `DEVELOPMENT_JOURNAL.md` entry** (newest at TOP): what changed, why, verified real results
     (not assumed), review findings + fixes, git ref, open follow-ups.
  4. **Report** a short summary to Ishan and wait.
- **Operational gotcha:** the `api` container bakes `src/` in via `COPY` — it is **not** bind-mounted.
  After ANY `src/` change run `docker compose build api && docker compose up -d --no-deps api` before
  `make test` / `make run` / `make bench-all`, or you silently test stale code. `data/` **is**
  bind-mounted, so corpus/scenario data changes need no rebuild.
- **Web changes** need `docker compose build web && docker compose up -d --no-deps web`.
- **Remote verification:** `localhost` only resolves *on* the GB10. Verify in a real browser from the
  laptop via the GB10's Tailscale address (see `docs/DEMO_GUIDE.md` remote-access section). Do not
  hardcode any IP into the repo.
- If you hit a guardrail conflict or a real blocker, **stop and report** — do not work around it.
- Phases are dependency-ordered. Do not skip ahead.

---

## 3. Phases

### Phase 0 — Orientation, green baseline & roadmap renumber *(cheap; no feature code)*

- **Objective:** confirm the repo is still green after the demo, clear one long-standing infra
  follow-up, and make the roadmap self-consistent before any feature work lands.
- **Tasks:**
  - Read `README.md`, `DEVELOPMENT_JOURNAL.md` (newest entries first), this PoA,
    `docs/DEMO_GUIDE.md`, and `.devin/rules/helix-sco.md`.
  - `make up` → `make test` (**expect 69 passed + 2 xpassed = 71**) → `make bench-all`. Record the
    four-scenario numbers as the pre-Iteration-4 reference (classical objectives should reproduce:
    baseline 81,789 · shortage-shock 95,445 · demand-surge 94,165 · stress-large 2,521,615).
  - **Close the stale-NVML follow-up.** The `llm` container has carried stale NVML since Iteration 3
    Phase 0 (works, fragile on restart). The demo is over — this is the maintenance window.
    `docker compose up -d --no-deps --force-recreate llm`, accept the ~2 min Nemotron reload, then
    confirm in-container `nvidia-smi` works and `/health` reports `gpu_visible:true`. If the 2 xpassed
    GPU-probe tests flip to passing, say so; if the recreate destabilizes anything, **revert and report**.
  - **Renumber the roadmap** (docs-only) per §0: `README.md` §13, `Iteration3_Plan_of_Action.md` §4 and
    Phase 7, `AI_Jumpstart_MVP_Iteration3_handoff.md` §9, journal snapshot. Everything that said
    "Iteration 4 = production" now says "Iteration 6"; add Iterations 4 and 5 with one-line scopes.
  - Commit this PoA to `docs/Iteration4_Plan_of_Action.md`.
- **DoD:** stack healthy; 71 tests accounted for; four-scenario reference captured in the journal;
  `llm` NVML state recorded honestly (fixed or explained); no doc anywhere still calls production
  "Iteration 4".
- **⏹ STOP / CHECKPOINT:** brutal-truth review → commit → journal → report → wait for go.

---

### Phase 1 — Dataset overview API *(the contract everything else depends on)*

- **Objective:** one authenticated endpoint that returns a complete, pre-aggregated, deterministic
  description of a scenario's dataset, derived entirely from files on disk.
- **Tasks:**
  - New module `src/dataset/overview.py` exposing `build_dataset_overview(scenario: str) -> dict`.
    **Reuse `src/ingest` loaders** — do not re-implement CSV parsing (the journal's standing DRY rule;
    duplicated parsing is how counts drift out of sync).
  - Payload sections (see §6 for the full shape):
    `provenance` · `at_a_glance` · `network` · `products` · `demand` · `lanes` · `capacity` ·
    `costs` · `service_targets` · `initial_inventory` · `scenario_diff` · `pipeline_link`.
  - **Aggregate, do not dump.** Hard rules: no section returns more than 200 rows; long tables are
    top-N by materiality with an explicit `"showing top N of M"` field; demand is returned as
    per-period totals plus top-N SKU series, never row-level.
  - New endpoint `GET /dataset/overview?scenario=<name>` on the existing protected router
    (`X-API-Key`, same validation posture as `/scenarios`). Unknown scenario → **404** with a clear
    message. Missing generated data → **409** with "run `make demo-data`", not a 500.
  - Optional `GET /dataset/table?scenario=<name>&table=<name>` returning the raw CSV as a download,
    whitelisted to the nine known tables. Path-traversal test required.
  - Tests in `tests/test_iteration4_dataset.py`:
    - **Reconciliation (the important one):** overview counts equal the pipeline's own ingest row
      counts for `baseline` — nodes 17, SKUs 28, BOM 24, demand 2,912, production lines 6, lanes 30,
      lane-periods 1,560, service targets 32, initial inventory 32.
    - **Determinism:** two calls on unchanged data return byte-identical JSON.
    - **All four scenarios** build without error, including `stress-large`.
    - **Payload budget:** `stress-large` overview serializes to **< 250 KB** and returns in **< 2 s**
      warm. If it does not, aggregate harder — do not raise the budget.
    - Auth required; unknown scenario 404; unknown table rejected; no path traversal.
    - **No fabrication:** grep the module for hardcoded topology integers; assert none.
- **DoD:** `curl` the endpoint for all four scenarios and paste real output in the journal; every count
  reconciles with ingest; determinism and payload budget verified on-device; tests green.
- **⏹ STOP / CHECKPOINT:** brutal-truth review → commit → journal → report → wait for go.

---

### Phase 2 — Plain-English narrative & scenario-diff layer *(deterministic, no LLM)*

- **Objective:** turn correct-but-technical numbers into sentences a non-specialist reads once and
  understands. This is where "even a child gets it" is actually won or lost.
- **Tasks:**
  - **The one-sentence summary**, composed from real values, e.g.:
    > "This is one factory network: **2 suppliers** ship parts to **1 plant** running **6 production
    > lines**, which sends finished goods through **3 distribution centers** to **11 customers** —
    > **28 products**, **52 weeks** of demand history, planned **8 periods** ahead."
    Derived from actual node-type counts. If the topology changes, the sentence changes.
  - **Six at-a-glance tiles** with plain labels and units, not schema names:
    Places in the network · Products tracked · Shipping lanes · Weeks of history · Demand records ·
    Random seed (reproducible).
  - **Inline glossary** for every term that will otherwise stop a reader: lane, echelon, BOM,
    lead time, fill rate, days of inventory, (s,S), safety stock, backorder vs lost sale. One short
    sentence each, no jargon inside the definition. Store centrally (`web/src/lib/glossary.ts`) so it
    is reusable by Iteration 5.
  - **Scenario diff card** — read the scenario YAML against `baseline` and state, in words, what is
    different and when. For `component-shortage-shock`: *"From period 3, one supplier's shipments of a
    key component drop to zero for 4 periods. Nothing else changes."* Include the affected node/lane/SKU
    IDs and the period range so it can be highlighted on the network map in Phase 4.
  - **Lumpiness / method callout:** for each series, the zero-fraction that decides AutoETS vs
    CrostonSBA. Renders as "X of Y products have lumpy, intermittent demand — those are forecast with
    Croston-SBA, the rest with AutoETS." This is the one place the dataset page explains a *modeling*
    choice, and it is fully derived, not asserted.
  - **`pipeline_link` section:** which dataset tables feed which pipeline stage
    (ingest → forecast → optimize → plan), so the viewer connects "my data" to "the result I just saw."
  - Formatting helpers in `web/src/lib/datasetFormat.ts` + Vitest coverage (units, thousands
    separators, singular/plural, "1 supplier" not "1 suppliers", empty/zero cases).
- **DoD:** narrative strings are generated from real values for all four scenarios and reviewed by
  Ishan for readability; scenario diff is correct against each YAML (verified by reading the configs,
  not assumed); glossary covers every jargon term that appears in the payload; Vitest green.
- **⏹ STOP / CHECKPOINT:** brutal-truth review → commit → journal → report → wait for go.

---

### Phase 3 — Web dataset view: navigation, layout & Level-1 hero

- **Objective:** the view exists, is reachable, is honest about provenance, and delivers the
  "ohh — that's my dataset" moment above the fold.
- **Design principle — three levels of progressive disclosure.** Non-negotiable structure:
  - **Level 1 (above the fold, zero clicks):** provenance badge · one-sentence summary · six tiles ·
    the network map. A viewer who reads only this understands the dataset.
  - **Level 2 (scroll):** section cards — products/BOM, demand, lanes, capacity, costs, service
    targets, starting inventory, scenario diff.
  - **Level 3 (click to expand):** full tables, exact values, CSV download.
- **Tasks:**
  - Header button on the results screen: **"View the dataset"**, plus a return button. Wire
    `?view=dataset` (and `?view=dataset&scenario=X`) so it is linkable and bookmarkable — Ryan can
    open it directly.
  - `web/src/DatasetView.tsx` + section components. Keep `App.tsx` from growing further; the journal
    already notes it is monolithic.
  - Persistent provenance badge (§0 guardrail) — visible at Level 1 and in the sticky header, not
    buried in fine print.
  - Loading, empty ("no data generated yet — run `make demo-data`"), and error states. No spinner
    that can hang forever; no blank screen.
  - Scenario selector inside the view, defaulting to whichever scenario is selected on the results
    screen so context carries across.
- **DoD:** view loads from the Tailscale address in a real browser at 1920×1080 **and** on a laptop
  screen; Level 1 fits above the fold without scrolling on a 1080p display; all four scenarios render;
  provenance badge always visible; no console errors; TypeScript/Vite build clean.
- **⏹ STOP / CHECKPOINT:** brutal-truth review → commit → journal → report → wait for go.

---

### Phase 4 — Web dataset view: visuals, disclosure & polish *(the "a child gets it" phase)*

- **Objective:** make it genuinely beautiful and genuinely legible. This is the phase Ryan will judge.
- **Tasks:**
  - **Network map (the hero visual).** Left-to-right tiers: suppliers → plant/lines → DCs → customers.
    Nodes labeled in plain words with counts; lanes drawn between tiers with lead time and cost on
    hover. **Scenario overlay:** the disrupted node/lane from Phase 2's diff is visually marked
    (e.g. amber, with a short "zero supply, periods 3–6" tag) so "what this scenario does" is visible
    on the picture, not just in text. Build with Recharts/SVG already in the bundle — **do not add a
    graph library** for one diagram; the bundle is already over the 500 kB Vite warning.
  - **Product tree:** BOM as an expandable finished-good → subassembly → raw-component tree with
    quantity-per, plus a plain line: "each unit of SKU-X needs 2 of SKU-Y and 4 of SKU-Z."
  - **Demand chart:** total units per period with the shock/surge window shaded and labeled; top-N SKU
    breakdown; the lumpiness callout from Phase 2.
  - **Lanes table:** origin → destination, lead time (in days, spelled out), cost per unit, capacity,
    and a small per-period disruption strip so capacity drops are visible as a timeline.
  - **"Where the money is" card:** the cost parameters that produce the objective (holding, ordering,
    transport, backorder, lost sale), so the viewer sees why the optimizer trades what it trades. Label
    it as *inputs*, distinct from the *results* screen's measured costs — these must never be confused.
  - **Capacity, service targets, starting inventory** cards, each with one plain-English line.
  - Level-3 expanders with full tables + per-table CSV download.
  - Accessibility and demo-readiness: keyboard reachable, colour choices that survive a projector and
    are not red/green-only, text large enough to read on a shared screen.
  - Visual QA: capture screenshots of all four scenarios from the laptop browser and attach them to the
    journal entry. **Do not skip this** — "no manual browser screenshot captured" is a recurring gap in
    prior phases.
- **DoD:** all four scenarios render correctly with the scenario overlay; screenshots in the journal;
  bundle size change recorded and justified; `npm test` green; `npm audit` still 0 vulns; no number on
  screen that is not in the API payload.
- **⏹ STOP / CHECKPOINT:** brutal-truth review → commit → journal → report → wait for go.

---

### Phase 5 — Demo integration, replay parity & docs

- **Objective:** the dataset view is part of the demo, works without a live GPU, and is documented.
- **Tasks:**
  - **Replay parity:** capture a real `dataset_overview` for `component-shortage-shock` into
    `web/public/demo-dataset-overview.json`; `?replay=true` serves the dataset view from it with no API
    call. Label it as a real captured snapshot, never mock data.
  - **Recapture `web/public/demo-replay.json`.** Known open follow-up from Iteration 3 Phase 4: it still
    carries pre-MDP PPO numbers. Recapture from a current live run so the replay's approaches table
    matches the shipped code. Verify the classical objective still lands on 95,445 and re-run the
    no-secrets scan on the new file (`api_key`, `password`, `secret`, `credential`, `HELIX_API`).
  - `make demo` banner prints the dataset URL alongside live and replay.
  - **`docs/DEMO_GUIDE.md`:** new section for the dataset view with a talk track — how to open it, what
    to point at in what order (one sentence → six tiles → map → scenario overlay → "and this is what
    produced the result you just saw"), and the honest "this is synthetic, seeded, on-device" line.
  - Fold in the **remote-access subsection** deferred from demo prep: `localhost` resolves only on the
    GB10; use the GB10's Tailscale address; SSH port-forwards must be run **from the laptop**, not from
    inside a GB10 session (the "Address already in use" trap). **No hardcoded IPs in the repo** —
    describe how to find it.
  - Update `README.md` §9 with the dataset view and its URL pattern.
- **DoD:** `?replay=true` gives a complete GPU-free walkthrough including the dataset view; recaptured
  replay verified current and secret-free; demo guide talk track written and followed end-to-end once
  by Ishan as a rehearsal.
- **⏹ STOP / CHECKPOINT:** brutal-truth review → commit → journal → report → wait for go.

---

### Phase 6 — Verification, brutal-truth sweep & Ryan review packet

- **Objective:** prove nothing regressed, then hand Ryan something he can look at in five minutes and
  react to.
- **Tasks:**
  - Full regression: `make test` (existing 71 + new dataset tests), `make bench-all` → **objectives
    identical to the Phase 0 reference**. If any objective moved, stop: this iteration touched no
    optimizer code, so a change means something unexpected happened.
  - Perf sanity on the box: dataset endpoint latency for all four scenarios; device memory unchanged
    (this iteration should add ~nothing to the envelope — confirm, don't assume).
  - Cross-check every claim in the new UI against the payload and the CSVs by hand for one scenario.
  - **Guardrail sweep:** synthetic-provenance badge present on every dataset screen · no LLM text on
    the dataset view · no hardcoded counts · no fabricated figures · improvement-% caveat intact on the
    results screen · PPO still visible and honestly labeled · no hospital claim · no `~94%` framing ·
    data never leaves the box · no API key in the browser bundle (re-run the leak scan).
  - **Iteration 4 handoff doc** at `docs/iteration-docs/AI_Jumpstart_MVP_Iteration4_handoff.md`, in the
    house style: TL;DR · what shipped per phase · the new endpoint · screenshots · honest caveats ·
    what's next (Iteration 5 pending his feedback).
  - Merge `feat/iteration4-dataset-transparency` → `main`; push.
  - **Ryan packet:** short message with (a) the dataset URL over Tailscale, (b) 2–3 screenshots,
    (c) one line on what it does, (d) an explicit ask: *"does this answer what you wanted? anything to
    add before I start the chatbot?"* Keep it short — he said he'd look and then tell you.
- **DoD:** full suite green; benchmark objectives bit-identical to Phase 0; guardrail sweep documented
  in the journal; handoff doc committed; merged to `main`; packet sent.
- **⏹ STOP / CHECKPOINT:** brutal-truth review → commit → journal → report → **wait for Ryan's
  feedback before opening the Iteration 5 plan.**

---

### Phase 7 — Deferred (do NOT execute this iteration)
- **Iteration 5:** conversational scenario/what-if analyst — see `docs/Iteration5_Plan_of_Action.md`.
  Ryan's explicit sequencing: only after he has reviewed Iteration 4.
- **Iteration 6:** production track — real customer-data onboarding/ETL, HA, multi-tenant isolation,
  security hardening, licensing (NFR/NVAIE), shippable appliance image, multi-vertical validation.
- Listed only so the boundary is deliberate, not drift.

---

## 4. Traceability — Ryan's ask → where it is answered

| What Ryan said | Where it lands |
|---|---|
| "No idea of the dataset it's running on" | Phase 1 (API) + Phase 3 (view) |
| "How many warehouses, how many shipments" | Phase 1 `network`/`lanes`; Phase 4 network map + lanes table |
| "A button, clicking which takes you to a page" | Phase 3 header button + `?view=dataset` |
| "Beautifully represented" | Phase 4 (visuals, progressive disclosure) |
| "Even a child can interpret it" | Phase 2 (plain-English layer, glossary) + Phase 3 Level-1 hero |
| "OHH that is my dataset, gotchaaaa" | Phase 2 one-sentence summary + Phase 4 network map |
| "The scenarios aren't intuitive" *(partial)* | Phase 2 scenario diff card + Phase 4 scenario overlay. **Full answer is Iteration 5.** |
| "Baby steps — do 1), let me know" | Phase 6 review packet, then hard stop |

---

## 5. Risks & how each is handled

| Risk | Mitigation |
|---|---|
| `stress-large` makes the view slow or huge | Server-side aggregation with a **hard < 250 KB / < 2 s** budget enforced by test (Phase 1). Aggregate harder rather than raise the budget. |
| Beautiful page reads as real customer data | Persistent synthetic-provenance badge; explicit in the demo talk track (Phases 3, 5, 6 sweep). |
| Dataset counts drift from what the pipeline actually ingests | Reconciliation test against ingest row counts; zero hardcoded integers (Phase 1). |
| Scope creep into the chatbot | Decision 6 draws the line; scenario support is **static description only**. Anything interactive stops and gets logged for Iteration 5. |
| Bundle bloat on an already-large chunk | No new graph/router libraries; Recharts/SVG only; bundle delta recorded in Phase 4 DoD. |
| Input costs confused with measured result costs | "Where the money is" card explicitly labeled as *inputs*, visually distinct from the results screen (Phase 4). |
| Regression in results while touching the web app | Phase 6 requires bit-identical benchmark objectives vs. the Phase 0 reference. |
| Session token limits | One phase per session; the web work is deliberately split across Phases 3 and 4. |

---

## 6. Appendix A — Proposed `dataset_overview` payload shape

Illustrative structure, not a schema to copy verbatim; finalize in Phase 1 against the real files.

```
dataset_overview
├── provenance        : scenario, requested_seed, effective_seed, generated_at, generator,
│                       is_synthetic=true, regeneration_command, byte_identical_claim
├── at_a_glance       : six tiles {label, value, unit, plain_english_note}
├── narrative         : one_sentence_summary, scenario_sentence, lumpiness_sentence
├── network           : nodes_by_type {supplier, plant, dc, customer},
│                       node_list [{id, type, plain_label, region}],
│                       edges [{from, to, lane_id, lane_type, lead_time_days, cost_per_unit, capacity}]
├── products          : sku_count_by_tier, bom_tree [{parent, children:[{sku, qty_per}]}],
│                       top_n_by_demand_share
├── demand            : periods, history_weeks, total_rows,
│                       units_per_period [], top_n_sku_series [],
│                       lumpy_series_count, forecast_method_split {auto_ets, croston_sba},
│                       shock_window {from_period, to_period, description} | null
├── lanes             : count_by_type, table [top-N], disruption_timeline [{lane_id, period, effect}]
├── capacity          : lines [{line_id, plant, capacity_units}], utilization_note
├── costs             : per_sku_params [top-N] {holding, ordering, backorder, lost_sale, unit},
│                       transport_cost_range, label="INPUT PARAMETERS — not measured results"
├── service_targets   : count, fill_rate_targets, criticality_tiers
├── initial_inventory : rows, total_units, days_of_cover_estimate
├── scenario_diff     : vs="baseline", changes [{what, where, when, plain_english}]
└── pipeline_link     : stage_inputs {ingest:[tables], forecast:[tables], optimize:[tables]}
```

## 7. Appendix B — Reusable agent starter prompt

Paste alongside this plan each session; change only the phase number.

```
You are resuming work on the Helix AI Jumpstart Service — an on-device supply-chain-optimization
prototype running entirely on an NVIDIA GB10 (arm64, Grace Blackwell, ~121 GiB unified memory).
The repo is cloned on the GB10 at ~/projects/Helix-AI-Jumpstart-Service-.

Before doing anything, READ these in full:
1. README.md                          (overview, hardware, status, decisions, guardrails)
2. docs/DEVELOPMENT_JOURNAL.md        (chronological truth ledger — newest entries first)
3. docs/Iteration4_Plan_of_Action.md  (the plan you will execute)
4. docs/DEMO_GUIDE.md                 (what the demo shows and how it is run)
5. .devin/rules/helix-sco.md          (auto-loaded accuracy guardrails)

Then follow the EXECUTION PROTOCOL in §2 of the plan. Non-negotiable rules:
- Execute EXACTLY ONE phase per session. This session, execute ONLY: >>> PHASE 1 <<<
  (change this number each session.)
- Do the phase's tasks, meet its Definition of Done, then STOP. Do NOT start the next phase.
- After ANY change under src/, rebuild before testing:
    docker compose build api && docker compose up -d --no-deps api
  After ANY change under web/, rebuild the web container:
    docker compose build web && docker compose up -d --no-deps web
  (src/ is baked into the image via COPY, not bind-mounted — editing on the host silently tests
  stale code. data/ IS bind-mounted.)
- Verify with REAL on-device runs (make test / make demo / make bench-all) and, for UI work, a real
  browser loaded over Tailscale. Never report a result you did not actually observe. If something
  fails or falls back, say so plainly.
- Every figure the dataset view shows must be derived from the actual generated files. No hardcoded
  counts, no fabricated numbers, no LLM-generated prose on the dataset view.
- Keep the synthetic-data provenance badge visible. This is seeded synthetic data, not customer data.
```

---

*Iteration 4 targets branch `feat/iteration4-dataset-transparency`. Vertical: Manufacturing.
Product shape: Development / PoC (demo/pilot-ready). Predecessor: Iteration 3, merged `main` 2026-07-27.*