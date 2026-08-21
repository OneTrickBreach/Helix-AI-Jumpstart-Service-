# Iteration 6b — Plan of Action: Custom Dataset (the network tier), demo-driven

**Prepared for:** Ryan Spurr | Helix, Connection Inc.
**From:** Ishan (AI Intern)
**Status:** 🔴 **PLANNED, NOT STARTED.** Written 2026-08-21 against `main` @ `262c498`, with every
number in §1 measured on-device that day. No code written.
**Branch:** `feat/iteration6b-custom-dataset`, to be cut from `main` @ `262c498` (Phase 0).
**Predecessor:** Iteration 6a — Custom Scenario. **Merged to `main` as `ad17cc5`** on 2026-08-20 and
re-verified on `main`: `make test` **558 passed + 2 xpassed**, `make bench-all` **all 12 objectives
bit-identical**, `make scenario-eval` **29/29**, `make web-test` **108**, `make web-check` **38/38**.
Handoff at [`iteration-docs/AI_Jumpstart_MVP_Iteration6a_handoff.md`](iteration-docs/AI_Jumpstart_MVP_Iteration6a_handoff.md).
**Origin:** Ryan's second ask of 2026-08-19, in his words — *"instead of asking the chat bot what would
happen if a warehouse went down, why can't we just reduce a warehouse."*
**Objective:** let a planner change the shape of the network itself — how many suppliers, plants,
warehouses, customers and products — run the real pipeline on it, and save it. **And be honest about
what the optimizer does and does not model about a warehouse**, because measuring that is the most
valuable thing this iteration produces.

---

## 0. Read-First

### 0.1 🔴 The binding constraint is a calendar, and it is short

| Date | What it is |
|---|---|
| **Fri 2026-08-21** | Today. Plan written. |
| Sat 22 – Sun 23 | Weekend. Available, not assumed. |
| **Mon 24 – Tue 25** | **The only two full working days.** |
| **Wed 2026-08-26** | 🔴 **Ryan demo.** Rescheduled from 2026-08-20 by him, twice. |
| Thu 27 – Fri 28 | The last two days of Ishan's internship. **Reserved for handoff, not features.** |

Two consequences baked into this plan rather than discovered on Tuesday night:

1. **Phase 0 is demo hardening, and it ships first — before any 6b feature.** It is worth more than
   this whole iteration, because it protects the meeting itself (§0.2). If everything after Phase 0
   slips, Wednesday is still a good demo of 6a.
2. **The cut line in §0.6 is real.** Each phase is independently shippable, and the plan says in
   advance which ones to drop.

### 0.2 🔴 The demo is currently one bad hour away from having no fallback

