# AI Jumpstart MVP — Iteration 6a Handoff: "Build Your Own Scenario" — the Custom Scenario Panel

**Prepared for:** Ryan Spurr | Helix, Connection Inc.
**From:** Ishan (AI Intern)
**Date:** 2026-08-20
**Branch:** `feat/iteration6a-custom-scenario`
**Predecessor:** Iteration 5 (Beta) — conversational analyst, merged to `main` 2026-08-05 (`bc42bb3`)
**Origin:** your demo review of **2026-08-19** — the first sponsor look at Iterations 4 and 5

---

## TL;DR

You asked for two things on 2026-08-19: **a custom scenario** and **a custom dataset**. You said the
dataset one looked hard and asked to see the scenario one first. This is that one.

Open the **Scenario** dropdown — on the results screen **or on the dataset view**. There is now a
fifth entry, **"Custom scenario…"**. It opens a control panel over the settings that actually define a scenario, pre-filled
from `baseline`. Move a control, name it, click **Save & run**, and the real pipeline runs on it — on
this device, in about a second and a half.

> ### The one architectural fact that made this cheap
> **The four scenarios were already data, not code.** `data/scenarios/*.yaml` is a complete
> declarative description — 59 editable settings across 7 groups — and `data/generator/generate.py`
> turns one of those files plus a seed into the nine CSVs the pipeline reads. The four differ *only* in
> those values.
>
> **So a custom scenario is a new YAML file and nothing else.** The generator was not modified. The
> optimizer was not modified. The forecast was not modified. Which is why the next line is a fact
> rather than a hope.

**Your four recorded results have not moved.** Not "should not" — *cannot*, because no code that
produces them was touched. Re-verified at every one of the six checkpoints:

| Scenario | Baseline | **Classical (winner)** | PPO |
|---|---:|---:|---:|
| `baseline` | 88,022.760795 | **81,789.359460** | 102,804.716650 |
| `component-shortage-shock` | 102,834.785064 | **95,445.445064** | 113,584.863463 |
| `demand-surge` | 100,734.738785 | **94,165.363245** | 115,161.538279 |
| `stress-large` | 2,622,335.215962 | **2,521,615.068565** | 2,867,271.225615 |

And the sharpest test of the whole iteration: **a custom scenario built with no changes at all
reproduces `baseline` to the digit — 81,789.359460.** Same generator, same seed, different name.

---

## 1. What it does

| Capability | Detail |
|---|---|
| **Simple tier** | 8 grouped controls: demand level · demand spike · capacity tightness · lane disruption · inventory holding cost · missed-order penalty · transport cost · fill-rate target |
| **Advanced tier** | All **59** settings by group, behind one disclosure |
| **Run** | The real pipeline — same code path, same screens as the four recorded scenarios |
| **Save / load** | A saved scenario is an ordinary scenario: it appears in the dropdown, renders in the dataset view, and comes back next time |
| **Delete / clear all** | **YOUR SAVED SCENARIOS** is the first block in the panel: a labelled **Delete** per scenario and **Delete all**. Removes the config, the generated data, the recorded artifact and the vector-store collection |
| **Honest labelling** | Every control says whether it can change the answer, and every result says it is not a benchmark result |

**Simple and Advanced are two views of one form.** The panel sends your edits to a preview endpoint;
the server resolves them into one complete config and hands it back; Advanced displays *that*. So a
Simple edit shows up in Advanced with no duplicated logic, and an Advanced edit wins over the Simple
control sharing its setting — which then says *"set in advanced"* rather than showing a slider position
that is a lie.

---

## 2. 🔴 The two things I would most like you to look at

Both are honesty features. Both ship in the first slice, because they are correctness, not polish.

### 2.1 Fifteen of the 59 settings cannot change the answer — and the panel says so

The forecast and the optimizer read six of the nine tables. **`nodes.csv`, `bom.csv` and
`production_lines.csv` are never read downstream** — but they *are* read by the dataset view, which is
what draws the network map. So those settings visibly change the dataset page and then fail to change
the result, which is nastier than doing nothing at all.

They are shown in Advanced under an explicit heading — *"recorded in the dataset, not read by the
optimizer"* — never as live Simple controls, and a change list tags them.

**`capacity.dc_throughput_units_per_period` is the dangerous one.** It reads like the most intuitive
control on the whole panel — how much this warehouse can handle — and it does nothing. Shipping it as a
live slider would have been the single most misleading thing in this iteration.

**The labels were derived, not asserted.** Two independent derivations run against the live system:

1. *What does this setting write?* Build the nine tables twice — once as-is, once with the setting
   moved — and diff the CSV columns.
2. *Does the optimizer read that column?* Perturb the column on a loaded state and re-run the
   optimizer. If an objective moves, it is read.

A setting is inert exactly when every column it writes is unread, and **a committed test fails if the
derived answer stops matching the label on screen.** A textual scan could not do this:
`capacity_units_per_period` is a column on both `nodes` (never read) and `lanes` (read), so grepping
for the literal answers the wrong question.

