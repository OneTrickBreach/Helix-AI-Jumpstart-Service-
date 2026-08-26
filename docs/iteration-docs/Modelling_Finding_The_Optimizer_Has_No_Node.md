# Modelling finding — the optimizer routes between lanes and has no concept of a node

**From:** Ishan (AI Intern)
**Date:** 2026-08-21
**Status:** Measured on-device. The measurements are real. **Decided: Ryan reviewed this at the
2026-08-26 demo and PARKED it** — acknowledged, not disputed, and deliberately not funded for this
engagement. 🔴 **It is parked, not resolved.** Every limit described below is still true of the code
as it stands today, and this document remains the single most important thing to read before anyone
builds a resilience, node-capacity or network-survivability feature on top of this optimizer.
**Audience:** Ryan Spurr (decision), and whoever picks this prototype up after 2026-08-28 (context).
**Scope:** This document describes a **limit of the model**, not a defect in the code as written. No
code was changed to produce it, and nothing here asks for code to be changed before the demo.

---

## The finding in one paragraph

The routing optimizer is **three independent single-commodity transportation problems** — one for
`inbound_raw`, one for `plant_to_dc`, one for `dc_to_customer` — each with one aggregate demand
constraint and per-lane capacity bounds. **There is no node anywhere in it.** No flow conservation
through a plant or a warehouse, no per-node throughput limit, and no link between the `plant_to_dc`
problem and the `dc_to_customer` problem. A warehouse is a label on the end of a lane. Consequently
a warehouse has no capacity, removing one is free, having **none** is optimal, and severing every
delivery path to every customer *improves* the reported service level.

---

## 1. What that means at the level Ryan asked about

Ryan's ask on 2026-08-19 was: *"instead of asking the chat bot what would happen if a warehouse went
down, why can't we just reduce a warehouse."* Building that control is what surfaced this. Here is
what the pipeline actually reports when you reduce a warehouse:

| Network | Objective | Fill rate | Days of inventory |
|---|---:|---:|---:|
| `baseline` — 2 DCs | 81,789.36 | 83.66% | 4.67 |
| **1 DC** — Ryan's own ask | **81,663.11** *(cheaper)* | **83.66%** *(identical)* | **4.67** |
| 3 DCs | 82,056.85 *(dearer)* | 83.66% *(identical)* | 4.67 |
| **0 DCs** | **68,565.25** *(16% cheaper)* | **92.01%** *(better)* | **0.63** |

**Removing warehouses makes the plan cheaper and never costs a point of service.** A network with no
warehouses at all scores best of the four.

The 1-DC-vs-2-DC delta is not warehouse economics either. The cost breakdown is **identical to the
cent** on holding (5,862.55), ordering (5,700.00), backorder (18,493.56) and lost sale (19,916.14).
**Only transport moves** — 20,478.98 at 2 DCs falls to 20,352.73 at 1 DC, and that fall of 126.25
is the *entire* objective delta, to the cent. A warehouse's whole modelled effect is which lanes
the LP picks.

### The zero-warehouse case is the one to read twice

With `distribution_centers = 0` the generated lane families collapse to `{inbound_raw: 10}` — **zero
`plant_to_dc` lanes and zero `dc_to_customer` lanes.** There is no longer any physical path by which
a finished good can reach a customer. And the pipeline reports:

| Metric (winning classical plan) | 2 DCs | **0 DCs** | Δ |
|---|---:|---:|---:|
| Fill rate | 83.66% | **92.01%** | ▲ *better* |
| Days of inventory | 4.67 | **0.63** | ▼ |
| Backorder cost | 18,493.56 | **9,043.70** | **−9,449.86** *halved* |
| Lost-sale cost | 19,916.14 | **9,739.37** | **−10,176.77** *halved* |
| Holding cost | 5,862.55 | 3,557.25 | −2,305.30 |
| Ordering cost | 5,700.00 | 10,740.00 | **+5,040.00** |
| Transport cost | 20,478.98 | 32,495.27 | **+12,016.29** |
| Total cost | 70,451.22 | **65,575.59** | −4,875.63 |
| **Objective** | **81,789.36** | **68,565.25** | **−13,224.11 (−16.2%)** |

Read the Δ column carefully, because it is more damning than "everything got cheaper". Transport and
ordering both go **up** at zero warehouses. What buys the 16% is that **the two shortage penalties
halve** — and they halve precisely because nothing is being shipped, so nothing is recorded as
short. The model pays a bigger bill for raw material and hauling, and is refunded more than that in
penalties it has stopped charging.

The reason is that fill rate and the shortage penalties are computed from the inventory policy
against forecast demand. **Neither asks whether a lane exists to deliver.** Delivery feasibility is
never checked anywhere, so severing every path to every customer is invisible to the metrics that
are supposed to detect exactly that.

That is the clearest single statement of the gap available, and it is why the 6b control floors the
warehouse count at 1 rather than merely warning: **a crash is embarrassing, but a confident wrong
answer is worse.**

