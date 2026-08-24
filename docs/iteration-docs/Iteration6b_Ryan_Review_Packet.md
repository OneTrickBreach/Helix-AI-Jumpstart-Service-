# Iteration 6b — Review Packet for Ryan

**From:** Ishan (AI Intern)
**Date:** 2026-08-24 · **for the demo on Wednesday 2026-08-26**
**Status:** 🔴 **DRAFT — not sent.**
**Subject:** You asked for two things on 2026-08-19. Both are on the box. And building the second one
found something about the product that nobody knew last Monday.

---

## 1. 🔴 The one thing worth your meeting time

> ### Should the optimizer model a node?

**Today it does not.** You asked *"why can't we just reduce a warehouse."* You can, now — and here is
what the tool says when you do:

| Network | Objective | Fill rate | Days of inventory |
|---|---:|---:|---:|
| `baseline` — 2 DCs | 81,789.36 | 83.66% | 4.67 |
| **1 DC** — your ask | **81,663.11** *(cheaper)* | **83.66%** *(identical)* | **4.67** |
| 3 DCs | 82,056.85 *(dearer)* | 83.66% | 4.67 |
| **0 DCs** | **68,565.25** *(16% cheaper)* | **92.01%** *(better)* | 0.63 |

**Removing a warehouse makes the plan cheaper and costs no service at all.** And a network with **no
warehouses** — where no lane exists by which a finished good can reach any customer — scores **best of
the four**, on both cost *and* service.

**Why:** the routing optimizer is three independent transportation problems, one per lane type, with
one aggregate demand constraint each. **There is no node in it.** No flow conservation through a
warehouse, no per-node throughput limit, no link between the plant→DC problem and the DC→customer
problem. A warehouse is a label on the end of a lane. Verified in the source, and the naive baseline
has the identical shape — so this is not an artifact of the tuned solver.

**This is not five problems. It is one, measured five ways:**

| What we recorded, and when | The same cause |
|---|---|
| Lane capacity read at **one period** (your question 6, Iteration 5) | capacity modelled thinly |
| `dc_throughput_units_per_period` is **inert** (Iteration 6a) | a node has no throughput |
| Zeroing a whole lane family **lowers** the objective (Iteration 6a) | not shipping is not penalised |
| **Removing a warehouse is free; zero is optimal** (Iteration 6b) | a node is not in the LP at all |
| **`lines_per_plant` is inert at 0, 2 and 4** (Iteration 6b) | a plant has no capacity either |

**What a fix costs:** per-node flow conservation and throughput constraints — a genuine multi-echelon
LP — plus reading capacity across the horizon and reporting unservable demand instead of skipping it.
🔴 **It would move every objective in every document I have shown you.** That is not a reason to avoid
it. It is why the decision is yours and not mine, and why I did not attempt it four days before this
meeting.

**My recommendation:** fund this before any further UI. **It is the difference between *"this tool
resizes a network"* and *"this tool tells you whether your network survives."*** The second is what you
were reaching for when you asked what happens if a warehouse goes down.

Full write-up, with the mechanism, the code references and the provenance of every figure:
[`Modelling_Finding_The_Optimizer_Has_No_Node.md`](Modelling_Finding_The_Optimizer_Has_No_Node.md).

**What I need from you:** fund it / park it / something in between.

---

## 2. What you asked for, and what is there

Both asks from 2026-08-19, in one panel.

- **Custom scenario** (6a, merged 2026-08-20): 8 grouped controls, 67 in Advanced.
- 🔴 **Custom dataset** (6b, this): the **eight network counts** — suppliers, plants, warehouses,
  customers, products and both bill-of-materials depths. Change them, run the real pipeline, save it,
  reopen it, delete it.

**One panel, not two**, because a custom dataset is still one config file and two screens would be a
lie about the architecture. If you expected two, that is question 8 below.

**Your four recorded results have not moved** — bit-identical at every checkpoint, because the
optimizer, the objective function and the generator were never touched.

**Five minutes, if that is all we have:** open **Custom scenario…** → **THE NETWORK** → set
**Distribution centers** to `1` → **Save & run** → read **81,663.11** against baseline's 81,789.36 with
identical fill. Then set it to `0` and *read the red box out loud*. That is the whole meeting.

---

## 3. The honest parts, up front

**A network count is not a resilience test, and the control says so.** Node counts move the objective
by under 1% and never change service. The panel labels them *"…the optimizer has no per-node capacity —
so this is NOT a resilience test."* I would rather the control said that than let you infer resilience
from a number that cannot express it.

**A resized network is not a better one.** 7 customers scores 66,548.24 — an apparent **18.6%
improvement** that is really **12% less demand to serve**. An amber block says so directly above the
numbers. This was the easiest number in the tool to misread, so it is the one with the most labelling
around it.

