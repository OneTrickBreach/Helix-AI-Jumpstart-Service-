# Iteration 6a — Plan of Action: Custom Scenario ("Build your own scenario")

**Prepared for:** Ryan Spurr | Helix, Connection Inc.
**From:** Ishan (AI Intern)
**Status:** 🔴 **PLANNED, NOT STARTED.** Written 2026-08-20 against a re-verified live stack. No code
has been written. Phases are runnable one per session.
**Branch:** `feat/iteration6a-custom-scenario`, to be cut from `main` @ `cd3905f` (see Phase 0).
**Predecessor:** Iteration 5 (Beta) — conversational analyst. Built, verified, merged to `main` as
`bc42bb3` on 2026-08-05; handoff at
[`iteration-docs/AI_Jumpstart_MVP_Iteration5_handoff.md`](iteration-docs/AI_Jumpstart_MVP_Iteration5_handoff.md).
**Origin:** Ryan's demo review of **2026-08-19** — his first look at Iterations 4 and 5. He liked the
dataset view (the **network map** most of all), parked the chat bot as-is, and asked for two things:
**a custom scenario** and **a custom dataset**. This plan is the first of those.
**Objective:** let a planner build their own scenario by moving controls over the settings that
already define the four shipped scenarios, run the **real** pipeline on it, and save it so it comes
back next time — with every control honest about whether it can actually change the answer.

---

## 0. Read-First

### 0.1 🔴 Why this is "6a", and what the deadline costs

Ryan asked for custom **scenarios** and custom **datasets**. He also said the dataset one looks hard,
and asked to see the scenario one first. So Iteration 6 is split:

- **6a — Custom Scenario (this plan).** Change the *conditions* applied to an existing dataset.
- **6b — Custom Dataset (deferred).** Change the *network itself* — the thing that makes "just remove
  a warehouse" possible. Deferred on Ryan's own sequencing, **not dropped**.

**The hard constraint is time: Ishan's internship ends approximately 2026-08-27.** That is roughly one
working week from this plan. Every previous iteration in this repo ran one phase per session with a
brutal-truth review at each checkpoint, and that protocol is what has repeatedly caught real defects —
it is not being dropped. What changes is that this plan carries an explicit **cut line** (§0.6) that
says, in advance, what ships if the days run out. Deciding that now is much better than discovering it
on the last afternoon.

### 0.2 The one architectural decision that makes this cheap

> ### The four shipped scenarios are already **data, not code**.
>
> `data/scenarios/*.yaml` is a complete, declarative description of a scenario — **59 editable
> settings across 7 groups**, plus two on/off switches (whether a demand shock and a lane disruption
> exist at all). `data/generator/generate.py` turns one of those files plus a seed into the nine CSVs
> the pipeline reads. The four scenarios differ *only* in those values.
>
> **Therefore a "custom scenario" is a new YAML file, and nothing else.** The generator is not
> modified. The optimizer is not modified. The forecast is not modified.

That single fact carries most of this iteration:

- **The four recorded objectives cannot move.** Not "should not" — *cannot*, because no code that
  produces them is touched. §5 Phase 0 captures them anyway, and every checkpoint re-checks.