Options A (results), C (dataset) and D (chat) all have a recorded, GPU-free replay path. **Option E —
the custom scenario, the entire subject of Wednesday's meeting — does not.** The control is
deliberately hidden in replay mode ([`App.tsx:447`](../web/src/App.tsx#L447)), and correctly so:
building a scenario needs the API, and offering a panel that can only say "Failed to fetch" would be
worse than hiding it.

But NVML has now detached from these containers **four times** (2026-07-10, 2026-07-30, 2026-08-20,
and 🔴 **again on 2026-08-21, found at the start of Phase 0** — `/health` read `gpu_visible:false`
after the `api` container had been up only **19 hours** since the 2026-08-20 fix). `llm`'s handle is
**still stale**. The cadence has gone from ~2 weeks to under a day, so the failure mode is not
theoretical: the box wobbles on Wednesday morning, and the one thing Ryan came to see cannot be shown
at all.

**Phase 0 closes that** — with a screen recording rather than a replay implementation, for the reasons
in Phase 0. It is not polish.

### 0.3 🔴 What measuring this iteration found, and why it changes the pitch

Before writing a line of it, the eight `network:` counts were measured the way a planner would
experience them: change the count, generate, run the real optimizer, read the objective (§1). The
results are the most valuable thing in this document.

> ### A warehouse is free, and the model says you should have none.
>
> | Network | Objective | Fill rate | Days of inventory |
> |---|---:|---:|---:|
> | `baseline` — 2 DCs | 81,789.36 | 83.66% | 4.67 |
> | **1 DC** — Ryan's own ask | **81,663.11** *(cheaper)* | **83.66%** *(identical)* | **4.67** |
> | 3 DCs | 82,056.85 *(dearer)* | 83.66% *(identical)* | 4.67 |
> | **0 DCs** | **68,565.25** *(16% cheaper)* | **92.01%** *(better!)* | **0.63** |
>
> Removing warehouses makes the plan cheaper and never costs a point of service. A network with **no
> warehouses at all** scores the best of the four.

That is not a bug to fix by Tuesday. It is a **measured statement about how deep the optimizer's model
goes**, and it is the same root cause as three things already on record:

| Already known | Same root cause |
|---|---|
| Question 6 — lane capacity is read at **one period** | capacity is modelled thinly |
| `dc_throughput_units_per_period` is **inert** (`nodes.csv` is never read) | a node has no throughput |
| Zeroing a whole lane family **lowers** the objective (81,789 → 77,788) | not shipping is not penalised |
| **New:** removing a warehouse is free, and zero warehouses is best | a node is not in the LP at all |

The mechanism, verified in [`src/optimize/common.py:114-185`](../src/optimize/common.py#L114): the
routing LP is **three independent single-commodity transportation problems**, one per lane type, each
with one aggregate demand constraint and per-lane capacity bounds. **There is no node in it.** No flow
conservation through a DC, no per-node throughput cap, and no link between the `plant_to_dc` problem
and the `dc_to_customer` problem. A warehouse is a label on the end of a lane. The specific line that
makes zero warehouses *free* rather than *infeasible* is
[`:149`](../src/optimize/common.py#L149) — `if frame.is_empty(): continue`, which silently skips a
lane family that has no lanes. **And `select_greedy_lanes` — the naive baseline — has the identical
shape** ([`:52-64`](../src/optimize/common.py#L52)), so this is not an artifact of the tuned solver:
both candidates share the gap, which is why the within-run comparison stays fair even though neither
models a node. Full write-up:
[`iteration-docs/Modelling_Finding_The_Optimizer_Has_No_Node.md`](iteration-docs/Modelling_Finding_The_Optimizer_Has_No_Node.md).

**So the Wednesday pitch changes shape, for the better.** Not *"here are more sliders"* but: *"you
asked for two things and here is both — and building the second one turned four separate oddities into
one coherent modelling gap, measured four ways, which is now the highest-value thing you could fund
next."* That is a better thing to hand a sponsor than another panel.

### 0.4 What this iteration IS / IS NOT

**IS:** the eight `network:` counts as validated controls · hard floors so no configuration can crash
the generator or the forecast · honest labelling of which counts move the answer, which cannot, and
which move it only by changing the size of the problem · reuse of every mechanism 6a already
built — synthesis, validation, save/list/delete, the run path, the results screen, the change list.

**IS NOT:** **not row-level entity editing.** *"Delete `DC-002` specifically, keep `DC-003`"* is not
expressible and is not in scope (§1.5) · not a change to the optimizer or the objective function
(§0.5 guardrail 2) · not a fix for the node-capacity gap — that gap is **measured, documented and put
in front of Ryan as a decision**, which is the honest thing to do with two days on the clock · not
real customer data · not a change to the chat surface.

### 0.5 Carry-forward guardrails (unchanged)

PPO evaluated-not-shipped and kept visible · naive baseline is the legitimate target · `~94%` is a
baseline-collapse artifact · improvement % is vs. the naive baseline and the caveat stays on screen ·
bandwidth not capacity is the binding hardware constraint · no hospital service-level claim · data
never leaves the box · prompt injection flagged, never executed · every number traces to a real run ·
the LLM narrates and never calculates · **no no-op controls** (6a guardrail 1) · the four canonical
scenarios are immutable and their names reserved · reproducible or it does not ship.

### 0.6 🔴 New guardrails, and the cut line

**Guardrails:**

1. **Nothing may crash.** Four network values raise `ZeroDivisionError` inside the generator today and
   one breaks the forecast (§1.3). Every one gets a floor and a plain-English refusal *before* anything
   is written. A stack trace in front of Ryan is a worse outcome than a missing feature.
2. **The optimizer and the objective function are not touched.** All 12 recorded objectives stay
   bit-identical, and the check runs at every checkpoint. The node-capacity gap is documented, not
   patched, four days before a demo at the end of an internship.
3. **Three honesty classes, on the control itself.** Every network control is labelled as one of:
   *changes the answer* · *changes the size of the problem, so the objective is not comparable to the
   recorded baseline* · *cannot change the answer*. §1.2 assigns each of the eight.
4. **A resized problem must never be compared to 81,789.36.** Changing the customer or product count
   changes total demand, so the objective is a different quantity, not a better or worse one. The
   within-run naive-vs-classical comparison stays valid and is what the screen must lead with.

**The cut line, decided now:**

| # | Slice | Verdict if the days run out |
|---|---|---|
| 1 | **Phase 0 — demo hardening** | 🔴 **Never cut.** Protects Wednesday regardless of everything else. |
| 2 | Phase 1 — network ledger, floors, labels | **Minimum shippable 6b.** Even with no UI, this is a real, testable, honest answer to "reduce a warehouse" via the API. |
| 3 | Phase 2 — network keys through synthesis and save | **Target.** Makes it a saved, reopenable dataset. |
| 4 | Phase 3 — the UI tier | **Target.** What Ryan actually clicks. |
| 5 | Phase 4 — regression, demo guide, packet | **Required to call it done.** |
| 6 | Row-level entity editing | **Explicitly out.** Named as deferred in the handoff, with the reason. |
| 7 | Fixing the node-capacity gap | **Explicitly out.** Documented as the recommended next investment (§4.1). |

---

## 1. 🔴 What was measured before writing this plan

All on-device on **2026-08-21**, on `main` @ `262c498`, by writing a config, generating it, and running
the real optimizer. Probes were removed afterwards; `data/scenarios/` holds exactly the four shipped
files.

### 1.1 Seven of the eight network counts move the objective — one cannot

Baseline via the probe reproduced **81,789.359460** exactly, confirming the 6a fairness invariant still
holds through this path.

| Setting | Probe | Objective | Δ vs baseline | Verdict |
|---|---:|---:|---:|---|
| `network.suppliers` | 4 / 6 | 81,887.69 / 82,308.50 | +0.12% / +0.63% | moves |
| `network.plants` | 3 | 81,611.00 | −0.22% | moves |
| **`network.lines_per_plant`** | **2 / 4 / 0** | **81,789.36** | **0.000000** | 🔴 **cannot move it** |
| `network.distribution_centers` | 1 / 3 | 81,663.11 / 82,056.85 | −0.15% / +0.33% | moves |
| `network.customers` | 7 / 9 | 66,548.24 / 83,735.10 | −18.6% / +2.4% | moves |
| `network.finished_goods` | 3 / 5 | 60,776.80 / 102,245.23 | −25.7% / +25.0% | moves |
| `network.subassemblies_per_finished_good` | 1 / 3 | 107,405.44 / 84,768.66 | +31.3% / +3.6% | moves |
| `network.raw_components_per_subassembly` | 1 / 3 | 80,741.83 / 89,681.64 | −1.3% / +9.6% | moves |

🔴 **`lines_per_plant` is inert.** It writes only `production_lines.csv`, which the forecast and the
optimizer never read. Set it to **0** — no production lines at all — and the objective is unchanged to
the digit. It is the most manufacturing-sounding control that could go on this panel and it does
nothing. Exactly the `dc_throughput_units_per_period` trap from 6a §1.4, and it gets the same
treatment: shown under *"recorded in the dataset, not read by the optimizer"*, never as a live control.

### 1.2 🔴 The eight counts split into two very different kinds, and the UI must say which

Read the magnitudes above again. They are not one population:

**Node counts — `suppliers`, `plants`, `distribution_centers`** move the objective by **0.12%–0.64%**
and change **fill rate and days of inventory not at all**. Against the 7.08% headline improvement, that
is noise. And the mechanism is not warehouse economics: the generator divides the **dc-to-customer** lane
capacity by `len(dcs) * len(customers)` ([`generate.py:521`](../data/generator/generate.py#L521)) and
draws each lane's cost with jitter, so the delta is capacity re-allocation and random cost draws — not
warehouse economics.

**Proof, measured:** between 1 DC and 2 DCs the cost breakdown is *identical to the cent* on holding
(5,862.55), ordering (5,700.00), backorder (18,493.56) and lost sale (19,916.14). **Only transport
moves** — 20,478.98 at 2 DCs → 20,352.73 at 1 DC, a fall of exactly 126.25, which is the whole
objective delta. A warehouse's entire modelled effect is which lanes the LP picks.

**Problem-size counts — `customers`, `finished_goods`, `subassemblies_per_finished_good`,
`raw_components_per_subassembly`** move it by **1.3%–31.3%**, because they change total demand and BOM
depth. Fewer customers is not a better plan; it is a smaller problem. Finished-good demand goes
66,807 → 58,972 units at 7 customers, and the objective falls with it.

**Therefore, guardrail 3's three classes:**

| Class | Settings | What the control says |
|---|---|---|
| Changes the shape of the network | `suppliers`, `plants`, `distribution_centers` | *"Moves the objective by well under 1% and does not change service at all — the optimizer has no per-node capacity, so this is not a resilience test. See the note."* |
| Changes the size of the problem | `customers`, `finished_goods`, `subassemblies_per_finished_good`, `raw_components_per_subassembly` | *"Changes total demand, so the objective is a different quantity — compare the naive-vs-classical result within this run, not against the recorded baseline."* |
| Cannot change the answer | `lines_per_plant` | The existing 6a inert heading |

### 1.3 🔴 Five network values crash the pipeline today, in three different places

Measured by trying them. These are uncaught exceptions, not validation errors:

| Value | Fails at | Exception |
|---|---|---|
| `plants = 0` | generator | `ZeroDivisionError: integer modulo by zero` |
| `finished_goods = 0` | generator | `ZeroDivisionError` |
| `subassemblies_per_finished_good = 0` | generator | `ZeroDivisionError` |
| `raw_components_per_subassembly = 0` | generator | `ZeroDivisionError` |
| `customers = 0` | **forecast** | `InvalidOperationError: sum operation not supported for dtype str` |

`customers = 0` is the nastiest: it passes generation, writes a full dataset, and only dies two stages
later. **Phase 1 owns floors for all five**, refused before anything is written.

**And two values that do *not* crash but are worse for it:**

| Value | Result | Why it must still be refused or hard-warned |
|---|---|---|
| `distribution_centers = 0` | objective **68,565.25**, fill **92.01%** | See below. The most misleading output this prototype can produce. |
| `suppliers = 0` | objective **77,390.94**, fill **83.66%** | No suppliers, service unchanged to the digit. |

🔴 **Look at what `DC = 0` actually generates.** The lane families collapse to
`{inbound_raw: 10}` — **zero `plant_to_dc` lanes and zero `dc_to_customer` lanes.** There is no longer
any lane by which a finished good can reach a customer. And the pipeline reports:

| Metric | 2 DCs | **0 DCs** |
|---|---:|---:|
| Fill rate | 83.66% | **92.01%** — *better* |
| Backorder cost | 18,493.56 | **9,043.70** — *halved* |
| Lost-sale cost | 19,916.14 | **9,739.37** — *halved* |
| Objective | 81,789.36 | **68,565.25** |

**Severing every delivery path to every customer improves the service metric and halves the shortage
penalties.** Fill rate and the shortage costs come from the inventory policy against forecast demand;
neither asks whether a lane exists to deliver. That single measurement is the clearest statement of
§0.3 available, and it is why decision 4 floors the count at 1 rather than merely warning.

A crash is embarrassing. **A confident wrong answer is worse**, and this is the Iteration 5 §1.2
lesson for the third time: the plausible implementation of "remove a thing" is a no-op or an
improvement, and only measurement tells you.

### 1.4 The upper end is sane, so the floors are the whole job

| Probe | Result |
|---|---|
| `customers = 40` | objective 343,408.86, fill 84.48%, 49 nodes, 94 lanes, 9,568 demand rows — fine |
| `distribution_centers = 12` | objective 81,433.47, 27 nodes, **130 lanes** — fine, and fast |

No ceiling work is needed for the demo. Iteration 3's scale study already establishes the real limit as
forecast latency (~25 ms/series), and `stress-large` (42 nodes, 152 lanes) is bigger than anything
reachable here. **Sanity-cap the counts to keep a fat-fingered 10,000 out of the generator, and move
on.**

### 1.5 Row-level editing is still out of reach, and the reason is positional IDs

The generator builds entities from counts with positional IDs — `DC-001 … DC-00n`
([`generate.py:453`](../data/generator/generate.py#L453)). So **reducing a count deletes the *last*
entity.** "2 DCs → 1" keeps `DC-001`. *"Delete `DC-002`, keep `DC-003`"* is not expressible without a
row-level overlay on the generated CSVs plus cascade repair across lanes, demand, inventory and service
targets — which is the expensive part of the original 6b sketch and is **not** a two-day job.

Say this to Ryan plainly. "Reduce a warehouse" is delivered; "delete *that* warehouse" is named,
scoped and deferred.

### 1.6 What 6a hands over that this must not rebuild

6a's architecture makes this iteration small. The gate is **one function**.

| Asset | Use it for |
|---|---|
| `is_network_key()` ([`synthesize.py:289`](../src/scenario/synthesize.py#L289)) and validation code `network_setting_out_of_scope` ([`validate.py:195`](../src/scenario/validate.py#L195)) | **The entire feature gate.** 6b flips one refusal into a validated path |
| `Setting` dataclass + `SETTINGS` + `REACH_LABELS` ([`ledger.py:63`](../src/scenario/ledger.py#L63)) | Add eight rows. `reach`, `writes`, `minimum`, `maximum` and `note` already exist |
| `derive_setting_targets` / `classify` ([`ledger.py:400`](../src/scenario/ledger.py#L400)) | The derived-equals-declared test extends to the new rows for free |
| `complete_config` / `expand_simple` ([`synthesize.py:193`](../src/scenario/synthesize.py#L193)) | Config synthesis already writes whole configs |
| `src/scenario/store.py` — save / list / delete / clear-all | **Unchanged.** A network-edited config is still just a config |
| `src/scenario/validate.py` — codes, refusal sentences, `capacity_reachability` | Add floor codes alongside the existing ones |
| `src/scenario/api.py` — `custom_settings_payload()`, incl. `excluded_from_6a` | The payload the form renders; the exclusion block becomes the network tier |
| `POST /scenarios/custom/preview` and the other six routes | **Unchanged shape**, new settings flow through |
| `CustomScenarioPanel.tsx` (28 KB), `DeleteScenarioButton.tsx` | Add a group, do not restructure |
| `make scenario-eval` (29 cases), `tests/test_iteration6a_*.py` (5 files) | Extend. Do not start new harnesses |
| 🔴 `__rows__` handling in the reach derivation ([`test_iteration6a_ledger.py:109`](../tests/test_iteration6a_ledger.py#L109)) | **Already solved, and it is the mechanism 6b needs.** A network count acts by changing *row counts*, not column values — and the ablation already treats `(table, "__rows__")` as read when the table is one the pipeline reads. `simulation.horizon_periods` is declared exactly this way. So the seven live counts classify correctly, and `lines_per_plant` falls out as `INERT` on its own because `production_lines` sits in `NON_PIPELINE_TABLES`. **Do not build a second classifier** |
| `narrative.py` ([`:117`](../src/dataset/narrative.py#L117)) | Already builds its summary "clause by clause so a network missing a tier still reads correctly", and already humanises `network` as "network size". A 1-DC dataset should narrate without new template work — verify in Phase 2 rather than assume |
| `NetworkMap.tsx` | 🔴 **Do not touch it.** It is Ryan's favourite screen, and a network-count change is the one edit that will make it visibly redraw — which is the best free demo beat in this iteration |

---

## 2. Decisions

Made under delegated authority on **2026-08-21**. **↩︎ revisit** = for Ryan on Wednesday.

| # | Decision | Call | Rationale |
|---|---|---|---|
| 1 | Scope | **The eight `network:` counts. No row-level editing.** | §1.5. Two working days, and the counts deliver Ryan's sentence. |
| 2 | Demo hardening first | **Phase 0, before any feature** | §0.2. The meeting is the deliverable; the feature is not. |
| 3 | The node-capacity gap | **Measure, document, escalate — do not fix** | §0.3. Fixing it means a real multi-echelon LP and moves all 12 recorded objectives. Not four days before a demo at the end of an internship. ↩︎ revisit — **this is the top question in §4.** |
| 4 | `distribution_centers = 0` and `suppliers = 0` | **Floor both at 1, refused with the measured reason quoted** | §1.3. A network with no warehouses scoring 92% fill is the most misleading thing this prototype can emit. The refusal text says *why*, so it teaches rather than blocks. |
| 5 | The crash floors | **`plants` ≥ 1, `finished_goods` ≥ 1, `subassemblies` ≥ 1, `raw_components` ≥ 1, `customers` ≥ 1** | §1.3. Guardrail 1. |
| 6 | Sanity ceilings | **Cap each count** (suppliers/plants/DCs ≤ 20, customers ≤ 60, finished_goods ≤ 12, BOM depth ≤ 6) | §1.4 shows headroom; the cap exists to stop a typo reaching the generator, not to model a limit. Numbers are a judgement call. ↩︎ revisit |
| 7 | `lines_per_plant` | **Inert class, under 6a's existing heading** | §1.1. Measured at 0, 2 and 4: identical to the digit. |
| 8 | The two honest classes | **Label node counts and problem-size counts differently, on the control** | §1.2, guardrails 3 and 4. A 25% objective move from a product-count change is not an improvement, and the screen must not imply it is. |
| 9 | Naming and storage | **Unchanged from 6a** — `custom-<slug>`, complete config in `data/scenarios/`, data in `data/generated/`, four names reserved | It is still one scenario file. §1.6. |
| 10 | "Dataset" vs "scenario" in the UI | **One panel, a new "Network" group** — not a second feature | Two panels for one config file would be a lie about the architecture, and there is no time to build the lie well. ↩︎ revisit: Ryan asked for two *things*; he may want two *screens*. |
| 11 | The four default scenarios on a custom network | **Out of scope** | The original 6b sketch included it. It needs the shock/disruption blocks re-expressed against a resized network, and it is not a two-day job on top of everything else. Named as deferred. |
| 12 | Chat surface | **Untouched**, regression test only | Ryan parked it 2026-08-19; 6a set this precedent. |

---

## 3. EXECUTION PROTOCOL

Unchanged from Iterations 3–6a. It has caught real defects in every single iteration — including four
in 6a Phase 4 that only a browser could find, and two that a reviewer found after Phase 5 was called
done. **The deadline is not a reason to drop it; it is the reason to keep it.**

- **One phase per session.** Do its tasks, meet its DoD, then **STOP** and wait for an explicit go.
- At every checkpoint, in order: **brutal-truth review** (assume something is wrong; go find it; fix
  real defects) → **commit** → **journal entry** (newest at TOP) → **report** → wait.
- **Rebuild after edits:** `src/` is baked into the `api` image via `COPY` —
  `docker compose build api && docker compose up -d --no-deps api`. Web:
  `docker compose build web && docker compose up -d --no-deps web`. `data/` **is** bind-mounted.
- **Verify with real runs**, never a build log. For UI, `make web-check` **and** a real browser.
- **Web tests run from the committed lockfile** (`npm ci` in a scratch container).
- **Check `/health` for `gpu_visible:true` before trusting any GPU-dependent result**, and read the
  **`xpassed`** count in `make test`, not just "passed" (§Phase 0).
- Stop and report on any guardrail conflict. Do not work around it.

---

## 4. What to put in front of Ryan on Wednesday

### 4.1 🔴 The one question that matters more than any feature

> **Should the optimizer model a node?**
>
> Today it does not. The routing LP is three independent per-lane-type transportation problems with no
> node in them — so a warehouse has no throughput limit, removing one is free, having none is optimal,
> `dc_throughput_units_per_period` is inert, zeroing a lane family *saves* money, and a narrow-window
> capacity disruption is a no-op. **Those are not five problems. They are one, measured five ways.**
>
> Fixing it means per-node flow conservation and throughput constraints — a genuine multi-echelon LP —
> and it would move every objective in every document you have been shown. **It is the highest-value
> engineering investment available on this prototype**, and it is the difference between "this tool
> resizes a network" and "this tool tells you whether your network survives."

Bring the four-row table from §0.3. It is more persuasive than any panel.

### 4.2 The rest, ranked

1. **Question 6** (lane capacity across the horizon) — unchanged from the Iteration 5 and 6a packets,
   and now clearly the same root cause as §4.1. Answer them together.
2. **Are the two honesty classes the right framing?** (§1.2) Node counts move the objective <1% with no
   service change; product counts move it 25% by resizing the problem. Both are honest and neither is
   an "improvement".
3. **Two screens or one panel?** (decision 10) He asked for a custom scenario *and* a custom dataset.
   This ships one panel with a Network group, because that is what the architecture actually is.
4. **Row-level editing** (§1.5) — *"delete `DC-002`, keep `DC-003`"*. Named, scoped, deferred. Worth it?
5. **The four remaining questions from the 6a packet**, still unanswered, plus the seven from
   Iteration 5. 🔴 **Eleven open questions total. Take them on one page.** Wednesday is the last
   scheduled chance to get answers before the internship ends.

---

## 5. Phases

### Phase 0 — 🔴 Demo hardening *(today and the weekend; never cut)*
**This phase contains no 6b feature work and is worth more than the rest of the plan.**

- **Recreate the `llm` container** in a quiet window now, not Wednesday morning: accept the ~10-minute
  Nemotron reload, clear its stale NVML, then re-verify a live completion and `/health`.
- 🔴 **Get a fallback for Option E — the cheap one.** The gap is §0.2, but note *which* fix to buy.
  The engineering answer is Iteration 5's replay pattern (`make chat-transcript` →
  `web/public/demo-chat-transcript.json`, composer locked, API-blocked browser check). Building that
  for Option E is **not a capture — it is UI work**, because the panel makes several round trips
  (settings → preview → save → run) and each would need a recorded response and a read-only mode.
  Call it half a day.
  **A screen recording of the real thing costs twenty minutes and covers the same failure**, which is
  "the box is down and I still need to show Ryan what this does". A fallback does not have to be
  interactive; it has to exist. **Record the walkthrough and spend the half-day on 6b.** It is listed
  under §Deferred with this reasoning, so the next person knows it was a timeline decision and not an
  oversight.
- **Commit a 6a screenshot set** under `docs/iteration-docs/screenshots/iteration6a/`. Iterations 4 and
  5 both have one; 6a has none, and these outlive the internship.
- **Write the consolidated modelling finding** (§0.3 / §4.1) as a standalone page in the 6a packet or
  its own doc. 🔴 **Do this in Phase 0, not Phase 4** — it needs no code, it is the single most
  valuable artifact of the week, and it must not be what gets cut on Tuesday night.
- **Read the Option E talk track out loud, end to end, once.** The definition-of-done item carried
  since Iteration 3 and never closed. It is one hour and it will find real problems.
- Green baseline: `make test` (**expect 558 passed + 2 xpassed** — read the `xpassed`),
  `make bench-all` (**all 12 objectives bit-identical**), `make scenario-eval` (**29/29**),
  `make web-test` (**108**), `make web-check` (**38/38**).
- Cut `feat/iteration6b-custom-dataset` from `main` @ `262c498`.
- **DoD:** Option E has a working GPU-free fallback, verified with the API blocked · `llm` NVML clean ·
  screenshots committed · the modelling finding written · the talk track spoken aloud by a human ·
  all five baseline numbers captured in the journal · branch cut.
- **⏹ STOP / CHECKPOINT.**

### Phase 1 — The network ledger, floors and labels *(Mon am; minimum shippable 6b)*
- **Objective:** make the eight network counts first-class, validated, honestly-labelled settings —
  with no UI and no new persistence.
- **Eight `Setting` rows** in `ledger.py`, with `reach` **derived, not declared**: seven
  `UNCONDITIONAL`, `lines_per_plant` `INERT`. Extend the existing derived-equals-declared test to cover
  them, so a generator change that makes `production_lines.csv` load-bearing fails the build.
- **Floors and ceilings** (decisions 4, 5, 6) as new validation codes with refusal sentences that quote
  the measured reason — *"a network with no distribution centers scores 68,565.25 at 92.01% fill,
  better than baseline on both, because the optimizer has no per-node capacity. That is a limit of the
  model, not a fact about your network."*
- **The two honesty classes** (§1.2) carried in the payload, not hard-coded in the UI — same discipline
  as 6a's `cannot_change_the_answer` block.
- `is_network_key` stops meaning "refuse" and starts meaning "validate as a network setting"; the
  `excluded_from_6a` payload block becomes the network tier's descriptor.
- **DoD:** all five crashing values refused with a sentence a planner can act on, asserted by test ·
  `DC=0` and `suppliers=0` refused with the measured reason · `lines_per_plant` classified inert by
  derivation · `make scenario-eval` extended and green · **no persistence or execution change in this
  phase** · all 12 objectives still bit-identical.
- **⏹ STOP / CHECKPOINT.**

### Phase 2 — Network keys through synthesis, preview and save *(Mon pm)*
- **Objective:** a network-edited config saves, generates, runs and reopens — reusing 6a end to end.
- Network keys flow through `complete_config`, `POST /scenarios/custom/preview` (diff, estimate,
  reachability) and `POST /scenarios/custom`. `store.py` should need **no change**; if it does, that is
  a finding worth writing down.
- **The run estimate must be recomputed, not inherited.** 6a's estimate assumes baseline's topology;
  a 40-customer network has more series and a longer forecast (§1.4 measured 9,568 demand rows). Reuse
  `_recorded_latencies`' honest posture: no run on record → conservative default, never an invented
  figure.
- **DoD:** save a 1-DC dataset, reopen it, run it, get **81,663.11**; delete it and confirm all three
  artifacts go · a resized dataset (7 customers) runs and its result is **labelled not-comparable** ·
  the dataset view renders it, change list included, **with no dataset-code changes**, and its
  one-sentence summary reads correctly for a 1-DC network (§1.6) · `NetworkMap` visibly redraws · the four canonical names still refused · 12 objectives bit-identical.
- **⏹ STOP / CHECKPOINT.**

### Phase 3 — The UI: a Network group *(Tue am)*
- **Objective:** what Ryan clicks.
- A **Network** group in `CustomScenarioPanel.tsx` — add a group, do not restructure a 28 KB component
  two days before a demo.
- The three label classes rendered distinctly (§1.2): live controls, "resizes the problem" controls
  with their caveat, and `lines_per_plant` under the existing inert heading.
- Floors and ceilings surfaced as control bounds **and** as refusals, so the honest reason is reachable
  even when the control cannot reach the value.
- **DoD:** works in a real browser · `make web-check` extended (build a 1-DC dataset → run → read the
  not-a-resilience-test note → save → reopen → delete) · Vitest for the label classes · no console
  errors · bundle delta recorded · `NetworkMap.tsx` **untouched**.
- **⏹ STOP / CHECKPOINT.**

### Phase 4 — Regression, demo guide & handoff *(Tue pm)*
- Full sweep: `make test`, `make scenario-eval`, `make web-test`, `make web-check`, **`make bench-all`
  bit-identical**, plus Iterations 4, 5 and 6a surfaces and every replay path unbroken.
- **`DEMO_GUIDE.md`**: extend Option E rather than adding an Option F — it is one panel (decision 10) —
  with the "reduce a warehouse" beat and the honest note said **out loud**, not just displayed.
- 6b handoff in house style, with the §5 limits: node counts move <1% and never change service, the
  node-capacity gap, no row-level editing, resized problems are not comparable, single-user storage.
- Ryan packet: **§4.1 first**, then the eleven open questions on one page.
- **DoD:** a cold reader can drive it from the guide · every number traces to a real run · **the
  Wednesday talk track re-read aloud** with the new material in it.
- **⏹ STOP / CHECKPOINT.**

### Phase 5 — 🔴 Post-demo handoff *(Thu–Fri, after the meeting)*
**Features stop on Tuesday. These two days are continuity.**
- Ryan's answers from Wednesday written into the journal **the same day**, while they are fresh.
- A "picking this up" document: what is where, what is deferred and why, what to do next in what order,
  and the four measured facts a newcomer would otherwise rediscover the hard way (single-period
  capacity read · no node in the routing LP · the 15 scenario settings that cannot change the answer,
  plus `lines_per_plant` making 16 · positional entity IDs).
- Final journal entry and snapshot rewrite so the top of the ledger is true on the last day.
- **DoD:** someone who has never seen this repo can find the state of play in under ten minutes.

### Deferred — beyond 6b
**A true GPU-free replay path for Option E** — deliberately traded for a screen recording on this
timeline (Phase 0), not overlooked; Iterations 4 and 5 both have one and 6a should eventually match
them · Row-level entity editing with cascade repair (§1.5) · the four default scenarios re-run on a custom
network (decision 11) · 🔴 **node capacity in the LP (§4.1)** · lane capacity across the horizon
(question 6) · real customer-data onboarding, multi-tenant isolation, per-tenant quotas, packaging.

---

## 6. Risks

| Risk | Mitigation |
|---|---|
| 🔴 **The box misbehaves on Wednesday and Option E has no fallback** | Phase 0, first, never cut (§0.2). Three NVML detachments on record and `llm` is still stale. Bought with a **screen recording**, not a replay build — the cheap fix covers the same failure and leaves the half-day for 6b |
| 🔴 **Ryan sets DCs to 0 and sees a better, cheaper network** | Floored at 1 with the measured reason quoted (decision 4). If he asks why, §4.1 is the answer and it is a strength, not a fumble |
| 🔴 **A 25% objective drop from a product-count change is read as a 25% improvement** | Guardrail 4 and §1.2's second class: resized problems are labelled not-comparable, and the screen leads with the within-run naive-vs-classical figure |
| **A stack trace in front of the sponsor** | Phase 1 floors all five crashing values before anything is written (§1.3) |
| **`customers = 0` passes generation and dies in the forecast** | Same floor, and it is the case that proves floors belong *before* the write, not after |
| **The recorded objectives move** | The optimizer, objective function and generator are untouched (guardrail 2); `make bench-all` at every checkpoint |
| **Two days is not two days** | §0.6's cut line, decided in advance; Phase 1 alone is a shippable, honest answer to Ryan's sentence |
| **Restructuring a 28 KB panel under time pressure** | Decision: add a group, do not refactor (Phase 3) |
| **`NetworkMap.tsx` regressions** | Do not touch it. A count change makes it redraw on its own, which is the demo beat |
| **The estimate is inherited from baseline's topology and lies on a big network** | Phase 2 recomputes it; no run on record → conservative default, never invented |
| **The consolidated modelling finding gets cut on Tuesday night** | It is a **Phase 0** deliverable precisely because it needs no code and matters most |
| **The last two days go on features instead of handoff** | Phase 5 exists and is named. Whatever is not written down on Friday is gone |

---

## 7. Why this is worth building

Ryan asked for two things. 6a delivered the first and this delivers the second, in his own words — a
planner can reduce a warehouse, resize a customer base, restructure a bill of materials, run the real
optimizer, and save the result.

But the more valuable half is what building it measured. Four separate oddities recorded across three
iterations — a capacity read at one period, an inert throughput setting, a lane family whose loss
*saves* money, and now a warehouse that is free — turn out to be one gap: **the optimizer routes
between lanes and has no concept of a node.** Nobody knew that at the start of this week, and it is
exactly the kind of thing a prototype exists to find out. It converts "make the scenarios more
intuitive" into a specific, costed, evidenced engineering decision about what to model next.

That is the difference between a demo that shows what was built and a demo that tells the sponsor
something they did not know about their own product. With two days left, the second is the better thing
to walk in with.

---

*Iteration 6b. Vertical: Manufacturing. Predecessor: Iteration 6a (custom scenario), merged `ad17cc5`.
Written 2026-08-21 against `main` @ `262c498`; every number in §0.3 and §1 came from an on-device run
that day. Demo: Wednesday 2026-08-26. Internship ends Friday 2026-08-28.*
