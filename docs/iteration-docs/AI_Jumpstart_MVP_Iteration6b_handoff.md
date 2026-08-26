# AI Jumpstart MVP — Iteration 6b Handoff: "Reduce a Warehouse" — the Custom Dataset (network tier)

**Prepared for:** Ryan Spurr | Helix, Connection Inc.
**From:** Ishan (AI Intern)
**Date:** 2026-08-24
**Branch:** `feat/iteration6b-custom-dataset` (cut from `main` @ `262c498`)
**Predecessor:** Iteration 6a — Custom Scenario, merged to `main` 2026-08-20 (`ad17cc5`)
**Origin:** your second ask of **2026-08-19**, in your words — *"instead of asking the chat bot what
would happen if a warehouse went down, why can't we just reduce a warehouse."*

---

## ✅ Outcome — reviewed 2026-08-26

**You reviewed this live on 2026-08-26, are satisfied, and requested no changes.** Iteration 6b is
accepted as-is and feature work on this engagement is closed.

**On the decision this document asks you for** — *should the optimizer model a node?* — **you parked
it.** The finding is acknowledged and not disputed; it is deliberately not funded for this
engagement. 🔴 **Parked is not resolved.** Every limit described below is still true of the code as
it stands, and this document plus
[`Modelling_Finding_The_Optimizer_Has_No_Node.md`](Modelling_Finding_The_Optimizer_Has_No_Node.md)
must be read before anyone builds a resilience, node-capacity or network-survivability feature on
this optimizer.

**One defect was found live at that demo and fixed the same day:** clicking **Save** and then
**Save & run** errored with *"already exists"*, because the panel had no dirty-state tracking. The
panel now greys **Save** out when what is on screen matches what is on disk and offers a plain
**Run** instead. Frontend only; no data was ever at risk and no result was ever wrong.
See [`../Known_Issue_Save_Run_Button_State.md`](../Known_Issue_Save_Run_Button_State.md) — 🔴 **worth
reading less for the defect than for why 633 passing tests, 118 Vitest and 50 browser checks did not
catch a two-click sequence.**

---

## TL;DR

You asked for two things on 2026-08-19. 6a delivered the conditions; **this delivers the network.**

Open **Custom scenario…**, scroll to **THE NETWORK**, set **Distribution centers** to `1`, click
**Save & run**. About a second and a half later you have a real result on a real network you shaped.

> ### 🔴 But the valuable half is not the panel. It is what building the panel measured.
>
> | Network | Objective | Fill rate | Days of inventory |
> |---|---:|---:|---:|
> | `baseline` — 2 DCs | 81,789.36 | 83.66% | 4.67 |
> | **1 DC** — your own ask | **81,663.11** *(cheaper)* | **83.66%** *(identical)* | **4.67** |
> | 3 DCs | 82,056.85 *(dearer)* | 83.66% | 4.67 |
> | **0 DCs** | **68,565.25** *(16% cheaper)* | **92.01%** *(better)* | 0.63 |
>
> **Removing a warehouse makes the plan cheaper and costs no service at all. A network with no
> warehouses at all scores best of the four** — and at zero DCs there is no lane by which a finished
> good can reach any customer.
>
> The routing optimizer moves volume between **lanes** and has **no concept of a node**. A warehouse is
> a label on the end of a lane: no throughput limit, free to remove, optimal to omit.
> **Full write-up:** [`Modelling_Finding_The_Optimizer_Has_No_Node.md`](Modelling_Finding_The_Optimizer_Has_No_Node.md).
> **That document is the most valuable thing this iteration produced**, and it is a decision for you.

**Your four recorded results have not moved.** The optimizer, the objective function and the generator
were not touched — verified bit-identical at every one of the four checkpoints:

| Scenario | Baseline | **Classical (winner)** | PPO |
|---|---:|---:|---:|
| `baseline` | 88,022.760795 | **81,789.359460** | 102,804.716650 |
| `component-shortage-shock` | 102,834.785064 | **95,445.445064** | 113,584.863463 |
| `demand-surge` | 100,734.738785 | **94,165.363245** | 115,161.538279 |
| `stress-large` | 2,622,335.215962 | **2,521,615.068565** | 2,867,271.225615 |

---

## What is there

**Eight `network:` counts**, in one panel with the 6a controls (decision 10 — a custom dataset is still
one config file, so two screens would be a lie about the architecture).