That derivation corrected my own hand count from **13** to **15**, and both additions are *names*:
`lane_disruption.name` writes only to a column the optimizer ignores, and `demand.shock.name` reaches
no table at all. The two disruption names are labels, not levers.

### 2.2 A disruption window can be a genuine no-op — and you are told before you spend the compute

🔴 **The optimizer reads lane capacity at exactly one period** — `max(demand.period)`, which is 52 on
the three small scenarios and 104 on `stress-large`. Every other period's capacity is in the CSV and
never read. This is your **question 6** from the Iteration 5 packet, and it is now load-bearing,
because a slider makes it trivially easy to hit.

Set a disruption to periods 18–27 and an amber block appears **before you run anything**: the optimizer
reads at period 52, this window stops at 27, it will not change the answer, extend it to 52 to make it
bite — and **"Do not read an unchanged result as resilience."** Run it anyway and the objective comes
back at exactly 81,789.359460, and the result banner repeats the warning.

**New evidence since the last packet, and the reason I am raising it again:** both shipped scenarios
that carry a lane disruption have one the optimizer never sees. `component-shortage-shock` disrupts 20
lane-periods over 18–27 against a read period of 52; `stress-large` disrupts 64 over 38–53 against 104.
**Neither has a single disrupted lane-period at the period actually read.** The Iteration 5 handoff
recorded this for `component-shortage-shock`; nobody had checked `stress-large`.

**I did not change it.** Widening the read is a modelling change that would move every recorded
objective in every document you have seen. That is your call, not mine — §6, question 1.

---

## 3. The endpoints

All on the existing authenticated router (`X-API-Key`); nginx injects the key server-side, so no
credential reaches the browser.

| Endpoint | What it does |
|---|---|
| `GET /scenarios/custom/settings` | The form schema: all 59 settings, their ranges, and the reach each one earned |
| `POST /scenarios/custom/preview` | Resolve edits — config, change list, validation, estimate. **Writes nothing, runs nothing** |
| `POST /scenarios/custom` | Validate → write the config → generate the data → return the summary |
| `GET /scenarios/custom` | Every custom scenario saved on this box |
| `DELETE /scenarios/custom/{slug}` | Delete one, and everything belonging to it |
| `DELETE /scenarios/custom` | Clear all. Selects on the `custom-` prefix only |
| `GET /scenario-comparison/card` | The pre-run card: what will run, the estimate with its basis, the seed, exclusions, warnings |

`POST /scenario-comparison` and its SSE stream gained `include_ppo` and `include_rationale`. Both
default to *"whatever is right for this kind of scenario"*: **the four recorded scenarios keep exactly
their previous behaviour**, and a custom scenario takes the fast path.

**Both are one tick away in the UI.** A *"A custom run will include:"* row appears above the results
whenever a custom scenario is selected, with **PPO candidate (+~2.7 s)** and **Written rationale
(+~20 s)**. That row exists for a second reason: without it, the header's **PPO timesteps** and
**Top K** controls were things a custom run silently ignored — a no-op control, which guardrail 1
forbids. The row states that they apply only when the matching box is ticked, and it is absent for the
four recorded scenarios, which always run everything.

### Measured latency, on this device

| Path | Time |
|---|---:|
| Save (validate → write config → generate nine CSVs) | **0.04–0.07 s** |
| Custom run, default (baseline + tuned classical) | **1.1–1.2 s** |
| Custom run with the written rationale opted in | **22.9 s** |
| A recorded scenario, unchanged behaviour (PPO + rationale) | **29.7 s** |

The rationale is **~20x the entire numeric comparison**, which is why it is off by default: the loop
has to be drag → run → read. When it is off, the payload carries a real rationale object with an
explicit *"not generated for this run"* marker — never a null, because the results screen dereferences
it and a null would break the screen for your four scenarios too.

---

## 4. Verification

Every number in this document came from a run on this device on 2026-08-20.

| Check | Result |
|---|---|
| `make test` | **555 passed + 2 xpassed** — **208 tests added by this iteration** (was 347 + 2). On a box that already has a saved custom scenario it reads **551 passed + 4 skipped + 2 xpassed**: the four clear-all tests refuse to run rather than delete someone's saved work |
| `make bench-all` | **all 12 objectives bit-identical**, exactly four artifacts |
| `make web-test` | **108 Vitest** (was 62) |
| `make web-check` | **32/32** headless-Chromium checks (was 26) |
| `make scenario-eval` | **29/29**, all 17 refusal classes and 5 warning classes exercised |
| Fairness invariant | a custom scenario equal to `baseline` returns **81,789.359460** |
| Determinism | the same saved scenario run twice, identical to the cent |
| Iteration 4 and 5 surfaces | dataset view, chat panel and **both** replay paths unbroken |