**Seven network values could not be run, and two of them were dangerous rather than merely broken.**
Five crashed (one of them *after* writing a complete dataset). Two returned confident, cheaper, better
answers for networks that cannot physically operate. All seven are refused before anything is written —
and the two dangerous ones are refused **with their measured numbers quoted**, because the message
should teach you the modelling limit rather than just block you.

**What it still cannot do:** delete a *specific* warehouse. IDs are positional, so reducing a count
removes the **last** entity — "2 DCs → 1" keeps `DC-001`. That is question 9.

---

## 4. 🔴 The questions — on one page

**First, an honest reconciliation.** I have been carrying "eleven open questions" in the plan. That
count was wrong in two directions, so here is the arithmetic:

- **One is already answered.** Iteration 5's question 1 asked whether the dataset view answered your
  first ask. You reviewed it on 2026-08-19 and the network map was your favourite screen. **Closed.**
- **Three were the same question.** Iteration 5 q6, Iteration 6a q1 and this packet's §1 are all *"how
  deep does the capacity/node model go?"* — merged into **Q1** above.
- **Four are new in 6b.**

So: 11 − 1 answered − 2 duplicates + 4 new = **13 open, and Q1 is worth more than the other 12
together.**

| # | Question | Origin | What I need |
|---|---|---|---|
| **1** | 🔴 **Should the optimizer model a node?** (subsumes lane capacity across the horizon) | I5 q6 · 6a q1 · **6b §1** | Fund / park. **The only one that matters this week** |
| 2 | Does the **`BETA`** chip come off the chat panel? Still on every surface, because the rule was "it comes off when the sponsor says so" | Iteration 5 | Keep for customer demos, or remove? |
| 3 | **Whitelist width** — 3 of 8 what-if perturbation types shipped | Iteration 5 | Which next: `supplier_zeroing`, `lead_time_inflation`, `capacity_cut`, `cost_shock`, `service_target_change`? |
| 4 | **PPO in what-ifs** — excluded by default, symmetrically | Iteration 5 | Leave opt-in, or always-on for resilience questions? |
| 5 | **Answer length** — planner-first, lead with the number | Iteration 5 | Right default, or executive-length? |
| 6 | **Hospital service-level questions** — refused outright, no numbers | Iteration 5 | Keep refusing, or answer with an explicit "manufacturing only, unvalidated for clinical" caveat? |
| 7 | Are those the right **eight Simple controls**? | Iteration 6a | Swap any? Cheap to change |
| 8 | Should a saved scenario be **shareable**? Today: this box, single-user, no permissions. **And: did you want two screens rather than one panel?** | 6a q3 · **6b** | Download-as-YAML is cheap; sharing is the production track |
| 9 | Should a custom run **write the rationale by default**? 22.9 s against 1.2 s for the numbers | Iteration 6a | Off by default, or on in front of a customer? |
| 10 | 🔴 **Row-level entity editing** — *"delete `DC-002`, keep `DC-003`"*. Named, scoped, deferred | **6b** | Worth funding, or is "reduce a count" enough? |
| 11 | Are the **two honesty classes** the right framing? Node counts <1% with no service change; product counts ±25% by resizing the problem | **6b** | Does that split match how a planner thinks? |
| 12 | **The sanity ceilings** — suppliers/plants/DCs ≤ 20, customers ≤ 60, **finished goods ≤ 12**, BOM depth ≤ 6 | **6b** | ⚠️ 12 is *exactly* `stress-large`'s value, so no custom network can carry more products than our largest shipped scenario. Raise it? |
| 13 | **The four default scenarios on a custom network** — out of scope this iteration | **6b** | Want it? Needs the shock blocks re-expressed against a resized network |

---

## 5. One thing I could not finish, and one I chose not to

**Could not:** Option E has **no GPU-free replay path**. Options A, C and D each have one; the custom
scenario panel does not, because building a scenario needs the API. On this timeline that gap was
traded for a screen recording — and then the recording was not made either, which was my call to
surface and yours to make. **So if the box misbehaves on Wednesday morning, this panel cannot be shown
at all.** I check `/health` before we start; that is the whole mitigation.

**Chose not to:** fix the node gap. It would have moved every number in every document you have seen,
four days before this meeting, at the end of an internship. Measuring it and handing you the decision
was the honest trade.

---

*Iteration 6b. Everything measured on-device on `helix-gb10-intern` between 2026-08-21 and 2026-08-24.
Synthetic seeded data — not customer data, and nothing left the box. Handoff:
[`AI_Jumpstart_MVP_Iteration6b_handoff.md`](AI_Jumpstart_MVP_Iteration6b_handoff.md). Talk track:
[`../DEMO_GUIDE.md`](../DEMO_GUIDE.md) Option E, steps 7–9.*