They are split into **two groups that are labelled differently on purpose**, because they are not one
population:

| Group | Counts | Measured behaviour |
|---|---|---|
| **Changes the shape of the network** | suppliers · plants · distribution centers | Moves the objective **0.12%–0.64%** and changes fill rate and days of inventory **not at all**. Comparable to baseline |
| **Changes the SIZE of the problem** | customers · finished goods · subassemblies · raw components | Moves it **1.3%–31.3%**, by changing total demand or BOM depth. **Not comparable to baseline** — a different quantity, not a better plan |
| **Cannot change the answer** | `lines_per_plant` | Identical to the digit at 0, 2 and 4. Under Advanced's *"recorded in the dataset, not read by the optimizer"* heading, never as a live control |

The split is **derived, not asserted**: a committed test measures that a shape count leaves total demand
bit-identical (1,837,066) while a size count moves it. Put a count in the wrong group and the build
fails.

**Everything else was reused unchanged.** `store.py` needed **no modification** — save, list, delete,
clear-all all carried a network-edited config as-is. The dataset view renders one with **no dataset-code
change**: `NetworkMap` redraws on its own (17 nodes → 16) and the narrative reads *"through **1**
distribution center"* with correct singular grammar. `NetworkMap.tsx` was **never touched** in this
iteration — 0 commits since `262c498` modify it.

---

## 🔴 The seven values that are refused, and why that is the interesting part

Five network values raised **uncaught exceptions** before this iteration. Two more did something worse.

| Value | What it did | Now |
|---|---|---|
| `plants = 0` | `ZeroDivisionError` in the generator | refused, before anything is written |
| `finished_goods = 0` | `ZeroDivisionError` | refused |
| `subassemblies_per_finished_good = 0` | `ZeroDivisionError` | refused |
| `raw_components_per_subassembly = 0` | `ZeroDivisionError` | refused |
| **`customers = 0`** | 🔴 **passed generation**, wrote a complete dataset, then died two stages later in the **forecast** | refused *before the write* |
| **`distribution_centers = 0`** | 🔴 returned **68,565.25 at 92.01% fill** — better than baseline on both | refused, **with the measured reason quoted** |
| **`suppliers = 0`** | 🔴 returned 77,390.94 at **83.66% fill, unchanged to the digit** | refused, with its measured reason |

**A crash is embarrassing. A confident wrong answer is worse.** So the last two are not silently
clamped — type `0` into Distribution centers and the panel *explains*:

> A network with no distribution centers has no lane by which a finished good can reach a customer —
> and this prototype does not notice. Measured: it scores 68,565.25 at 92.01% fill, which is better
> than baseline on BOTH counts (81,789.36 at 83.66%), because the optimizer has no per-node capacity
> and the fill-rate calculation never asks whether a delivery route exists. **That is a limit of the
> model, not a fact about your network.** Keep at least 1.

**Reaching that sentence is the point.** A control that snapped the `0` back to `1` would have hidden
the most valuable thing this iteration measured. Screenshot:
[`screenshots/iteration6b/network-zero-dc-refusal.png`](screenshots/iteration6b/network-zero-dc-refusal.png).

---

## 🔴 Limits — read this section before showing anyone

1. **This is not a resilience test, and the panel says so.** Node counts move the objective by under 1%
   and never change service. *"What happens if this warehouse goes down"* is **not answerable by this
   model today**, and the answer it appears to give is wrong in the *optimistic* direction. That is the
   dangerous direction, which is why it is labelled on the control itself.
2. **A resized network's objective is not comparable to 81,789.36.** 7 customers scores 66,548.24 — an
   apparent 18.6% "improvement" that is really 12% less demand to serve (66,807 → 58,972 units). An
   amber block says so directly above the numbers, and the valid comparison — naive vs. classical
   *within* the run — sits below it.
3. **No row-level entity editing.** IDs are positional (`DC-001 … DC-00n`), so **reducing a count
   removes the LAST entity**. "2 DCs → 1" keeps `DC-001`. *"Delete `DC-002`, keep `DC-003`"* is not
   expressible and is deferred, not dropped — it needs a row-level overlay plus cascade repair across
   lanes, demand, inventory and service targets.
4. **The four default scenarios cannot be re-run on a custom network.** The shock and disruption blocks
   would need re-expressing against a resized network. Named as deferred.
