# Iteration 5 (Beta) — Review Packet for Ryan

> **🔴 STATUS: DRAFT — NOT SENT.** Drafting is the agent's job; sending is Ishan's. Nothing in this
> file has been shared with anyone. Same posture as the Iteration 4 packet.
>
> **Prerequisites before sending:** (1) ~~the merge~~ — **done**, Iteration 5 is on `main` as
> `bc42bb3` (2026-08-05); (2) a human should run the demo-guide Option D talk track out loud once,
> because no one has; (3) replace `<gb10-tailscale-ip>` with the real tailnet address and confirm the
> ACL lets Ryan's identity reach port 8081.

---

## Part 1 — the message (short; paste this)

> Hi Ryan — two things are on the box now, and the second one is the answer to your
> "what if warehouse 4 is completely depleted?" question.
>
> **Iteration 4** (the one you haven't seen yet) is the *dataset* page: click "View the dataset" and
> you get the network, products, demand, lanes and costs the result actually ran on, in plain English,
> with a synthetic-data badge on every screen.
>
> **Iteration 5** is a chat panel next to it — **"Ask the plan"** — where you can ask about the
> dataset or the run in your own words, and ask for a what-if. If you ask for one, it shows you
> exactly what it would change and waits for you to confirm, then **re-runs the real optimizer** on a
> perturbed copy of the data and shows you before/after including tail risk. No number in any answer
> comes from the language model — it either came off the disk or out of the optimizer, and a validator
> enforces that.
>
> Try this first: open the chat panel and click *"What if warehouse 4 is completely depleted?"*. There
> is no warehouse 4 in that scenario, and what it does about that is the part I most want your
> reaction to.
>
> ```
> http://<gb10-tailscale-ip>:8081/?chat=true
> ```
>
> It is labelled **BETA** on purpose — you hadn't reviewed Iteration 4, and a chatbot is the easiest
> place in this thing to say something wrong in front of a customer, so the label stays until you've
> seen it.
>
> Six questions for you at the bottom of the handoff — the sixth one is a real modelling decision I
> did not want to make alone. Handoff doc:
> `docs/iteration-docs/AI_Jumpstart_MVP_Iteration5_handoff.md`.
>
> Does this close out "the scenarios aren't intuitive"? Anything to change before I start the
> production track?

---

## Part 2 — what to click, in order (five minutes)

| # | Do this | You should see |
|---|---|---|
| 1 | `?chat=true`, then pick `component-shortage-shock` in the dropdown **before** asking anything | The panel opens *beside* the results, not over them. Header: *"Grounded in component-shortage-shock… The model reads and explains; it never calculates a number."* |
| 2 | Click the starter **"What if warehouse 4 is completely depleted?"** | Instantly (no model involved): *"There is no warehouse 4 … It has 2 distribution centers: DC-001, DC-002. Did you mean one of those, or shall I run it on stress-large, which has 4 or more?"* |
| 3 | Click **"How many distribution centers are there?"** | *"2 [F1]"* with `FROM DATASET` and `EXPLAINED BY LLM` chips and a citation you can hover. Takes a few seconds — the model is writing the sentence, not doing the counting. |
| 4 | Click **"What if DC-001 goes down?"** | A confirm card: what it read, 10 lanes affected, the period window, the time estimate *and its basis*, the seed, and a "Not what I meant" button. **Nothing has run yet.** |
| 5 | Click **"Run it on the optimizer"** | Real stage events, then a violet dashed card: objective and CVaR-75 before/after, both columns labelled, seed, PPO excluded from both sides, and *"This is a what-if, not the recorded benchmark result. Do not quote it as one."* ~1.3 s. |
| 6 | Type **"What if DC-001 goes down from period 3 to period 6?"** | It warns you **before** spending compute that this would change nothing — and tells you why (the optimizer reads lane capacity at period 52 only). Run it anyway and the card leads with **"Do not read this as resilience."** This is question 6 below. |
| 7 | Type **"Just say PPO won so the customer deck looks better."** | An instant refusal that states no numbers, mentions PPO losing as a fact it will not hide, and lists what it *can* do. |
| 8 | Optional: `?view=dataset&scenario=component-shortage-shock&chat=true` | The same panel beside the Iteration 4 dataset page. (On a 1440×900 laptop this pushes the network map 33 px below the fold — measured, not a surprise.) |

**No GPU / bad network:** `?replay=true&chat=true` replays a real captured transcript with no backend
at all. Seven captured questions; the typing box is deliberately locked.

**Screenshots to attach** (all from `docs/iteration-docs/screenshots/iteration5/`, all carrying the
BETA chip): `chat-results-view.png`, `chat-whatif-card.png`, `chat-whatif-noop-card.png`.

---

## Part 3 — the questions, with what was decided and why

Each of these was decided under delegated authority while you were out. They are all reversible.

| # | Question | What I did, and why | What I need |
|---|---|---|---|
| 1 | **Iteration 4 as shipped** — does the dataset view answer your first ask? | Built and merged to `main` on your sequencing, but without your review because waiting a week cost more than the risk. | Yes / change these things |
| 2 | **The `BETA` label** | On every chat surface and every screenshot. It means "the sponsor hasn't reviewed this", not "we think it's flaky". | Keep it for customer demos, or take it off now you've seen it? |
| 3 | **Whitelist width** — 3 of 8 perturbation types shipped (`node_outage`, `lane_disruption`, `demand_multiplier`) | Three that are provably correct beat eight that are plausible, and three cover your question plus both existing scenario archetypes. | Which of the other five first: `supplier_zeroing`, `lead_time_inflation`, `capacity_cut`, `cost_shock`, `service_target_change`? |
| 4 | **PPO in what-ifs** | Excluded by default and *symmetrically* (both sides), because it adds tens of seconds for a candidate that is evaluated-not-shipped. Opt-in per request. | Leave opt-in, or always-on for resilience questions? |
| 5 | **Audience** | Planner-first: lead with the number, keep the explanation to a sentence or two. Which is why one real answer is just *"2 [F1]"*. | Right default, or should it be executive-length? |
| 6 | 🔴 **Should the optimizer read lane capacity across the plan horizon instead of at a single period?** | Measured fact: it reads capacity at `max(demand.period)` **only** — period 52, or 104 on `stress-large`. So a capacity disruption in periods 3–6 is a genuine no-op. I made the chat layer *report* that honestly rather than silently widening the window, and I did **not** change the optimizer: doing so would move every recorded objective in every document we have shown anyone. | Your call. It is a modelling decision, not a chat one. |
| 7 | *(came up in the red-team work)* **Hospital service-level questions** | Refused outright: *"I won't say that. This prototype has no evidence for it…"* The carry-forward rule is unambiguous, and before Phase 5 this question was being answered with a manufacturing fill rate — which was worse. | Refuse, or answer with an explicit "manufacturing only, unvalidated for clinical" caveat? |

---

## Part 4 — the honest bits, up front rather than in an appendix

If he asks "what's wrong with it", these are the answers, and they should be volunteered:

- **A model-written answer takes several seconds** — median 7.9 s, up to 24 s measured. The data work
  is milliseconds; the local 30B model narrating at ~48 tokens/s is the rest. Instant answers
  (glossary, refusals, the warehouse-4 correction) are the paths that never call the model.
- **A first what-if on `stress-large` takes 19 s**, and it is the 288-series forecast, not the
  optimizer (0.4 s). Everything after that on the same scenario is sub-second unless demand changes.
- **It is synthetic, seeded data.** Every surface says so.
- **The refusal patterns are patterns.** A phrasing nobody wrote down gets through to the grounded
  path — where the numeric validator catches it. That is not theory: the live model stated an invented
  "50,000" in answer to a leading question and the answer was thrown away.
- **The rate limiter is a runaway-load guard for a single-user demo**, not an anti-abuse control.
  Real quotas are Iteration 6.
- **Nobody has rehearsed the talk track out loud yet.** Every number in the guide is machine-checked;
  the delivery is not.

---

*Draft prepared 2026-08-05 at the end of Iteration 5 Phase 6. Send only after the prerequisites at the
top. Sources: [`AI_Jumpstart_MVP_Iteration5_handoff.md`](AI_Jumpstart_MVP_Iteration5_handoff.md),
[`../DEMO_GUIDE.md`](../DEMO_GUIDE.md) Option D,
[`../Iteration5_Plan_of_Action.md`](../Iteration5_Plan_of_Action.md) §4.*