**What the browser checks assert that a screenshot cannot:** that the fifth dropdown entry exists and
is grouped away from the four; that Advanced renders all 59 settings with the inert heading present and
`dc_throughput_units_per_period` individually flagged; that a scenario can be created, run, seen
labelled as custom, and deleted out of the dropdown; that the no-op warning renders as an amber block
with its resilience caveat (checked by computed style, not by eye); and that **`?replay=true` does not
offer the control at all**, because that walkthrough blocks every API call by design.

---

## 5. Honest limits

- **This is the scenario layer, not the network.** You cannot add or remove a supplier, plant,
  warehouse, customer or product. The `network:` block is deliberately excluded — that is
  **Iteration 6b**, the custom dataset, and it is deferred on your own sequencing, not dropped.
- 🔴 **Fifteen of the 59 settings cannot change the optimizer's answer** (§2.1). Labelled, not hidden.
- 🔴 **Lane capacity reaches the optimizer at one period** (§2.2). Warned, not widened.
- **Storage is single-user and box-global.** A saved scenario is visible to anyone who can reach this
  box. There is no per-user state and no auth beyond the shared API key. Real per-tenant state is the
  production track.
- **Synthetic data.** Seed 12345, generated on-device. Every surface says so.
- **A custom run writes its own benchmark artifact** (`benchmark/custom-<slug>-…json`), name-keyed and
  git-ignored. It cannot touch the four; `make bench-all` and `make demo-data` iterate a literal list
  of four and a test reads the Makefile to prove it.
- **The written rationale is off by default** for custom runs (§3). Numbers are unaffected — the model
  never computes them.
- **`POST /scenario-comparison` is not rate limited.** Pre-existing, and now reachable from a click.
  Saving and deleting *are* limited (20/60 s). Worth closing before this is in front of a customer.
- **An optional block cannot be switched off from the Advanced tier** — use the Simple checkbox. A form
  limitation, recorded rather than discovered later.
- **The chat surface is untouched** (your call on 2026-08-19). Custom scenarios are *visible* to it
  because it reads the same scenario list; that path has a regression test, not a feature. It will
  answer questions about a custom scenario and will not claim to have built one.
- **`index.html` is served `no-store` and hashed assets `immutable`.** Before Phase 5 review, nginx
  sent no `Cache-Control` for `index.html`, so a returning viewer kept loading the previous build and
  could not see new features at all. A browser check now asserts both headers.
- 🔴 **No human has read the Option E talk track out loud yet.** Every number in it was checked against
  a live payload or a committed artifact, and the five-step sequence was driven end to end in a real
  browser by an automated check — but that is not the same as a person saying it. It is the one
  definition-of-done item in this repo that no machine check can close, it has been carried since
  Iteration 3, and it is still open. Stated plainly rather than quietly counted as met.

---

## 6. Your call, on four questions

1. 🔴 **Should the optimizer read lane capacity across the plan horizon rather than at a single
   period?** This is question 6 from the Iteration 5 packet, now with sliders attached and with new
   evidence: **both** shipped disruptions are already invisible to it (§2.2). Today a planner can build
   a ten-week supplier outage, run it, and get baseline's number back — honestly warned three times
   over, but still a no-op. Widening it would move every recorded objective in every document you have
   seen, which is why I did not.
2. **Are those the right eight Simple controls?** Demand level · demand spike · capacity tightness ·
   lane disruption · holding cost · missed-order penalty · transport cost · fill-rate target. That is a
   planner's vocabulary as read off your own shipped configs — but you are the one who talks to
   planners.
3. **Should a saved scenario be shareable?** Today it lives on this box (§5). "Download this scenario
   as YAML" is cheap; anything more is the production track.
4. **Should a custom run include the written rationale by default?** It is 22.9 s of the ~24 s total.
   Off makes the loop feel instant; on makes a custom scenario look exactly like one of the four.

---

## 7. What's next

**Iteration 6b — the custom dataset.** The thing you actually asked about second: *"instead of asking
the chat bot what would happen if a warehouse went down, why can't we just reduce a warehouse"*. That
means the `network:` block as controls, plus row-level entity editing (delete `DC-002` specifically),
cascade and feasibility validation, and re-running the four default scenarios on a custom dataset.

One finding worth carrying into it: because the generator builds entities from counts with positional
IDs, *reducing* a count is equivalent to deleting the **last** entity. "2 DCs → 1" is expressible;
"delete `DC-002`, keep `DC-003`" is not, and needs a row-level overlay layer.

**Then the production track:** real customer-data onboarding, multi-tenant isolation, per-tenant
quotas, packaging.

---

*Vertical: Manufacturing. Product shape: Development / PoC (demo-ready). Every number in this document
came from a real on-device run on 2026-08-20 or from a committed artifact generated by one; see
[`../DEVELOPMENT_JOURNAL.md`](../DEVELOPMENT_JOURNAL.md) for the per-phase record, including every
defect found and how it was found.*