- **The dropdown populates itself.** `known_scenarios()`
  ([`src/dataset/overview.py:112`](../src/dataset/overview.py#L112)) and the `_scenario_configs()` helper behind
  `GET /scenarios` ([`src/api/pipeline.py:124`](../src/api/pipeline.py#L124)) already **union** the YAML configs on disk
  with the generated data directories. A saved custom scenario appears in both with **zero new
  discovery code**.
- **The "what did I change?" panel already exists.** `_scenario_diff`
  ([`overview.py:766`](../src/dataset/overview.py#L766)) computes config deltas by comparing a
  dataset's own `metadata.json` against `baseline`'s ([`:820`](../src/dataset/overview.py#L820)), and every generated dataset embeds the exact
  config that produced it. A custom scenario gets a change list against `baseline` for free.
- **Everything is already parameterised by `(scenario, data_root)`** — `load_scenario_state`, the
  dataset overview, the chat facts bundle. A custom scenario is a name, not a refactor.
- **The run path already accepts a non-canonical run.** `run_head_to_head` takes `state=`,
  `forecast=`, `include_ppo=` and `write_artifact=`
  ([`src/pipeline/bench.py:33`](../src/pipeline/bench.py#L33)) — four keywords added in Iteration 5 for
  exactly this class of caller.
- **Persistence is a bind mount.** `./data:/app/data` is mounted into `api`, so a saved scenario
  survives container restarts with no database and no new service.
- ⚠️ **But `data/generated/` is `root:root`** on the host — the container created it. The API writes as
  root inside the container, so save and delete work; a developer clearing things up *from the host*
  needs `sudo`. Every `make` target already goes through `docker compose exec`, so nothing in the
  documented workflow breaks. Worth knowing before it looks like a bug.

### 0.3 What this iteration IS / IS NOT

**IS:** a control panel over the settings that already define a scenario · Simple and Advanced tiers ·
a real run of the real pipeline on the result · save / load / delete / clear-all, persisted on the box
· honest labelling of which controls can and cannot change the answer.

**IS NOT:** not a network editor (no adding or removing suppliers, plants, DCs, customers or products
— that is **6b**) · not row-level data editing · not a change to the optimizer's modelling (see
decision 4 and §1.3) · not real customer data (**Iteration 6b/6**) · not a change to the chat surface,
which Ryan explicitly parked · not a replacement for the benchmark — the four shipped scenarios remain
the recorded comparison and their numbers stay bit-identical.

### 0.4 Carry-forward guardrails (unchanged)

PPO evaluated-not-shipped and kept visible · naive baseline is the legitimate target and a tuned
classical does not collapse · `~94%` is a baseline-collapse artifact, never a flat saving ·
improvement % is vs. the naive baseline and the caveat stays on the results screen · bandwidth
(~273 GB/s) not capacity is the binding constraint · no hospital service-level claim · data never
leaves the box · prompt injection flagged, never executed · every number traces to a real run · the
LLM narrates and never calculates.

### 0.5 🔴 New guardrails introduced by this iteration

1. **No no-op controls.** A control that cannot change the optimizer's answer must not be presented as
   if it can. §1.4 identifies **13 of the 59 settings** that do not reach the optimizer at all. They
   are either excluded or explicitly marked *"recorded in the dataset, not read by the optimizer."*
   This is the Iteration 5 §1.2/§1.3 lesson applied to a slider: a lever that silently does nothing is
   worse than no lever.
2. **A custom result is labelled as custom, everywhere.** A custom scenario's numbers must never be
   quotable as one of the four recorded benchmark results. Same discipline as the Iteration 5 what-if
   card, and the naming scheme (decision 3) makes it visible in the payload, the filename and the URL.
3. **The four canonical scenarios are immutable.** Their names are reserved and refused. Their config
   files, their generated data and their benchmark artifacts are never written by any 6a code path,
   and a test asserts it.
4. **Reproducible or it does not ship.** A saved scenario re-run must return the same objective to the
   cent. The seed is part of the saved config, not ambient.
5. **Validate before generating, generate before running.** An infeasible configuration is refused in
   plain English *before* anything is written or any compute is spent — never a 500, never a garbage
   objective.
6. **Deleting is as first-class as saving.** Delete-one and clear-all both ship in the same phase as
   save. A feature that can only accumulate state is not finished.

### 0.6 🔴 The cut line, decided in advance

If the week runs short, ship in this order and stop wherever it stops. Each line is independently
demoable.

| # | Slice | Status if reached |
|---|---|---|
| 1 | Simple tier (8 controls), run, results on screen | **Minimum shippable.** This is the demo Ryan asked for. |
| 2 | Save / load / delete / clear-all | **Target.** This is what he explicitly asked for ("name this scenario and save it"). |
| 3 | Advanced tier (all 59 settings) | **Target.** His course-registration analogy. |
| 4 | No-op labelling + the capacity-window warning | **Non-negotiable — ships with slice 1**, because it is a correctness guardrail, not a feature. |
| 5 | Handoff doc, demo-guide section, screenshots | **Required to call the iteration done.** Reserve the last session for it. |
| 6 | Custom scenarios inside the chat surface | **Explicitly out.** Regression-tested only (decision 12). |

Slice 4 is listed after 3 but ships first; it is called out separately because it is the one thing a
reviewer might mistake for polish.

---

## 1. 🔴 What building Iterations 4 and 5 discovered that changes this plan

Measured facts about *this* codebase, re-verified on-device on **2026-08-20** while writing this plan.
Each one would have cost a phase if found mid-build. **Read this section before Phase 1.**

### 1.1 Generation is effectively free, so "save then run" is a sub-second loop

Measured on the GB10 today, `data/generator/generate.py` into a scratch directory:

| Scenario | Generation |
|---|---:|
| `baseline` (17 locations, 30 lanes, 2,912 demand rows) | **0.23 s** |
| `stress-large` (42 locations, 152 lanes, 44,928 demand rows, 104 periods) | **0.55 s** |

And the run, measured today with `write_artifact=False` (no artifact written, so no side effects):

| Step | `baseline`, horizon 8 |
|---|---:|
| Forecast (**32** finished-good series → 256 rows at horizon 8) | **0.83 s** |
| Baseline + classical comparison, warm forecast | **0.17 s** |
| Same, **with** PPO at 128 timesteps | **2.82 s** |
| LLM advisory rationale (`llm_finalized`, 5 citations) | **20.1 s** |

The classical objective came back **81,789.359460** — bit-identical to the recorded value, through a
code path that loads state and forecast explicitly. That is the determinism this iteration depends on,
re-demonstrated rather than assumed.

**Consequence for the design:** a custom scenario can be generated and compared in **~1.2 s** without
PPO, ~4 s with it. The LLM rationale is **~20× the cost of the entire numeric comparison** — 20.1 s
against 1.0 s of forecast plus compare. That drives decision 8.

### 1.2 The fairness invariant is already true — proven, not assumed

The generator seeds its RNG with `np.random.default_rng(effective_seed)`
([`generate.py:644`](../data/generator/generate.py#L644)) — **the scenario *name* is not part of the
seed.** It reaches the builders only as a provenance column.

Verified today rather than reasoned about: `baseline`'s config was written out under the name
`custom-probe`, generated with seed 12345, and compared against `baseline`'s own generated data.

- **All nine tables byte-identical** with the provenance `scenario` column dropped.
- Classical objective **81,789.359460** — the recorded value, to the digit.

So a custom scenario that changes nothing reproduces the recorded run exactly. **Phase 3's fairness
invariant is therefore known to be achievable before any code is written**, which is a much better
position than Iteration 5's equivalent invariant started from. The probe also confirmed two Phase 2
mechanics for free: `generate()` is importable and callable in-process, and generating into an
arbitrary directory then loading it with `data_root=` works.

### 1.3 🔴 Lane capacity reaches the optimizer at exactly ONE period — and both shipped disruptions miss it

`src/optimize/common.py:53` and `:128` filter `lane_periods` to `period == state.horizon()`, where
`horizon()` is `max(demand.period)`. Every other period's capacity is present in the CSV and never
read. Audited today across the shipped scenarios:

| Scenario | Capacity read at period | Disrupted lane-periods | Spanning | Disrupted **at the read period** |
|---|---:|---:|---:|---:|
| `baseline` | 52 | 0 | — | — |
| `component-shortage-shock` | 52 | 20 | periods **18–27** | **0** |
| `stress-large` | 104 | 64 | periods **38–53** | **0** |

**Both shipped scenarios that carry a lane disruption have a disruption the optimizer never sees.**
`component-shortage-shock` scores 95,445 rather than baseline's 81,789 because of its *other* config
deltas, not because two inbound lanes go to zero for ten weeks. The Iteration 5 handoff states this for
`component-shortage-shock`; **nobody had checked `stress-large`, and it is the same story.** That is a
new finding from writing this plan and belongs in the journal.

**Why it becomes urgent now.** Iteration 5's chat layer got away with it: an unqualified *"what if
DC-001 goes down?"* takes the full period range, covers the read period, and returns real numbers — and
a narrow window produced an amber *"Do not read this as resilience"* card explaining the mechanism. A
slider has no such escape hatch. A user drags a disruption window into the middle of the year, waits,
and sees numbers identical to baseline.

**Scope of the problem, precisely.** It is narrower than "capacity controls":

- **`lane_disruption` (7 settings) is the only affected group.** It writes a *windowed* multiplier into
  `lane_periods.csv`.
- **`capacity.capacity_tightness` is safe** — it scales lane capacity at *every* period, including the
  read period.
- **All demand controls are safe** — they are baked into `demand.csv`, and the forecast reads the whole
  history.
- **All cost and service-target controls are safe** — they land in `skus.csv` and
  `service_targets.csv`, which are read without a period filter.

🔴 **And the read period is itself a lever.** `build_lane_periods` writes capacity for periods
`1..config["simulation"]["horizon_periods"]`, and the optimizer reads at `max(demand.period)` — so
**`simulation.horizon_periods` (an Advanced control) moves the read period.** Set it to 26 and a
disruption over periods 18–27 suddenly *does* bite. The warning in decision 4 must therefore compute
the read period from the configuration the user is editing, **never from a hardcoded 52.** This is the
easiest thing in the whole iteration to get quietly wrong.

Handled by decision 4. **The optimizer is not being changed in this iteration.**

### 1.4 🔴 Thirteen of the fifty-nine settings cannot change the answer at all

The optimizer and forecast read six of the nine tables: `demand`, `lanes`, `lane_periods`, `skus`,
`initial_inventory`, `service_targets`. **`nodes`, `bom` and `production_lines` are never read by the
forecast or the optimizer** — the Iteration 5 §1.3 finding, re-verified today.

🔴 **But they *are* read by the dataset view** (`nodes` 3×, `bom` and `production_lines` once each in
`src/dataset/`) — that is what draws Ryan's favourite screen, the network map. So the inert settings
below are not inert *everywhere*: they visibly change the dataset page and then fail to change the
answer, which is a nastier failure than doing nothing at all. It is also exactly why decision 15's
label is *"recorded in the dataset, not read by the optimizer"* rather than *"has no effect"*.

Traced through the generator, the inert settings are:

| Setting | Lands in | Why it is a no-op |
|---|---|---|
| `capacity.plant_storage_periods` | `nodes.csv` `storage_capacity_units` | `nodes.csv` is never read |
| `capacity.supplier_capacity_units_per_period` | `nodes.csv` | ” |
| `capacity.supplier_storage_units` | `nodes.csv` | ” |
| `capacity.dc_throughput_units_per_period` | `nodes.csv` | ” |
| `capacity.dc_storage_units` | `nodes.csv` | ” |
| `capacity.customer_storage_units` | `nodes.csv` | ” |
| `lanes.*.lead_time_std_days` (×3 families) | `lanes.csv` | column not consumed by the optimizer |
| `lanes.*.co2_kg_per_unit` (×3 families) | `lanes.csv` | ” |
| `service_targets.criticality_tier` | `service_targets.csv` | only `fill_rate_target` and `days_inventory_target` are read |

**`dc_throughput_units_per_period` is the dangerous one.** It reads exactly like "how much this
warehouse can handle" — the most intuitive thing on the whole panel — and it does nothing. Shipping it
as a live slider would be the single most misleading thing in this iteration.

**The settings ledger, then:**

| Reach | Count |
|---|---:|
| Changes the optimizer's answer, unconditionally | **39** |
| Changes it **only if the window covers the capacity read period** (`lane_disruption`, 7 settings) | **7** |
| Cannot change it (the table above) | **13** |
| **Total editable settings** | **59** |
| Excluded because they are the dataset layer (`network.*` → 6b) | 8 |

Phase 1 must reproduce this ledger as a committed, machine-checked table. If a future generator change
makes `nodes.csv` load-bearing, the test should fail and the labels should change.

### 1.5 The generator has no defaults — a saved config must be complete

`load_scenario(name)` reads **only** `data/scenarios/<name>.yaml`, requires the file's `scenario:` key
to equal the filename stem, and then indexes straight into `config["demand"]`,
`config["capacity"]["capacity_tightness"]` and friends. There is **no defaults merge and no schema**.

So a saved custom scenario must be written as a **complete** config — baseline's values with the user's
overrides applied — not a sparse patch. That is a feature, not a chore: the saved file is then a
first-class scenario indistinguishable in kind from the four, it works with `make data
SCENARIO=custom-x`, and `metadata.json` embeds it so `scenario_diff` can diff it.

Also: `load_scenario` reports every error by raising `SystemExit`. Calling it in-process from the API
would take down the request handler in a way FastAPI cannot render. **Validate before calling the
generator, and never let a `SystemExit` cross the API boundary.**

### 1.6 The `network:` block is the dataset layer, and must stay out of 6a

The same YAML holds both layers. `network.{suppliers, plants, lines_per_plant,
distribution_centers, customers, finished_goods, subassemblies_per_finished_good,
raw_components_per_subassembly}` — 8 settings — are what "remove a warehouse" would change, and the
generator builds entities purely from those counts with positional IDs (`DC-001 … DC-00n`,
[`generate.py:453`](../data/generator/generate.py#L453)).

**They are excluded from 6a.** Two reasons. First, exposing them would quietly turn 6a into 6b, the
thing Ryan sequenced second. Second, count changes are the ones that need cascade validation (a
customer with no serving lane, a network with zero DCs) and a feasibility pre-check — the expensive
engineering 6b exists to do properly.

Worth recording for 6b: because IDs are positional, *reducing* a count is equivalent to deleting the
**last** entity. "2 DCs → 1" is expressible; "delete `DC-002`, keep `DC-003`" is not, and needs the
row-level overlay layer.

### 1.7 The four scenarios are hardcoded where it matters, and that is a safety property

`make demo-data` and `make bench-all` iterate a **literal list** of the four
([`Makefile:98`](../Makefile#L98), [`:184`](../Makefile#L184)), and `src/bench/suite.py:18` defines
`SCENARIOS` as a literal 4-tuple. **Custom scenarios therefore cannot leak into `bench-all` or
`demo-data`**, and `benchmark/suite-summary.json` cannot be polluted by one. This is asserted, not
built.

The one place that *is* dynamic is `GET /scenarios` — which is exactly what we want for the dropdown.
And `tests/test_phase5_api.py:130` checks the four with `.issubset(names)`, so extra entries do not
break it. Verified by reading the assertion, not assumed.

### 1.8 What Iterations 4 and 5 hand over that this must not rebuild

| Asset | Use it for |
|---|---|
| `GET /dataset/overview` — 13 deterministic sections | The custom scenario's dataset page, unchanged |
| `scenario_diff.config_changes` — diffs `metadata.json` vs `baseline`, cap **200** rows so 59 settings cannot truncate | The "here is what you changed" panel, for free |
| `NetworkMap.tsx` / `LanesTable.tsx` / `DemandChart.tsx` / `ProductTree.tsx` | The custom scenario's dataset view — **Ryan's favourite screen; do not touch it** |
| `GET /scenario-comparison/stream` + the truthful SSE stepper | Running a custom scenario with real progress. Do not build a second progress path |
| Iteration 5's confirm-card pattern (reading, estimate **with its basis**, seed, fixed inputs) | The pre-run card for a custom scenario |
| Iteration 5's `reaches_optimizer` and `capacity_read_period` fields ([`perturbation.py:112`](../src/chat/perturbation.py#L112)) and the amber *"Do not read this as resilience"* block | The capacity-window warning (decision 4) — reuse the field names and the wording rather than inventing a second vocabulary for the same fact |
| `_recorded_latencies` ([`pipeline.py:163`](../src/api/pipeline.py#L163)) — returns `{}` rather than inventing a figure | The run estimate for a scenario with no run on record |
| `_resolve_scenario_dir` containment check + `test_no_path_traversal_via_scenario` | The model for custom-name validation (§ decision 3) |
| `make web-check` — 26 headless-Chromium checks | Extend it. Do not start a new harness |
| `make test` writes to `HELIX_BENCHMARK_DIR` via a session fixture | Why the suite cannot clobber recorded artifacts. Keep it that way |

---

## 2. Decisions

Made under delegated authority on **2026-08-20**, with Ryan's 2026-08-19 review in hand. Items marked
**↩︎ revisit** are ones to put back in front of him.

| # | Decision | Call | Rationale |
|---|---|---|---|
| 1 | Scope | **6a only — custom scenario. Custom dataset is 6b.** | Ryan's own sequencing on 2026-08-19: he called the dataset one hard and asked to see scenarios first. |
| 2 | What a custom scenario *is* | **A complete scenario YAML plus its generated data** | §0.2/§1.5. No new format, no new storage engine, no generator change. |
| 3 | Naming and namespace | **`custom-<slug>`**, slug `^[a-z0-9][a-z0-9-]{0,39}$`; config at `data/scenarios/custom-<slug>.yaml`, data at `data/generated/custom-<slug>/`; the four canonical names **reserved and refused** | The prefix does four jobs: a `.gitignore` pattern that keeps saved scenarios out of git; collision protection for the name-keyed benchmark artifact; a visible marker in the dropdown and the URL; and a safe `clear-all` selector. |
| 4 | 🔴 The capacity read period | **Do NOT change the optimizer.** `lane_disruption` windows default to *running to the end of the horizon*; narrowing one so it excludes the read period raises a **pre-run** warning naming the period, with an "extend to the end" action; the payload carries `reaches_optimizer: false` | ↩︎ revisit — **this is question 6 from the Iteration 5 packet and it is now Ryan's to answer.** Widening the read would move **every objective in every document he saw yesterday**. Not doing that in the same week he first saw them. §1.3. |
| 5 | Control tiers | **Simple (8 grouped controls) and Advanced (all 59 settings)**, one form, disclosure between them | Ishan's call, 2026-08-20, on Ryan's course-registration analogy: simple search by default, advanced filters behind a click. 59 sliders is a wall; 8 is a control panel. |
| 6 | The `network:` block | **Excluded from 6a** | §1.6. Exposing it makes 6a into 6b. |
| 7 | Seed | **Part of the saved config**, default 12345, editable in Advanced only | Guardrail 4. A saved scenario that cannot be re-run to the same number is not saved. |
| 8 | What a run computes | **Default: baseline + classical, no PPO, no LLM rationale.** Both available as explicit opt-ins. PPO reports `ppo_outcome: not_evaluated` when off, and **the rationale is returned as a real object carrying an explicit "not generated for this run" marker — never `null` and never omitted** | §1.1: the numeric comparison is 0.17 s and the rationale is 20.1 s. The lever loop must be *drag → run → see → adjust*; a 20-second narration per iteration kills it. The `not_evaluated` convention already exists in `run_head_to_head`. **The placeholder is not politeness:** `ResultsView`, `PlanSummary` and `RationalePanel` in `web/src/App.tsx` take `rationale` as a **required** prop and dereference `rationale.advisory_rationale` and `rationale.prompt_injection_flags`, so a `null` would break the results screen for the four shipped scenarios too. Name the flag `use_llm` to match the existing chat requests. |
| 9 | Run path | **Reuse `POST /scenario-comparison` and its SSE stream**, extended with the opt-out flags | Decision 9 of Iteration 5, still right: one truthful progress path, not two. |
| 10 | Benchmark artifacts | **A custom run writes `benchmark/custom-<slug>-head-to-head-comparison.json`** — name-keyed, `.gitignore`d, and asserted never to touch the four | Consistent with what the results page already does for the four (a UI run on 2026-08-19 rewrote `component-shortage-shock`'s artifact and reproduced its objective to the digit). It also makes `_recorded_latencies` and the chat facts bundle work on custom scenarios at no cost. |
| 11 | Validation posture | **Validate → refuse in plain English → only then write.** Range-check every setting, cross-check windows against the horizon, and run a feasibility pre-check before generating | Guardrail 5. A slider that produces a 500 is worse than a slider that says why it refused. |
| 12 | The chat surface | **Untouched.** Custom scenarios will be *visible* to it via `known_scenarios()`; that path gets a **regression test**, not a feature | Ryan explicitly parked the chat bot on 2026-08-19. Do not build for it, do not claim it, do not let it break. |
| 13 | Delete semantics | **Delete-one** removes config + generated dir + benchmark artifact for that slug; **clear-all** operates only on the `custom-` prefix; both refuse the four canonical names | Guardrail 6, and Ryan asked for the clear button by name. |
| 14 | Multi-user | **Single-user, box-global.** Saved scenarios are visible to anyone who can reach the box | No auth beyond the shared API key exists. State it in the handoff; real per-user state is the production track. |
| 15 | No-op settings | **Excluded from Simple; shown in Advanced under an explicit *"recorded in the dataset, not read by the optimizer"* heading** | §1.4, guardrail 1. Hiding them entirely would be dishonest about what the dataset contains; showing them as live controls would be worse. |

---

## 3. EXECUTION PROTOCOL

Unchanged from Iterations 3, 4 and 5. It has repeatedly caught real defects — keep it, deadline or not.

- **One phase per session.** Do its tasks, meet its DoD, then **STOP** and wait for an explicit go.
- At every checkpoint, in order: **brutal-truth review** (assume something is wrong; go find it; fix
  real defects) → **commit** → **journal entry** (newest at TOP) → **report** → wait.
- **Rebuild after edits:** `src/` is baked into the `api` image via `COPY`, not bind-mounted —
  `docker compose build api && docker compose up -d --no-deps api`. Web:
  `docker compose build web && docker compose up -d --no-deps web`. `data/` **is** bind-mounted, so
  saved scenarios need no rebuild.
- **Verify with real runs**, never a build log. For UI, `make web-check` **and** a real browser.
- **Web tests run from the committed lockfile** (`npm ci` in a scratch container) — the host
  `web/node_modules` is stale and will silently use the wrong vitest.
- **🔴 If a container has been up for days, check GPU reporting before trusting anything.** NVML
  detaches from long-running containers on this box; it had broken again by 2026-08-20 (§5 Phase 0).
  The fix is `docker compose up -d --no-deps --force-recreate api`.
- Stop and report on any guardrail conflict. Do not work around it.

---

## 4. Questions for Ryan

Three are new; the fourth is his outstanding one, which this iteration makes urgent.

1. **Is the Simple tier the right eight controls?** Demand level · demand spike · capacity tightness ·
   lane disruption · inventory holding cost · missed-order penalty · transport cost · fill-rate target.
   That is a planner's vocabulary as read off the shipped configs — but he is the one who talks to
   planners.
2. **Should a saved scenario be shareable/exportable?** Today it lives on the box and is visible to
   anyone who can reach it (decision 14). A "download this scenario as YAML" button is cheap; anything
   more is the production track.
3. **Should a custom run include the written rationale by default?** It is 20.1 s of the ~21 s total
   (decision 8). Off by default makes the loop feel instant; on by default makes a custom scenario look
   exactly like one of the four.
4. 🔴 **The capacity read period — his question 6, now with sliders attached.** Today the optimizer
   reads lane capacity at one period, so a narrow disruption window is a genuine no-op, and **both
   shipped disruptions are already invisible to it** (§1.3 — new evidence since the last packet).
   Decision 4 warns rather than widens. Widening it is a modelling change that moves every recorded
   objective. **His call.**

---

## 5. Phases

### Phase 0 — Orientation, green baseline & branch
- Read `README.md`, the journal (newest first), this plan, the Iteration 5 handoff and plan,
  `.devin/rules/helix-sco.md`.
- **🔴 GPU first.** On 2026-08-20 both `api` and `llm` reported `Failed to initialize NVML: Unknown
  Error` after 2 weeks up, with `/health` `gpu_visible:false` — while compute still worked off
  already-loaded CUDA contexts. `api` was fixed with
  `docker compose up -d --no-deps --force-recreate api` and verified: `nvidia-smi` in-container,
  `/health` → `gpu_visible:true, gpu_name:"NVIDIA GB10", driver_version:"580.159.03"`,
  `torch.cuda.is_available()` → `True`, `nomic-embed` on `cuda:0` at 768 dim, and the full RAG advisory
  path `llm_finalized` with 5 citations in 20.1 s. **`llm`'s own NVML is still stale** — it serves
  fine, but a restart would not re-see the GPU. Recreate it in a window before the demo, accepting the
  ~10-minute Nemotron reload.
- `make test` (**expect 347 passed + 2 xpassed**) → `make bench-all` (**expect 81,789.359460 /
  95,445.445064 / 94,165.363245 / 2,521,615.068565**) → `make web-test` (**expect 62**) →
  `make web-check` (**expect 26/26**).
- **Read the xpassed count, not just "passed".** The 2 xpassed are `test_gpu_visible` and
  `test_driver_version`, `xfail`-marked because of this very NVML issue. **If they report `xfailed`
  instead, the GPU fix above has not taken** — and the suite will still say "passed" overall, so this
  is the field that tells you. Re-verified today after the recreate: `tests/test_service_health.py`
  → **2 passed, 2 xpassed**.
- Confirm the Iteration 4 and 5 surfaces are intact: `?view=dataset`, `?chat=true`, and both replay
  paths with the API blocked.
- Cut `feat/iteration6a-custom-scenario` from `main` @ `cd3905f`.
- **DoD:** GPU reporting restored and recorded; all four reference numbers captured in the journal;
  branch cut; the §1.3 `stress-large` finding written into the journal as its own note.

### Phase 1 — The settings ledger, schema & validation *(no persistence, no execution)*
- **Objective:** turn 59 YAML settings into a typed, range-checked, honestly-labelled schema — and
  prove which ones matter.
- **The ledger as a test.** A committed, machine-checked table mapping every setting to the CSV it
  writes and whether the optimizer reads it: **39 unconditional · 7 conditional (`lane_disruption`) ·
  13 inert**. Derived from the optimizer's real column reads, not hand-maintained. **This test failing
  is the signal that a label is now a lie.**
- **Complete-config synthesis** (§1.5): baseline's config + overrides → a full, valid config. Family
  controls (e.g. "transport cost") write concrete per-tier values, so the output is an ordinary
  scenario file with no new schema.
- **Validation:** per-setting ranges and types · window bounds against `simulation.horizon_periods` ·
  the capacity-read-period check producing `reaches_optimizer`, **with the read period derived from the
  edited config rather than a constant** (§1.3) · name validation per decision 3,
  including the reserved four and the `..` case that the existing `^[a-zA-Z0-9._-]+$` pattern permits ·
  a feasibility pre-check. Every refusal is a sentence a planner can act on.
- `POST /scenarios/custom/preview` — returns the resolved config, the diff vs `baseline`, the
  `reaches_optimizer` verdict and the run estimate **with its basis**. Writes nothing, runs nothing.
- **DoD:** a committed settings-ledger test that fails if the optimizer's reads change; a committed
  validation eval set covering every refusal class; **no write path and no execution path exist at this
  checkpoint, asserted structurally** (as Iteration 5 Phase 2 did).
- **⏹ STOP / CHECKPOINT.**

### Phase 2 — Persistence: save, list, delete, clear-all
- **Objective:** a saved scenario is a real scenario, and can be un-saved.
- `POST /scenarios/custom` (validate → write config → generate data → return the summary),
  `GET /scenarios/custom`, `DELETE /scenarios/custom/{slug}`, `DELETE /scenarios/custom` (clear-all).
- Generation in-process via `data.generator.generate.generate(...)`, **guarded** so no `SystemExit`
  crosses the API boundary (§1.5). Confirmed callable in-process by the §1.2 probe.
- **Save is atomic.** `known_scenarios()` unions configs *and* data directories, so a config written
  whose generation then failed would leave a dropdown entry that answers **409** forever. On any
  failure after the config is written, remove it and report the failure — never leave a half-saved
  scenario in the list.
- `.gitignore` gains `data/scenarios/custom-*.yaml` — checked with `git check-ignore` today:
  `data/generated/custom-*/` is **already** covered by `data/**/generated/` and the benchmark artifact
  by `benchmark/*.json`, but a custom **config** is **not ignored** and would show up as an untracked
  file on every `git status`. That one rule is the whole change.
- **DoD:** a saved scenario appears in `GET /scenarios` and renders in the existing dataset view with
  its change list against `baseline`, with **no changes to the dataset code**; delete removes all three
  artifacts; clear-all touches only `custom-`; the four canonical names are refused by save *and*
  delete; **`make bench-all` and `make demo-data` still see exactly four scenarios** (§1.7);
  `make test` still green.
- **⏹ STOP / CHECKPOINT.**

### Phase 3 — Running a custom scenario
- **Objective:** real numbers from the real pipeline, labelled as custom.
- Extend `POST /scenario-comparison` and `GET /scenario-comparison/stream` with `include_ppo` and
  `include_rationale` (decision 8), defaulting to the fast path for custom scenarios and to **existing
  behaviour for the four** — no recorded result changes shape.
- Pre-run card reusing Iteration 5's pattern: what will run, the estimate **and its basis**, the seed,
  what is excluded, and the `reaches_optimizer` warning when it applies.
- **DoD:** the four shipped scenarios' results screen is **unchanged** — same payload shape, rationale
  still generated (decision 8's placeholder path is exercised by a test, not only by custom runs);
  a custom scenario runs end-to-end with truthful SSE stages; **the same saved scenario run
  twice returns the identical objective to the cent**; a custom scenario whose settings equal
  baseline's **reproduces 81,789.359460 exactly** (the fairness invariant, mirroring Iteration 5
  Phase 3 — and already proven reachable in §1.2, so a failure here means 6a broke it); a `lane_disruption` narrowed off the read period is warned about *before* the run and
  explained after; the four canonical artifacts are untouched (md5 before/after).
- **⏹ STOP / CHECKPOINT.**

### Phase 4 — The UI: Simple and Advanced
- **Objective:** the control panel Ryan asked for, on the screen he liked.
- A fifth dropdown entry — **"Custom scenario…"** — opening a panel pre-filled from `baseline`.
- **Simple:** the 8 grouped controls (decision 5). Grouped means one control per idea: "demand spike:
  1.75× for 8 weeks from week 20" is one thing a human says, and it is `demand.shock` underneath.
- **Advanced:** all 59 settings by group, with the 13 inert ones under an explicit *"recorded in the
  dataset, not read by the optimizer"* heading (decision 15). Simple and Advanced stay in sync.
- Name · Save · Delete · Clear all · Run. Saved scenarios appear in the dropdown, grouped and visibly
  `custom-`.
- **Do not touch `NetworkMap.tsx`.** It is Ryan's favourite screen and it needs no change.
- **DoD:** works in a real browser; `make web-check` extended (custom scenario created → run → results
  → deleted, plus the no-op warning path and the inert-settings labelling); Vitest coverage for the
  config synthesis and validation display; no console errors; bundle delta recorded and justified.
- **⏹ STOP / CHECKPOINT.**

### Phase 5 — Regression, docs & handoff
- Full sweep: `make test`, `make web-test`, `make web-check`, **`make bench-all` bit-identical**, plus
  the Iteration 4 and 5 surfaces (dataset view, chat panel, both replay paths) unbroken — including the
  decision-12 regression test that the chat layer neither breaks on nor claims custom scenarios.
- `DEMO_GUIDE.md` **Option E** with a talk track: build a scenario from baseline in front of the
  viewer, run it, read the change list, save it, reopen it.
- Iteration 6a handoff in house style, with an honest limits section: scenario-layer only, no network
  edits, the capacity read period, the 13 inert settings, single-user box-global storage, synthetic
  data.
- Update `README.md`, `docs/handoff.md`, the journal, and draft the Ryan packet with the four §4
  questions.
- **DoD:** a cold reader can drive the feature from the guide; every number in the handoff traces to a
  real run; **a human reads the Option E talk track out loud once** — the definition-of-done item this
  repo has never met, and the one Ishan can still close before leaving.
- **⏹ STOP / CHECKPOINT.**

### Deferred — Iteration 6b and beyond
**6b, custom dataset:** the `network:` block as controls · row-level entity editing (delete `DC-002`
specifically, edit one lane) via an overlay on generated CSVs · cascade and feasibility validation ·
the four default scenarios re-run on a custom dataset · custom scenarios stacked on a custom dataset's
baseline. **Beyond:** real customer-data onboarding, multi-user state, per-tenant quotas, compound
perturbations, cross-scenario comparison, and the rest of the production track.

---

## 6. Risks

| Risk | Mitigation |
|---|---|
| 🔴 **A control that does nothing.** 13 of 59 settings cannot move the answer, and `dc_throughput_units_per_period` reads like the most intuitive control on the panel | §1.4 ledger, enforced as a test; excluded from Simple; explicitly labelled in Advanced (decisions 11, 15). This is the Iteration 5 §1.2/§1.3 lesson, and it is the top risk in this iteration |
| 🔴 **A disruption window that silently no-ops** | Decision 4: default to the full horizon, warn *before* the run, `reaches_optimizer: false`, and reuse Iteration 5's amber wording. A test pins the §1.3 fact so nobody "fixes" it silently |
| **A custom result quoted as a benchmark result** | The `custom-` prefix in the name, the payload, the artifact filename and the URL; the existing improvement-% caveat; a labelled results header (guardrail 2) |
| **The four recorded objectives move** | Structurally impossible — neither the generator nor the optimizer is modified (§0.2) — and checked at every checkpoint anyway with `make bench-all` |
| **A custom scenario leaks into the recorded suite** | `bench-all`, `demo-data` and `suite.py` all iterate literal lists of four (§1.7); asserted, and the artifact is name-keyed |
| **An infeasible configuration returns a 500 or a garbage objective** | Validate-then-generate-then-run, with a feasibility pre-check and plain-English refusals (decision 11) |
| **`SystemExit` from the generator kills a request** | Validate before calling it; guard the call (§1.5) |
| **Path traversal or a name collision via the slug** | Decision 3's slug pattern plus the reserved four; modelled on `_resolve_scenario_dir` and `test_no_path_traversal_via_scenario`, which already exist |
| **The lever loop feels slow** | Decision 8: PPO and the 20.1 s rationale both off by default; the numeric comparison is ~1.2 s cold at baseline size |
| **A large custom demand change makes the run slow** | The forecast is the known ceiling (~25 ms/series); the pre-run estimate states it with its basis, as Iteration 5's card does |
| 🔴 **NVML detaches from long-running containers** | It had already broken again by 2026-08-20 and was fixed in Phase 0. Check `/health` before trusting any GPU-dependent result. `llm` is still stale — recreate it in a window before the demo |
| 🔴 **The capacity warning hardcodes period 52** | `simulation.horizon_periods` is itself a control, and it *moves* the read period (§1.3). Derive it; a test should cover a non-default horizon |
| **The chat surface breaks on a custom scenario** | Decision 12: a regression test, not a feature |
| 🔴 **The week runs out mid-feature** | §0.6's cut line, decided in advance; every slice is independently demoable, and the correctness guardrail ships with slice 1 |
| **Scope drifts into 6b** | Decision 6 and §1.6: the `network:` block is out, and the reason is written down |

---

## 7. Why this is worth building

Ryan's original complaint was that the four scenarios "aren't intuitive". Iteration 4 answered it by
showing what the data *is*; Iteration 5 answered it by letting someone *ask*. Both still leave the
viewer inside four scenarios somebody else chose.

This one hands over the controls. A planner who thinks their real problem is a demand spike in Q3 with
tighter lane capacity can build that, run it on the actual optimizer, and read the answer off the same
screens the shipped scenarios use — in about a second, on a 240 W box on the desk, with no data
leaving it. That is the difference between "here is our benchmark" and "here is your network", and it
is the last thing this prototype needs before the honest question stops being *"is this real?"* and
starts being *"can it run my data?"* — which is precisely 6b, and precisely the right question to be
asked next.

It is also the ask from the sponsor's own review, delivered in the week it was asked for.

---

*Iteration 6a. Vertical: Manufacturing. Predecessor: Iteration 5 (Beta) — conversational analyst.
Successor: Iteration 6b (custom dataset), then the production track. Written 2026-08-20 against a
re-verified live stack; every measured number in §1 came from an on-device run that day.*