5. **The ceilings are typo guards, not modelled limits** (suppliers/plants/DCs ≤ 20, customers ≤ 60,
   finished goods ≤ 12, BOM depth ≤ 6). 40 customers and 12 DCs were both measured running fine and
   fast. ⚠️ Note **finished goods ≤ 12 is exactly `stress-large`'s own value** — so no custom network
   can carry more products than the largest shipped scenario. That is a judgement call and it is a
   question for you.
6. **Single-user storage.** Saved datasets live on this box and are visible to anyone who can reach it.
   No per-user state, no sharing, no permissions.
7. **The estimate borrows when it must, and says so.** A network with no run on record uses baseline's
   recorded optimizer latency — and states that it came from a different-shaped network
   (*"17 nodes / 30 lanes against 49 / 94 here, so treat this as a floor"*). It never invents a figure.

---

## Verified on-device

Every number here came from a real run on the GB10, at the checkpoint of each of the four phases.

| Check | Result |
|---|---|
| `make test` | **635 passed, 2 xpassed** (77 added by 6b) |
| `make bench-all` | 🔴 **all 12 objectives bit-identical**, checked programmatically |
| `make scenario-eval` | **41/41** (12 controls); refusal classes **21/21**, warnings **6/6** |
| `make web-test` | **118** |
| `make web-check` | **49/49**, 0 FAIL, 0 console errors |
| `make scenario-ledger` | 67 settings across 8 groups; `lines_per_plant` flagged inert |
| 1-DC dataset, end to end | saved → ran → **81,663.107829** → reopened → deleted, all four artifacts removed |
| 7-customer dataset | **66,548.241282**, labelled not-comparable on screen |
| Bundle | 657.15 → **660.14 kB** raw (+2.99), 186.31 → 186.97 gzip (**+0.66**), no new dependencies |
| `NetworkMap.tsx` | **untouched**, 0 commits |

---

## What I would do next, in order

1. 🔴 **Decide whether the optimizer should model a node.** Everything else on this list is smaller.
   [`Modelling_Finding_The_Optimizer_Has_No_Node.md`](Modelling_Finding_The_Optimizer_Has_No_Node.md)
   costs it out. It would move every published objective, which is exactly why it is your call and not
   mine.
2. **Lane capacity across the horizon** — the same root cause, answer it together with (1).
3. **Row-level entity editing** with cascade repair, if *"delete DC-002"* is what you actually wanted.
4. **A GPU-free replay path for Option E** — Iterations 4 and 5 have one; this panel does not, and that
   gap was traded for a screen recording on this timeline. See the deferred list.
5. **Multi-user storage** if a saved dataset ever needs to leave this box.

---

## Where things are

| What | Where |
|---|---|
| The ledger — 67 settings, reach **derived** not declared | [`src/scenario/ledger.py`](../../src/scenario/ledger.py) |
| Floors, ceilings, comparability | [`src/scenario/validate.py`](../../src/scenario/validate.py) |
| The form payload, including the two honesty classes | [`src/scenario/api.py`](../../src/scenario/api.py) |
| The Network group | [`web/src/custom/CustomScenarioPanel.tsx`](../../web/src/custom/CustomScenarioPanel.tsx), [`web/src/lib/customForm.ts`](../../web/src/lib/customForm.ts) |
| The derivation that proves the labels | [`tests/test_iteration6a_ledger.py`](../../tests/test_iteration6a_ledger.py) |
| 6b's own tests | [`tests/test_iteration6b_network.py`](../../tests/test_iteration6b_network.py), [`tests/test_iteration6b_dataset.py`](../../tests/test_iteration6b_dataset.py) |
| The talk track | [`../DEMO_GUIDE.md`](../DEMO_GUIDE.md) **Option E**, steps 7–9 |
| Screenshots | [`screenshots/iteration6b/`](screenshots/iteration6b/) — all five reproducible from `make web-check` |
| The plan, with every measurement | [`../Iteration6b_Plan_of_Action.md`](../Iteration6b_Plan_of_Action.md) |
| Day-by-day record | [`../DEVELOPMENT_JOURNAL.md`](../DEVELOPMENT_JOURNAL.md) |

---

*Iteration 6b. Vertical: Manufacturing. On-device on `helix-gb10-intern` (NVIDIA GB10, driver
580.159.03, CUDA 13.0). Synthetic seeded data throughout — not customer data. Nothing leaves the box.*