---

## 2. Five oddities recorded across three iterations are one gap, measured five ways

None of these were connected to each other when they were found. They are the same root cause.

| # | What was observed | When | The same cause, stated |
|---|---|---|---|
| 1 | Lane capacity is read at **one period only**, so a narrow-window capacity disruption is a no-op | Iteration 5 (open question 6) | capacity is modelled thinly |
| 2 | `capacity.dc_throughput_units_per_period` is **inert** — `nodes.csv` is never read downstream | Iteration 6a §1.4 | a node has no throughput |
| 3 | Zeroing a **whole lane family** *lowers* the objective (81,789.36 → 77,788) | Iteration 6a | not shipping is not penalised |
| 4 | **Removing a warehouse is free; zero warehouses is optimal** | Iteration 6b, 2026-08-21 | a node is not in the LP at all |
| 5 | `network.lines_per_plant` is inert at 0, 2 and 4 — identical to the digit | Iteration 6b, 2026-08-21 | a plant has no capacity either |

**Those are not five problems. They are one, seen from five directions.** That reframing is the most
valuable thing Iteration 6b produced, and it was produced by trying to build the feature rather than
by reasoning about it.

---

## 3. The mechanism, verified in the source

Read directly from the code on 2026-08-21, not inferred.

**`select_ortools_lanes()`** — [`src/optimize/common.py:114`](../../src/optimize/common.py#L114), the
tuned-classical solver that wins every recorded benchmark:

- [`:147`](../../src/optimize/common.py#L147) — `for lane_type in ["inbound_raw", "plant_to_dc", "dc_to_customer"]:`
  builds **one LP per lane type, in a loop.** The three never meet. Nothing requires that what
  arrives at a DC on a `plant_to_dc` lane is what leaves it on a `dc_to_customer` lane.
- [`:166`](../../src/optimize/common.py#L166) — `solver.Add(solver.Sum(flow_vars) >= min(demand, total_capacity))`
  is the **only** structural constraint: one aggregate demand row per problem.
- [`:163`](../../src/optimize/common.py#L163) — capacity enters **only** as a per-lane variable upper
  bound, `NumVar(0.0, capacity)`. There is no variable representing a node, so there is nothing a
  node-level limit could be written against.
- [`:149`](../../src/optimize/common.py#L149) — `if frame.is_empty(): continue`. **This is why zero
  warehouses is free.** With no `plant_to_dc` and no `dc_to_customer` lanes, those two problems are
  silently skipped. Not infeasible — *absent*. There is no penalty for a demand that has no path.
- [`:153`](../../src/optimize/common.py#L153) — `if total_capacity <= 0: continue`, the same skip for
  a lane family whose capacity has been zeroed. That is oddity 3 above.
- [`:128-129`](../../src/optimize/common.py#L128) — `latest_period = state.horizon()` then
  `filter(pl.col("period") == latest_period)`. **Capacity is read at exactly one period**, the last
  one. That is oddity 1, and Ryan's open question 6.

**The naive baseline has the same shape**, so this is not an artifact of the tuned solver:
`select_greedy_lanes()` at [`:52`](../../src/optimize/common.py#L52) reads a single period
([`:53-54`](../../src/optimize/common.py#L53)), loops the same three lane types independently
([`:59`](../../src/optimize/common.py#L59)) and carries the same `if frame.is_empty(): continue`
([`:64`](../../src/optimize/common.py#L64)).

**Why the reduction in warehouse count moves the number at all** is capacity re-allocation, not
economics: the generator divides `dc_to_customer` capacity by `len(dcs) * len(customers)`
([`data/generator/generate.py:521`](../../data/generator/generate.py#L521)) and draws each lane's
cost with jitter. Fewer DCs means fewer, larger-capacity lanes and a different random cost draw. The
0.15% is arithmetic on lane capacity, not a warehouse having been closed.

---

## 4. What this does and does not invalidate

Being precise about this matters, because the honest scope is narrower than "the numbers are wrong".

**Still valid:**

- **The within-run comparison.** Naive baseline vs. tuned classical vs. PPO all run against the
  *same* model, and the gap affects all three identically. The recorded improvement figures are a
  fair comparison of routing policies under the model as defined.
- **All 12 recorded objectives.** They are reproducible to the digit and were re-verified at every
  6a and 6b checkpoint. They are correct computations of the objective as specified.
- **Everything the forecast and inventory tiers do.** This finding is about the routing LP.

**Not supported by the model, and must not be claimed:**

- 🔴 **Any resilience or network-survivability claim.** "What happens if this warehouse goes down"
  is *not* answerable today. The model has no answer to it, and the answer it appears to give is
  wrong in the optimistic direction — which is the dangerous direction.
- Any comparison of a resized network against 81,789.36 as better or worse. A different network is a
  different problem, not a better plan.
- Any reading of `dc_throughput_units_per_period` or `lines_per_plant` as a capacity control.

---

## 5. The decision this puts in front of Ryan

> ### Should the optimizer model a node?

Fixing this means **per-node flow conservation and per-node throughput constraints** — a genuine
multi-echelon network LP replacing three decoupled transportation problems. Concretely it means:

1. Node-balance constraints linking inbound and outbound flow at every plant and DC.
2. A real throughput capacity per node, which finally makes `dc_throughput_units_per_period` and
   `nodes.csv` load-bearing.
3. Capacity read across the whole horizon rather than at one period (question 6, same work).
4. An infeasibility path, so a demand with no delivery route is reported as unserved rather than
   silently skipped.

**Cost and consequence, stated honestly:** this is real optimization work, not a patch — and **it
would move every objective in every document Ryan has been shown.** That is not a reason to avoid
it; it is the reason it was not attempted four days before a demo at the end of an internship.

**It is the highest-value engineering investment available on this prototype.** It is the difference
between *"this tool resizes a network"* and *"this tool tells you whether your network survives."*
The second is what Ryan was reaching for when he asked what happens if a warehouse goes down.

**Recommendation:** fund this before any further UI surface. Another panel adds reach; this adds
truth.

---

## 6. Provenance

Every number in this document was **measured twice**: once when the Iteration 6b plan was written on
2026-08-21, and again independently in Phase 0 the same day, on
`feat/iteration6b-custom-dataset` @ `262c498`. The second pass exists because this document is the
one going in front of a sponsor.

**Method.** Copy `baseline.yaml`, change one `network:` count, generate with `--seed 12345`, run
`src.pipeline.bench --horizon 8 --ppo-timesteps 128`, read the classical row. **A renamed but
otherwise unmodified `baseline` was run as a control and reproduced 81,789.35946 exactly**, which
validates the probe path itself. All probe configs, generated data and benchmark artifacts were
deleted afterwards; `data/scenarios/` and `data/generated/` were confirmed back to exactly the four
shipped scenarios, and `make cli-list` confirmed the API sees only those four.

| Claim | Re-verified 2026-08-21 (Phase 0) |
|---|---|
| `baseline` (2 DCs) = 81,789.359460, 83.66%, 4.67 days | ✅ `81789.35946`, `0.836619`, `4.665808` |
| 1 DC = 81,663.11, service identical | ✅ `81663.107829`, `0.836619`, `4.665808` — **fill rate and days of inventory identical to the digit** |
| 3 DCs = 82,056.85, service identical | ✅ `82056.854415`, `0.836619`, `4.665808` |
| 0 DCs = 68,565.25 at 92.01% fill | ✅ `68565.250935`, `0.920103` |
| 0 DCs collapses the lane families to `{inbound_raw: 10}` | ✅ counted directly from the generated `lanes.csv`: 2 DCs `{inbound_raw: 10, plant_to_dc: 4, dc_to_customer: 16}`, 1 DC `{inbound_raw: 10, plant_to_dc: 2, dc_to_customer: 8}`, 0 DCs `{inbound_raw: 10}` |
| The 1-DC-vs-2-DC breakdown moves on transport only | ✅ holding, ordering, backorder and lost sale identical to the cent; transport 20,478.98 → 20,352.73, a fall of 126.251631 = the objective delta exactly |
| `lines_per_plant` is inert | ✅ set to **0** — no production lines at all — and the objective is `81789.35946`, bit-identical to baseline |
| Every code citation in §3 | ✅ read from source, line numbers verified individually |
| Oddities 1–3 in §2 | Recorded in the Iteration 5 and 6a handoffs and journal; unchanged, not re-run here |

### 🔴 Two figures in the Iteration 6b plan did not reproduce, and are corrected here

The re-verification earned its keep. Both are fixed in
[`../Iteration6b_Plan_of_Action.md`](../Iteration6b_Plan_of_Action.md) as well as here.

| Plan said | Measured | What it was |
|---|---|---|
| 0 DCs → **4.28** days of inventory (§0.3) | **0.63** | A wrong figure. The correction makes the finding *stronger*: the "best" network in the model also holds almost no inventory |
| *"Only transport moves — 20,352.73 → 20,478.98"* (§1.2) | 2 DCs = 20,478.98, 1 DC = **20,352.73** | **The direction was reversed.** As written it said transport *rises* when you remove a warehouse, which contradicts the plan's own headline that 1 DC is cheaper |

Neither error touched the objective figures or the argument. Both would have been quoted out loud on
Wednesday.

**Nothing in this document required a code change, and none was made.** The optimizer, the objective
function and the generator are untouched, per the Iteration 6b guardrails.

---

*Iteration 6b, Phase 0. Vertical: Manufacturing. Written 2026-08-21 against
`feat/iteration6b-custom-dataset` @ `262c498`. Plan: [`../Iteration6b_Plan_of_Action.md`](../Iteration6b_Plan_of_Action.md) §0.3, §1.2, §1.3, §4.1.*
