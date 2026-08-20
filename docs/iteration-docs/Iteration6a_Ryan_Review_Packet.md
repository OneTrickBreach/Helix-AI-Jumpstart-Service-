# Iteration 6a — Review Packet for Ryan

**From:** Ishan (AI Intern)
**Date:** 2026-08-20
**Status:** 🔴 **DRAFT — not sent.**
**Subject:** You asked for a custom scenario on 2026-08-19. It is on the box. Four questions.

---

## What you asked for, and what is there

On **2026-08-19** you reviewed the live demo — your first look at Iterations 4 and 5 — and asked for
two things: **a custom scenario** and **a custom dataset**. You said the dataset one looked hard and
asked to see the scenario one first.

**The custom scenario is built, verified on-device, and demoable.** Open the Scenario dropdown on the
results screen; there is a fifth entry, **"Custom scenario…"**. It opens a control panel over the
settings that define a scenario, pre-filled from `baseline`. Move a control, name it, click **Save &
run** — the real pipeline runs on it in about a second and a half. Save it and it comes back in the
dropdown next time.

**Your four recorded results have not moved, and cannot.** The generator, the optimizer and the
forecast were not modified — a custom scenario is a new config file and nothing else. Re-verified
bit-identical at every checkpoint:

| Scenario | Classical (winner) |
|---|---:|
| `baseline` | 81,789.359460 |
| `component-shortage-shock` | 95,445.445064 |
| `demand-surge` | 94,165.363245 |
| `stress-large` | 2,521,615.068565 |

A custom scenario built with **no changes at all** reproduces `baseline` to the digit.

**What it is not:** it cannot change the network. No adding or removing suppliers, plants, warehouses,
customers or products. That is **Iteration 6b**, the custom dataset — deferred on your own sequencing,
not dropped.

**Walkthrough:** `DEMO_GUIDE.md` **Option E** — a five-step talk track.
**Detail:** [`AI_Jumpstart_MVP_Iteration6a_handoff.md`](AI_Jumpstart_MVP_Iteration6a_handoff.md).

---

## Two things I want you to see, because they are the honest parts

### 1. Fifteen of the 59 settings cannot change the answer — and the panel says so

The optimizer and forecast read six of the nine data tables. `nodes.csv`, `bom.csv` and
`production_lines.csv` are never read downstream — **but they are read by the dataset view**, which is
what draws the network map you liked. So those settings visibly change the dataset page and then fail
to change the result. That is worse than doing nothing, so they are shown in Advanced under an explicit
heading — *"recorded in the dataset, not read by the optimizer"* — and never as live controls.

**`capacity.dc_throughput_units_per_period` is the one to look at.** It reads like the most intuitive
control on the whole panel — how much this warehouse can handle — and it does nothing. Shipping it as a
working slider would have been the most misleading thing in this iteration.

Those labels were **derived, not asserted**: the system generates the data twice per setting and
re-runs the optimizer to see whether the answer moves. A committed test fails if a label stops being
true. That derivation corrected my own hand count from 13 to 15.

### 2. A disruption can be invisible to the optimizer — including in two of your own scenarios

🔴 **The optimizer reads lane capacity at exactly one period** — the last period of the demand history
(52, or 104 on `stress-large`). Every other period's capacity is in the data and never read.

Build a disruption over periods 18–27 and the panel tells you, **before spending any compute**, that it
cannot change the answer, names the period it would need to reach, offers to extend it, and says **"Do
not read an unchanged result as resilience."** Run it anyway and the objective comes back at exactly
`baseline`'s number, with the warning repeated.

**New since the last packet:** both shipped scenarios that carry a lane disruption have one the
optimizer never sees. `component-shortage-shock` disrupts periods 18–27 against a read period of 52;
`stress-large` disrupts 38–53 against 104. **Neither has a single disrupted lane-period at the period
actually read.** The Iteration 5 handoff recorded this for `component-shortage-shock` only — nobody had
checked `stress-large`.

I did not change it. That leads to question 1.

---

## The four questions

### 1. 🔴 Should the optimizer read lane capacity across the plan horizon, rather than at one period?

This is **question 6 from the Iteration 5 packet**, now with sliders attached and with the new evidence
above. Today a planner can build "we lose two supplier lanes for ten weeks", run it, and get
`baseline`'s number back — warned three times over, but still a no-op.

**Why I did not just fix it:** widening the read is a modelling change that would move **every recorded
objective in every document you have seen**, including the four above. Doing that in the same week you
first saw them seemed like the wrong call to make on your behalf. **It is yours.**

### 2. Are those the right eight Simple controls?

Demand level · demand spike · capacity tightness · lane disruption · inventory holding cost ·
missed-order penalty · transport cost · fill-rate target.

That is a planner's vocabulary as read off your own four shipped configs. You are the one who talks to
planners — if two of those should be swapped for something else, that is a cheap change.

### 3. Should a saved scenario be shareable?

Today it lives on this box and is visible to anyone who can reach it — single-user, no per-user state.
A "download this scenario as YAML" button is cheap. Anything more (sharing between users, a library
with permissions) is the production track.

### 4. Should a custom run write the rationale by default?

The written advisory rationale takes **22.9 s**; the entire numeric comparison takes **1.2 s**. So it
is off by default, and the loop feels instant. Turning it on makes a custom scenario look exactly like
one of the four recorded results — which may be what you want in front of a customer.

---

## Also still open from Iteration 5

You have now seen the chat panel, but you have not said whether the **`BETA`** chip comes off. It is
still on every chat surface, because the rule I wrote was "it comes off when the sponsor says so, not
when the code is finished". Iteration 6a built nothing for the chat panel, per your "not concerned
about that right now" — it is regression-tested against custom scenarios, and otherwise untouched.

The other Iteration 5 questions (whitelist width, PPO in what-ifs, answer length) are unchanged and
lower stakes than question 1 above.

---

## One thing I could not finish

🔴 **Nobody has read the Option E talk track out loud.** Every number in it is checked against a live
payload or a committed artifact, and an automated browser check drives the whole sequence end to end —
but that is not the same as a person saying it in front of someone. It has been an unmet
definition-of-done item in this repo since Iteration 3, and it is still unmet. Flagging it rather than
counting it as done.

---

*My internship ends approximately 2026-08-27. Iteration 6a is complete on
`feat/iteration6a-custom-scenario` and has not been merged to `main` — that is your call, as the
Iteration 5 merge was. Everything is documented for a cold reader: the plan, the per-phase journal
including every defect found and how, the handoff, and the demo guide.*
