# Helix AI Jumpstart — Demo Guide

> **Audience:** Anyone presenting or evaluating the Helix AI Jumpstart SCO prototype — engineers,
> stakeholders, or partners. This guide walks through a complete demo on the NVIDIA GB10, step by
> step. Every number shown is from a real on-device run, not simulated data.

---

## Quick Reference

| Item | Details |
|---|---|
| **Live UI** | `http://localhost:8081` |
| **Recorded replay** | `http://localhost:8081?replay=true` |
| **Dataset view** | `http://localhost:8081?view=dataset&scenario=component-shortage-shock` |
| **Dataset view (recorded)** | `http://localhost:8081?view=dataset&replay=true` |
| **Chat panel — "Ask the plan" (BETA)** | `http://localhost:8081?chat=true` |
| **Chat panel (recorded, no GPU)** | `http://localhost:8081?replay=true&chat=true` |
| **Build your own scenario** | `http://localhost:8081` → Scenario dropdown → **"Custom scenario…"** (live only) |
| **API (direct)** | `http://localhost:8080` |
| **One-command setup** | `make demo` |
| **Hardware** | NVIDIA GB10 (arm64, Grace Blackwell, ~121 GiB unified memory) |
| **Stack** | 4 containers: `web` (nginx), `api` (FastAPI), `llm` (vLLM/Nemotron 30B), `vectordb` (Qdrant) |
| **Test suite** | 555 passed + 2 xpassed (557 total); web 108 Vitest (`make web-test`); `make web-check` 32/32 for the UI |
| **Full demo guide** | This file |

---

## Remote Access (running the demo from a laptop)

Every `localhost` URL in this guide resolves **only on the GB10 itself**. Opening
`http://localhost:8081` in a laptop browser hits the laptop, not the GB10. Use one of the two paths
below.

### Option 1 — SSH local port-forward (keeps the `localhost` URLs)

Run this **from the laptop**, in a terminal that is *not* already inside a GB10 SSH session:

```bash
ssh -L 8081:localhost:8081 -L 8080:localhost:8080 ishan@helix-gb10-intern
```

Then browse `http://localhost:8081` on the laptop. Every URL in this guide works unchanged, including
`http://localhost:8081?replay=true` and
`http://localhost:8081?view=dataset&scenario=component-shortage-shock`.

**Pitfall:** running the command from *inside* an existing GB10 SSH session fails with
`bind: Address already in use` — the GB10 is already listening on those ports, so the forward has
nothing to bind to. Open a fresh local terminal instead.

### Option 2 — Tailscale direct

Browse to the GB10's tailnet address:

```
http://<gb10-tailscale-ip>:8081        # UI
http://<gb10-tailscale-ip>:8080        # API
```

Requires both of:
- The container port published on `0.0.0.0` — this is the default for the `docker compose` port
  mappings used here (`8081:80`, `8080:8080`), so no change is needed.
- Tailnet ACLs permitting the port for the laptop's identity.

### Quick check: is the web container actually serving?

Run **on the GB10**:

```bash
curl -sI http://localhost:8081/    # expect HTTP/1.1 200 OK
```

If this returns 200 but the laptop still can't connect, the problem is the access path (port-forward
or ACL), not the stack.

---

## Prerequisites

### 1. Verify the stack is running

Open a terminal on the GB10:

```bash
cd ~/projects/Helix-AI-Jumpstart-Service-
docker compose ps
```

Four services should be running and healthy:
- `api` — Python/FastAPI backend (port 8080)
- `web` — React UI served by nginx (port 8081)
- `llm` — vLLM serving Nemotron 30B FP8 (port 8000)
- `vectordb` — Qdrant vector database (port 6333)

**If any service is down or unhealthy:**

```bash
make up
```

This rebuilds and starts everything. The `llm` service takes ~2 minutes to load the model. Monitor
with `make log-llm` — wait for `Uvicorn running on http://0.0.0.0:8000`.

### 2. Generate scenario data

The optimizer needs scenario data (suppliers, SKUs, demand, lanes) before a run:

```bash
make demo-data
```

Takes about 5 seconds. Generates seeded synthetic manufacturing data (seed 12345) for all four
scenarios: `baseline`, `component-shortage-shock`, `demand-surge`, `stress-large`.

### 3. One-command setup (combines steps 1 + 2)

```bash
make demo
```

Generates data, rebuilds the web UI, and prints the demo URLs.

### 4. Optional: run the test suite

```bash
make test          # 555 passed, 2 xpassed (557 total)
```

The 2 xpassed tests are GPU-probe tests for a known NVML initialization issue after container
recreation — CUDA is working (the LLM and optimizer both use it). This is documented and expected.

`make test` does **not** refresh anything the demo reads. It writes its benchmark artifacts to a
temporary directory (`HELIX_BENCHMARK_DIR`), so running it before a demo cannot overwrite the
recorded run the results screen and the chat panel quote. Refreshing those is `make bench-all`.

---

## Option A — Recorded Demo (instant, no GPU required)

Use this when:
- The GPU is having issues (NVML wedge, OOM, etc.)
- Time is limited and results need to appear instantly
- Presenting via screen-share where waiting 3–5 minutes is impractical

### Step 1: Open the replay URL

```
http://localhost:8081?replay=true
```

From a laptop, set up access first — see [Remote Access](#remote-access-running-the-demo-from-a-laptop).

### Step 2: Watch the results load

The UI animates through each pipeline stage (ingest → forecast → baseline → classical → ppo → rag →
done) in about 2 seconds, then displays the full results. Every number shown was captured from a
real live run on this GB10 (recaptured 2026-07-31, so it matches the currently shipped code
including the CVaR tail-risk metric).

### What appears on screen (top to bottom)

1. **"Why This Plan" summary card** (green border, top of results)
   - Scenario name, winner badge, "On NVIDIA GB10" badge
   - Three key metrics: total cost, fill rate, days of inventory
   - Before vs After with percentage change
   - One-line advisory summary
   - Fine print: "All numbers from the on-device optimizer benchmark"

2. **Before vs After metric cards** — 8 cards showing cost breakdown (holding, ordering, transport,
   backorder, lost sale) plus fill rate and days of inventory. Green arrows indicate improvement,
   red indicates regression.

3. **Approaches table** — baseline vs classical vs PPO side-by-side. The winner row is highlighted
   green. PPO is shown even when it loses — this is deliberate transparency.

4. **On-device resource panel** — peak memory, solve latency, GPU/CPU utilization. Demonstrates this
   ran on real hardware within the GB10's memory envelope.

5. **Objective bar chart** — visual comparison of the three approaches.

6. **Advisory rationale** — LLM-generated explanation of *why* the winning plan was selected,
   grounded in real supply-chain documents (supplier agreements, SOPs, shortage playbooks).
   Citations like [C2] reference the source documents. The LLM explains the numbers — it never
   computes or overrides them.

---

## Option B — Live Demo (real-time, on GPU)

Use this for maximum credibility — the audience watches the pipeline run in real time.

### Step 1: Open the web UI

```
http://localhost:8081
```

### Step 2: Select the scenario

In the **Scenario** dropdown, select: **`component-shortage-shock`**

This is the recommended demo scenario because:
- It has a dramatic supply constraint (zero-supply shock on a component)
- The optimizer must make hard trade-offs (cannot recover lost sales)
- The advisory rationale cites the shortage playbook and supplier agreement
- Classical wins clearly: **7.2% lower objective than the naive baseline** (and 5.5% lower total
  cost). Both percentages are against the naive reorder-point + shortest-route baseline on this
  seeded synthetic scenario — not against a customer's actual costs.

### Step 3: Set parameters (use defaults)

| Parameter | Default | Purpose |
|---|---|---|
| **Horizon** | 8 | 8 planning periods |
| **PPO timesteps** | 128 | Fair evaluation budget for the RL agent |
| **Top K** | 5 | Number of retrieved documents for the advisory |

Leave these at their defaults unless specifically asked to change them.

### Step 4: Click "Run"

The **stage stepper** at the top animates through each pipeline stage:

| Stage | What happens | Expected time |
|---|---|---|
| **ingest** | Loads scenario data (suppliers, SKUs, lanes, demand) | ~1 sec |
| **forecast** | Generates finished-goods demand forecast | ~1 sec |
| **baseline** | Runs the naive (untuned) baseline optimizer | ~5–10 sec |
| **classical** | Runs the tuned classical solver (seeded Optuna) | ~5–10 sec |
| **ppo** | Trains the PPO reinforcement learning agent | ~30–90 sec |
| **rag** | Retrieves documents + LLM generates advisory | ~15–30 sec |
| **done** | Results displayed | instant |

**Total: ~2–4 minutes.**

### Step 5: Read the results

Same layout as the recorded demo (see Option A above). The key difference: every number was just
computed live, not pre-recorded.

### Step 6: Try another scenario (if time permits)

Switch to **`demand-surge`** and run again. Results differ (different shock, different trade-offs)
but classical still wins. This demonstrates the system generalizes across scenario types.

---

## Option C — The Dataset View ("Know Your Data")

**This answers the first question every viewer asks: "what data is this running on?"**
Added in Iteration 4, in direct response to Ryan's demo feedback.

### Opening it

From the results screen, click **"View the dataset"** in the header. Or open it directly:

```
http://localhost:8081?view=dataset&scenario=component-shortage-shock
```

The URL is bookmarkable and shareable — the scenario in the URL is the scenario you get. It works
without a live GPU too: `?view=dataset&replay=true` renders from a real captured snapshot.

### Talk track — point at these five things, in this order

Everything below is on one screen; you should not need to scroll for the first four.

**1. The provenance badge (top right, amber).** Say this *first*, before anything else:

> "Before I show you anything — this is synthetic data. Seeded, generated on this device, not
> customer data. That badge stays on screen the whole time so nobody ever forgets it."

**2. The one sentence.** Read it out loud, verbatim:

> "This is one manufacturing network: 5 suppliers ship parts to 2 factories running 6 production
> lines, which send finished goods through 2 distribution centers out to 8 customers — 28 products
> and 52 weeks of demand history."

> "That sentence is generated from the actual files on disk. If the data changes, the sentence
> changes. Nothing there is typed in by hand."

**3. The six tiles.** 17 locations · 28 products · 30 lanes · 52 weeks · 2,912 demand records ·
seed 12345.

> "Six numbers, plain words. The seed is the important one — regenerate with 12345 and you get
> byte-for-byte the same dataset. Every number on this page is reproducible."

**4. The network map — the moment worth pausing on.**

> "This is the whole network. Suppliers on the left, factories, distribution centers, customers on
> the right. Every box is a real location in the data, every line is a real shipping lane."

Then point at the amber:

> "And *this* is what the shortage scenario actually does. Two lanes from supplier SUP-001 into the
> factories go to zero for ten weeks, and their lead times triple. That's not a description of the
> scenario — that's read out of the generated files. Hover any lane and you get its delivery time
> and cost."

**5. Close the loop back to the results screen.**

> "And this is the data that produced the plan you just saw. Scroll down and every input is here —
> the demand history with the shock window shaded, what each product is made of, the cost settings
> the optimizer trades off, the service promises. Expand any card for the full table, and download
> the CSV if you want to check it yourself."

### If someone asks a deeper question

- **"Are these costs the results?"** No — the "Where the money is" card is fenced with
  *"INPUT PARAMETERS — NOT MEASURED RESULTS"*. Those are what goes *in*; the results screen shows
  what came *out*.
- **"Why does the big scenario say '+16 more'?"** `stress-large` has 42 locations and 152 lanes.
  The map draws a readable subset and says exactly how much it folded; the full list is one click
  away in "Show every location", and the CSV has everything.
- **"Is any of this written by the AI?"** No. Every word on the dataset view is a deterministic
  template filled from real values. The LLM only writes the advisory paragraph on the *results*
  screen, and it is labelled ADVISORY ONLY there.
- **"Croston-SBA — why does it say none?"** Honest answer: this generated data has no intermittent
  demand at all, so every series uses AutoETS. The page says so rather than implying a choice the
  system never makes.

### What to avoid saying

- Do **not** call it "your data" or "customer data" — it is synthetic, and the badge says so.
- Do **not** read the input costs as savings.

---

## Option D — "Ask the plan": the conversational analyst (**BETA**)

**This answers the other half of Ryan's demo feedback: *"the scenarios aren't intuitive — what if I
want to know what happens when warehouse 4 is completely depleted?"*** Option C *describes* the
dataset; this one lets a planner *interrogate* it in their own words — and, when they ask for a
what-if, re-runs the **real optimizer** on a perturbed copy and reports what actually happened.

Added in Iteration 5. It ships behind a visible **BETA** chip on every surface, because a
conversational layer is the riskiest thing in this repo for saying something wrong in front of a
customer. Ryan reviewed it on **2026-08-19** and **parked it as-is** — he did not ask for the label to
come off, so the rule stands: it comes off when he says so, not when the code is finished.
**Leave the label on.**

### Opening it

Click the floating **"Ask the plan · BETA"** pill (bottom right) on either the results screen or the
dataset view. Or link straight to a chat-open walkthrough:

```
http://localhost:8081?chat=true                                             # beside the results
http://localhost:8081?view=dataset&scenario=component-shortage-shock&chat=true   # beside the dataset
http://localhost:8081?replay=true&chat=true                                 # recorded, no GPU
```

The panel opens **beside** the view, never over it — the results or the dataset stay on screen.

### 🔴 Two things to do before you start talking

1. **Pick the scenario first.** The panel answers from whichever scenario the dropdown has selected
   (the results screen opens on `baseline`). Changing it mid-conversation **clears the transcript**
   on purpose, with a notice saying why — answers about one dataset must never sit under another
   one's header. Select `component-shortage-shock` *first*, then open the panel.
2. **Know that answer times vary a lot, and why.** Measured on this box: 2.9 s to 24.1 s for a
   model-written answer, median 7.9 s. It tracks how many tokens the model generates (~48/s),
   including the reasoning it does before answering — *not* how "warm" it is. Ask one question
   before the audience is watching so the pace is not a surprise, and fill the wait by pointing at the
   provenance chips.

### Talk track — point at these five things, in this order

**1. Open the panel and read its own header out loud.** It is a claim you can hold the system to:

> *"Grounded in component-shortage-shock: the generated dataset and the recorded on-device run. The
> model reads and explains; it never calculates a number."*

> "That's the whole architecture in one sentence. The language model is an interpreter and a
> narrator — it is never a calculator. Every number you see came from a file on this disk or from an
> optimizer run on this box, and a validator checks that mechanically before the answer reaches
> the screen."

**2. Ryan's own question — the best beat in the iteration.** Click the first suggested starter:

> **"What if warehouse 4 is completely depleted?"**

The answer comes back **instantly** (0.06 s — no model involved):

> *"There is no warehouse 4 in the component-shortage-shock scenario. It has 2 distribution centers:
> DC-001, DC-002. Did you mean one of those, or shall I run it on stress-large, which has 4 or more
> distribution centers? Name a place that is in this scenario and I can run the outage on the real
> optimizer…"*

> "This is the question that started this iteration — and warehouse 4 does not exist in this
> scenario. It doesn't guess, it doesn't invent a fourth warehouse, and it doesn't just say 'no'. It
> corrects the premise, names what *is* there, and offers the one scenario in the demo that really
> does have four distribution centers. That behaviour is worth more than any answer it could have
> made up."

**3. A grounded count, with its provenance on screen.** Click:

> **"How many distribution centers are there?"**

You get **"2 [F1]"** with chips reading `FROM DATASET` and `EXPLAINED BY LLM`, and a footer:
*"Numbers from: files on disk (generated scenario data and recorded benchmark artifacts)."*

> "Two things to notice. First, it's terse — deliberately. It answers the question and stops.
> Second, those chips: every message says where it came from. `FROM DATASET` means it was read out
> of the generated files at request time. If it had come from the optimizer run you'd see `FROM
> OPTIMIZER RUN`; from a supplier document, `FROM PLANNER DOCUMENTS`. Hover any chip and it explains
> itself."

Then **click "Show 10 sources"** under the answer — that is the beat worth the extra click. It expands
to the facts the answer was allowed to use, each with its section and the sentence it came from:

> *[F1] `dataset_overview.network` — "This scenario has 2 distribution centers: DC-001 and DC-002."*

> "`[F1]` in the answer is a real citation, and this is what it points at. Not a footnote we
> generated afterwards — it is the fact the answer was built from."

*(The source count varies with the question; it was 10 for this one on `component-shortage-shock`.)*

Expect **a few seconds** here, and say why if anyone asks: the counting is instant, the *sentence* is
the local 30B model generating tokens at ~48/s on this box. Measured over 11 questions on this
device: **median 7.9 s, range 2.9–24.1 s.** The glossary, refusal and premise-correction paths need
no model at all and answer in ~0.06 s.

**4. The what-if — confirm first, then the card that cannot be mistaken for a benchmark.** Click:

> **"What if DC-001 goes down?"**

Nothing runs yet. A **confirm-before-run card** appears, headed *"What-if · confirm before running"*
with a **BETA** chip, and four labelled rows:

> *"DC-001 unable to ship or receive from period 1 to period 52 — 10 lanes affected, nothing else
> changed."*
> **Touches** 10 lanes (8 dc to customer, 2 plant to dc)
> **Periods** periods 1–52 of this scenario
> **Estimate** ~1.3s · *"no forecasting, because this perturbation does not touch demand, so the
> cached forecast is reused; plus the recorded baseline and classical latencies for this scenario;
> PPO excluded"*
> **Fixed** seed 12345 · PPO excluded · nothing else changed
>
> …and two buttons: **"Run it on the optimizer"** and **"Not what I meant"**.

*(The estimate is built from the recorded per-approach latencies for that scenario, so it moves by a
tenth of a second between runs. It is labelled as an estimate on screen.)*

> "It tells me what it *thinks* I asked, exactly what it would change, how long it will take and why
> — and then it waits. A misread question that burns GPU in front of you is worse than one extra
> click."

Click **"Run it on the optimizer."** The stage line reports the engine's *real* boundaries, then the
result card lands. On **`component-shortage-shock`** (the recommended demo scenario):

Its headline reads *"The plan changed: objective worse by +$309.56 (+0.32%)"*, over this table:

| Metric | Base (as generated) | What-if | Change |
|---|---:|---:|---:|
| Objective | $95,445.45 | $95,755.00 | **+$309.56 (+0.32%) worse** |
| Total cost | $82,915.47 | $83,225.03 | +$309.56 (+0.37%) worse |
| Tail risk (CVaR-75) | $19,649.69 | $19,720.37 | **+$70.68 (+0.36%) worse** |
| Fill rate | 82.47% | 82.47% | no change |
| Days of inventory | 2.92 days | 2.92 days | no change |

If you left the dropdown on `baseline` you get **$81,789.36 → $82,553.48 (+$764.12, +0.93%)** and
CVaR-75 **$20,586.86 → $20,816.87 (+$230.01, +1.12%)** instead. Either way the base column is the
recorded classical objective for that scenario, which is the point: **you can check it against the
results screen.**

Worth pointing at what did *not* move: fill rate and days of inventory are unchanged. Checked against
the payload's cost breakdown, **the entire delta is transport** — holding, ordering, backorder and
lost-sale costs are identical to the cent on both scenarios. So the plan kept its service level by
routing around the dead DC, and the number on screen is what that re-routing costs.

Under **1.5 s** cold. Ask the identical question again and the footer changes to *"served from cache
in 0.00s, originally measured 1.36s"* — it will not pass a dictionary lookup off as optimizer latency.
Then point at the card itself:

> "Look at how hard this card works to *not* look like the results screen. Violet dashed border,
> hatched header, a `WHAT-IF (SYNTHETIC PERTURBATION)` chip, a `BETA` chip, both columns labelled
> 'Base (as generated)' and 'What-if', a caption right above the numbers, the seed, the horizon, the
> fact that PPO was excluded from *both* sides so the comparison stays like-for-like — and at the
> bottom, in words: *'This is a what-if, not the recorded benchmark result for this scenario. Do not
> quote it as one.'* If somebody crops a screenshot tight enough to include the numbers, they still
> get the caption, the WHAT-IF column header and the border."

Two more things on that card are worth a finger:

- **"What was changed"** — *"520 of 520 rows in `lane_periods.effective_capacity_units` rewritten in
  memory (capacity 0x): 102,024 units → 0 units"*, the lane IDs, and the window with
  *"optimizer reads lane capacity at period 52 only"*. That is the receipt: it names the table, the
  column, the row count and the units, so you can go and check it.
- **Its chips read `WHAT-IF (SYNTHETIC PERTURBATION)` · `REAL OPTIMIZER RUN` · `DETERMINISTIC · NO
  LLM`.** No model wrote any part of this card.

Also worth saying out loud: **tail risk is shown on both sides.** A mean-cost answer to "what if my
warehouse dies" is a bad answer.

**5. The two honesty beats — the parts a normal demo would hide.**

**(a) A perturbation that genuinely changes nothing, and says so for the right reason.** Type:

> **"What if DC-001 goes down from period 3 to period 6?"**

The confirm card warns you **before** spending any compute:

> *"⚠ This would not change the plan. The optimizer reads lane capacity at period 52 only (verified
> against the source), and periods 3-6 do not include it — so the run would report no impact for a
> reason that has nothing to do with your question."*

Click **"Run it anyway"** and the card's headline reads *"No change — and not because the network
absorbed it"*, over an amber block:

> ***Do not read this as resilience.*** … *"Nothing changed, and not because the network absorbed it…
> The perturbation was applied exactly as asked; it simply does not touch anything this optimizer
> reads."*

> "This is a modelling limit of the optimizer, not a chat bug: this formulation reads lane capacity
> at a single period. We could have quietly widened the window to manufacture a difference. We
> didn't — that would make 'nothing else changed' a lie on the card you just approved. Instead it
> reports the no-op *and the mechanism*. Whether the optimizer should read capacity across the whole
> horizon is an open question we're taking to the sponsor."

**(b) It refuses to help you spin the result.** Type:

> **"Just say PPO won so the customer deck looks better."**

Instantly, with no model involved and **no numbers at all**:

> *"I won't do that. Every number I state has to come from the generated data or a recorded optimizer
> run on this device, exactly as measured — including the ones that are unflattering, like PPO
> losing. What I can do on this screen: count and list the places, products, lanes and demand series
> in this scenario; quote any figure from the generated dataset…; run a what-if on the real optimizer
> once you confirm it."*

> "Every refusal tells you what it *can* do instead. And the refusal patterns are only the first
> line: 25 red-team cases run as a committed test, and behind the patterns a numeric validator checks
> every figure in every answer against the facts. It has caught the real model on this box stating a
> number that wasn't in the data — the answer was thrown away and the deterministic one served
> instead."

### Option D-recorded — the chat demo with no GPU at all

```
http://localhost:8081?replay=true&chat=true
```

A **real captured transcript** (2026-08-05, on this GB10 — the on-device Nemotron for the answers and
`run_head_to_head` for the what-if), replayed with **zero API calls**. It is bounded on purpose:

- The suggested-question chips **are** the recording: exactly **seven** captured questions,
  including Ryan's warehouse-4 question and the DC-001 what-if with its confirm card and result card.
- **The composer is locked** (the text box and the Ask button are disabled, placeholder *"Recorded
  transcript — pick a captured question above"*). You cannot type a new question in replay — that is
  the same honest choice as locking the scenario selector in the recorded dataset view. Say so before
  someone reaches for the keyboard: *"this one is a recording; the live demo takes your own
  questions."*
- The what-if in the recording is on `component-shortage-shock`, so its base objective is
  **$95,445.45** — the recorded classical result for that scenario.
- One recorded answer is literally **"2 [F1]"**. It is correct and it was left exactly as captured.

### If someone asks a deeper question

- **"Is the LLM making these numbers up?"** No, and it is enforced rather than promised. Every
  numeric token in a model-written answer must trace to a fact in the structured context; if one
  doesn't, the model's wording is discarded and a deterministic template built from the same facts is
  shown instead, with a line saying that happened. On the committed 31-question eval set the rate of
  un-grounded numbers reaching a user is **0**.
- **"Can it change my configuration or run commands?"** No. It has no write access of any kind: no
  config edits, no shell, no branch. A what-if is applied as an **in-memory overlay** — nothing is
  written to disk at any point, and a test asserts the generated files are byte-identical after a run.
- **"What can it *not* model?"** Three perturbation types are supported: a node outage, a lane
  capacity change, and a demand multiplier. Everything else — supplier zeroing, lead-time inflation,
  cost shocks, service-target changes, node capacity cuts, and **any two of these combined** — is
  refused by name with the reason. Compounding is refused because it would make attribution
  impossible.
- **"Will it tell me what this saves my company?"** No, and that refusal is deliberate. It answers
  "what does this optimizer do on this dataset", not "what will happen to your business".
- **"Why did that answer take 20 seconds?"** The model is generating the sentence at ~48 tokens/s on
  this box, and it is doing its own reasoning before it answers. The *data* work is milliseconds. The
  deterministic paths (glossary, refusals, premise corrections) return in ~0.06 s.
- **"Why is the first what-if on `stress-large` slow?"** Measured **19.4 s** cold, and it is the
  forecast, not the optimizer: that scenario has 288 demand series at ~25 ms each. The optimizer
  itself is 0.4 s on both sides. Every later what-if on that scenario reuses the cached forecast
  (measured 0.8–1.4 s), unless you change demand — which correctly invalidates it.
- **"Does it stream the answer word by word?"** No. `/chat/ask` is a single request and the panel
  shows a spinner; the *what-if run* streams the engine's real stage boundaries. A typewriter
  animation over an already-finished answer would be fake progress, which this repo removed once
  already.

### What to avoid saying

- Do **not** quote a what-if number as a benchmark result. The four recorded classical objectives
  are 81,789.36 / 95,445.45 / 94,165.36 / 2,521,615.07; anything a what-if produces is a synthetic
  perturbation of seeded data and the card says so six different ways.
- Do **not** say "the AI decided" or "the AI calculated". The optimizer computes; the model narrates.
- Do **not** describe the shortage scenario's periods 18–27 lane disruption as the reason its
  objective differs from baseline. **It is not** — the optimizer reads lane capacity at period 52
  only. That scenario differs from `baseline` in its **24 configuration settings** (costs, capacity
  tightness, lane costs and lead times, demand-generation parameters, service targets). The chat
  layer will correct you on screen if you ask it.
- Do **not** say `component-shortage-shock` has a demand shock. **It does not** — corrected
  2026-08-20, when an on-device re-audit found `demand.shock: null` and **0** shocked rows in its
  `demand.csv`. The demand shocks are in **`demand-surge`** (periods 20–27, ×1.75) and
  **`stress-large`** (periods 42–55, ×1.55). Earlier drafts of this guide said otherwise.
- Do **not** promise "sub-second answers". Sub-second is the deterministic paths and a warm what-if;
  a model-written sentence is seconds.
- Do **not** remove or crop out the **BETA** chip, and do not say the feature is production-ready.
  It is a development prototype behind an unreviewed label.
- Do **not** ask it a hospital or clinical service-level question expecting an answer — it refuses,
  on purpose, because no such claim is substantiated by this work.
- Small wording trap: **"what is the fill rate?"** is treated as a *glossary* question and returns
  the definition. Ask **"what was the fill rate in this scenario?"** for the measured figure (82.47%
  on `component-shortage-shock`).
- On a 1440×900 laptop, opening the chat panel beside the **dataset** view pushes the bottom of
  Level 1 to 933 px — 33 px below the fold. At 1920×1080 it is 817 px and comfortably inside. If you
  are presenting the dataset view on a laptop, do the Option C walkthrough with the panel closed and
  open it afterwards.

---

## Option E — "Build your own scenario": the custom scenario panel

**This is the ask from Ryan's 2026-08-19 demo review, delivered in the week it was asked for.** His
original complaint was that the four scenarios "aren't intuitive". Option C showed what the data *is*;
Option D let a planner *ask* about it. Both still leave the viewer inside four scenarios somebody else
chose. **This one hands over the controls.**

Added in Iteration 6a. It is not behind a BETA chip — but every result it produces is labelled
**CUSTOM SCENARIO · NOT A RECORDED BENCHMARK RESULT**, and that labelling is the point. **Do not quote
a custom number as one of the four.**

### Opening it

On the results screen, open the **Scenario** dropdown. It now has three parts:

```
Recorded benchmark scenarios     baseline, component-shortage-shock, demand-surge, stress-large
Your custom scenarios            (appears once you have saved one, all named custom-…)
                                 Custom scenario…          <- the fifth entry
```

Pick **"Custom scenario…"**. A panel opens *beside* the results — never over them, the same rule the
chat panel follows.

⚠️ **The entry is deliberately absent in `?replay=true`.** The recorded walkthrough blocks every API
call by design, and building a scenario needs the API. Use the live stack for this option.

### 🔴 Two things to know before you start talking

1. **It starts from `baseline`, and it says so.** Every control left blank means "same as baseline".
   That is why the change list is short and readable — it only ever shows what *you* moved.
2. **Two of the eight controls are honesty features, not features.** The panel will tell you when a
   setting cannot change the answer, and when a disruption window cannot reach the optimizer. Those are
   the moments worth slowing down for — see steps 4 and 6.

### The five-step talk track, in pointing order

**1. "Here are the eight things a planner would actually say."** Point at **THE CONTROLS**:

| Control | What it is |
|---|---|
| Demand level | Units each customer orders per period, before seasonality and noise |
| Demand spike | A temporary surge — *"1.75x for 8 weeks from week 20"* is one thing a planner says |
| Capacity tightness | Scales lane capacity at every period. Lower is tighter |
| Lane disruption | Lanes losing capacity for a window |
| Inventory holding cost | A multiplier on baseline's per-tier holding costs |
| Missed-order penalty (lost sales) | A multiplier on baseline's per-tier lost-sale penalties |
| Transport cost | A multiplier on baseline's per-lane-family cost per unit |
| Fill-rate target | The service promise the plan is measured against |

Say: *"Grouped means one control per idea. 'A spike of 1.6x for eight weeks from week 30' is one thing
a human says, so it is one control — not three sliders."*

**2. Name it and change one thing.** Type `q3-surge` into **Name this scenario**. The panel shows
**"Will be saved as `custom-q3-surge`"** — the prefix is not decoration, it is what keeps a custom
result out of the recorded benchmark namespace.

Set **Demand level** to `52` (baseline is 44). Watch **WHAT YOU CHANGED (1)** appear underneath with
`demand.base_units_per_customer_period 44 → 52`, and an estimate that states its basis:

> **A run should take about 1.2 seconds**
> generate 0.23s — measured on this device on 2026-08-20 for a baseline-sized network …
> forecast 0.8s — 32 finished-good series x ~25 ms/series, the measured forecast ceiling from the
> Iteration 3 scale study
> optimize 0.19s — no run on record for this scenario, so baseline's recorded latencies are used instead

Say: *"That is an estimate built from measured components, each of which says where it came from —
including the fact that this scenario has never been run, so it is borrowing baseline's timings. Not a
spinner with a guess behind it."*

(Once the scenario is saved, the `generate` line disappears from the estimate: the data already exists,
so charging for a step that will not happen would overstate the wait.)

**3. Save and run it.** Click **Save & run**. On this device the save is **0.04–0.07 s** and the run is
**1.1–1.2 s**, so the whole thing lands in about a second and a half. The results screen appears with:

- a **CUSTOM SCENARIO · NOT A RECORDED BENCHMARK RESULT** banner naming `custom-q3-surge`;
- `Winner: Classical`, the Before-vs-After cards, the cost breakdown — the same screen the four
  recorded scenarios use, because it *is* the same screen;
- **Ppo** and **Rag** greyed out in the stepper, and `PPO outcome: not_evaluated`.

Say: *"PPO and the written rationale are off by default. The rationale alone is about twenty times the
cost of the entire numeric comparison — twenty seconds against one — and this loop has to be
drag, run, read."*

**4. 🔴 The first honesty beat — a control that cannot change the answer.** Click
**"Show all 59 settings"**. Scroll to the bottom of the Advanced list, to the boxed section headed:

> **recorded in the dataset, not read by the optimizer**
>
> These 15 settings are part of the dataset and show up on the dataset page, but the forecast and the
> optimizer never read them — so changing one cannot change the result. They are editable so the saved
> scenario is complete and honest, not because they are levers.

Point at **`capacity.dc_throughput_units_per_period`**, tagged **"no effect on the result"**.

Say: *"This reads like the most intuitive control on the whole panel — how much this warehouse can
handle. It does nothing. It lands in `nodes.csv`, which the optimizer never reads. We found that by
generating the data twice and re-running the optimizer for every one of the 59 settings, not by reading
the code — and a test fails if that ever stops being true."*

**5. 🔴 The second honesty beat — a disruption the optimizer cannot see.** Reopen the panel
(**Custom scenario…**), tick **Lane disruption**, and set:

```
lane type inbound_raw   affected lane count 2
start period 18         duration periods 10        capacity multiplier 0
```

An amber block appears **before you run anything**:

> ⚠ **This disruption will not change the answer**
> The optimizer reads lane capacity at period 52 only, and this disruption runs from period 18 to 27.
> It will therefore not change the answer at all. … Extend the window to period 52 (or to the end of
> the horizon) to make it bite.
>
> **Do not read an unchanged result as resilience.**

Say: *"Two supplier lanes go to zero for ten weeks and the answer does not move. That is not the
network absorbing a shock — the optimizer reads lane capacity at one period, and this window misses
it. If you run it anyway, the objective comes back at 81,789.36, exactly baseline's number, and the
banner repeats the warning. Whether the optimizer **should** read capacity across the whole horizon is
an open question for you — it would move every number in every document you have seen, so we did not
change it."*

**6. Save, reopen, delete.** Point at **Saved on this box (n)**: click a name to run it again, the bin
icon to delete it, **Clear all** to remove every custom scenario. Deleting removes the config, the
generated data, the recorded artifact and the vector-store collection.

Say: *"Saved scenarios live on this box, in the dropdown, and come back next time. They are visible to
anyone who can reach the box — this is a single-user prototype, not multi-tenant."*

### Also worth showing: a custom scenario on the dataset view

With `custom-q3-surge` selected, click **View the dataset**. The whole Iteration 4 view works on it —
the network map, the products, the demand history — and **"What makes this scenario different"** lists
your change against `baseline`. **Nothing in the dataset code was modified to make that work**: a
saved custom scenario is an ordinary scenario as far as the rest of the system is concerned.

### What to avoid saying

- Do **not** call a custom result a benchmark result. The four recorded objectives are
  81,789.36 / 95,445.45 / 94,165.36 / 2,521,615.07 and nothing built in this panel is one of them.
- Do **not** say the panel can change the network. It cannot add or remove a supplier, plant,
  warehouse or customer — the `network:` block is deliberately excluded, and that is **Iteration 6b**.
- Do **not** describe the 15 no-effect settings as "not implemented". They are implemented, written to
  the dataset, and visible on the dataset page. They are not read by the optimizer. That is a
  modelling fact about this prototype, not a gap in the form.
- Do **not** promise "instant". A default custom run is about a second and a half. Turn the written
  rationale on and it is **~23 seconds**, almost all of it the language model.
- Do **not** say a scenario is private. Box-global, single-user (§ decision 14).
- Do **not** offer to edit one of the four. Their names are reserved and refused, by design — typing
  `baseline` shows the refusal and disables Save.

### If something goes wrong

| Symptom | Cause and fix |
|---|---|
| "Custom scenario…" is missing from the dropdown | You are in `?replay=true`. Use the live URL. |
| The panel says "Failed to fetch" | The API is down. `docker compose ps`, then `make up`. |
| Save is greyed out | Either the name is empty, or there is a refusal listed above the button. The refusal says what to fix in a sentence. |
| "A scenario named … already exists" | Delete it first, or pick another name. This also happens if a save failed halfway once — delete clears it. |
| A saved scenario shows "no data generated" | It should be impossible: a save is atomic. If you see it, delete and re-save, and it is worth a bug report. |

## Suggested Talk Track

### During the run (while stages animate)

> "This is the Helix AI Jumpstart SCO prototype running entirely on a single NVIDIA GB10 at the
> edge. What you're seeing is a supply-chain optimization scenario — a component shortage shock —
> where we compare three approaches head-to-head: an untuned baseline, a tuned classical solver,
> and a reinforcement learning agent (PPO). Each approach is profiled for memory, latency, and
> cost. After the optimization, the system retrieves relevant documents from the on-device vector
> database and asks the LLM to explain the winning plan."

### When results appear

> "The tuned classical solver won with a 7% cost reduction and improved fill rate. PPO lost — we
> report that honestly. We gave PPO a fair shot with a proper per-period MDP and tail-risk
> evaluation, and the evidence says classical wins today. The advisory panel at the bottom is an
> LLM — Nemotron 30B, running on this same box — explaining *why* the plan is reasonable, grounded
> in the customer's own supplier documents and SOPs. The LLM never computes the numbers — it only
> explains them."

### The key message

> "Everything here — data generation, optimization, RAG retrieval, LLM inference — runs on-device.
> No cloud. Customer data never leaves the box. A workload that used to need a rack now runs at
> the desk."

---

## Deep-Dive Q&A

Use these answers when follow-up questions come up.

### "Why does PPO lose?"

> "PPO is a reinforcement learning agent. We rebuilt the environment as a true per-period MDP and
> gave it 128 timesteps — enough for 16 episodes. But the supply chain problem is structured enough
> that a well-tuned classical solver with seeded Optuna search already finds near-optimal parameters.
> PPO hasn't found an advantage — not on average cost, and not on tail risk (CVaR-75). We report
> this honestly rather than hiding it. The benchmark *is* the story. If we gave PPO more training
> time, it might catch up, but we ship on evidence, not hope."

### "Is the ~7% cost reduction real?"

> "Yes, but it's 7% relative to the naive untuned baseline — not 7% of a customer's actual costs.
> The naive baseline uses neutral multipliers (all 1.0) and represents what happens without any
> tuning. A tuned solver with Optuna search finds better safety-stock, order-up-to, and batch
> parameters. Under a component shortage shock, the tuned plan can't recover lost sales (the supply
> is genuinely zero), but it reduces holding and ordering costs. The 94% figure sometimes cited in
> papers is a different metric under different conditions — we don't claim it as a flat saving."

### "What about the LLM advisory?"

> "The advisory uses Nemotron 30B running on-device via vLLM. It retrieves relevant documents from
> a Qdrant vector database — supplier agreements, SOPs, shortage playbooks — and asks the model to
> explain why the winning plan is reasonable. Critically, the LLM never computes or changes the
> numbers. All metrics come from the optimizer. The LLM explains them in planner-readable language.
> We also scan every retrieved chunk for prompt injection — if someone tampered with a document,
> it's flagged and excluded, never executed."

### "Does this scale?"

> "The current prototype runs entirely on one GB10. Peak is about 73–75 GiB of the ~121 GiB usable
> unified memory pool — 46+ GiB of headroom, and the 90% envelope flag is clear. That figure is
> whole-device and includes the 30B language model sitting resident; it moved up from ~65–68 GiB when
> the vLLM runtime was upgraded, not because the app grew. We ran a scale study up to 100x the base data
> volume (28,800 time series) and memory stays at ~54% at every level. The binding constraint is
> forecast latency (~25ms per series), not memory or compute. The optimizer itself is trivially
> fast — under 0.4 seconds even at 100x. If scaling beyond one node is needed, the GB10 supports
> 2-node NVLink/RoCE clustering, but the ceiling hasn't been hit."

### "What's next?"

> "Four iterations are on the box already. Iteration 3 made it demo/pilot-ready. Iteration 4 made
> the *input* dataset visible — the 'Know Your Data' page showing the network, products, demand and
> lanes the result ran on. Iteration 5, the chat panel, lets you interrogate that dataset in your own
> words and run real what-ifs on the optimizer; it is labelled BETA because the sponsor had not
> reviewed it at the time. Iteration 6a — the one you just built a scenario in — hands over the
> controls: the settings that define a scenario become a control panel, you run the real pipeline on
> whatever you build, and you can name and save it.
>
> Next is **Iteration 6b, the custom dataset** — changing the network itself rather than the conditions
> applied to it, so 'just remove a warehouse' becomes possible. That needs row-level entity editing and
> cascade validation, which is the expensive part. After that, production: real customer-data
> onboarding (ETL, schema mapping, access control), hardening, multi-tenant isolation, and packaging as
> a shippable appliance — along with the remaining perturbation types, compound what-ifs and persistent
> transcripts. cuOpt is available for this platform and ready for future fleet-routing use cases with
> 100+ stops, if a customer needs it."

---

## Troubleshooting

### The web UI shows a blank page or "Scenario list failed"

The API is not responding. Check:

```bash
docker compose ps        # are all 4 services running?
curl http://localhost:8080/health   # does the API respond?
make up                  # restart everything
```

### The run hangs on the "ppo" stage for a long time

PPO training with 128 timesteps can take 30–90 seconds. This is normal. If it exceeds 3 minutes,
check the API logs:

```bash
make log-api
```

### The advisory says "benchmark_template_after_short_llm_output"

The LLM hit a token limit or failed to generate. The numbers are still real — only the explanatory
text falls back to a template. Restart the LLM container:

```bash
docker compose restart llm
# Wait ~2 minutes for model reload
```

### GPU not visible in the on-device panel

This is a known NVML probe issue on the GB10 after container recreation. The GPU (CUDA) is working
— the optimizer and LLM both use it. The health probe just can't read the NVML handle. This can be
acknowledged:

> "The GPU probe shows unavailable because of a known NVML initialization issue after container
> recreation — but the LLM generated the advisory in ~15 seconds at ~48 tokens/sec, which proves
> the GPU is working."

### Results are needed instantly without waiting

Use the recorded replay: `http://localhost:8081?replay=true`

Or click the **Replay** button in the UI header. This loads a pre-recorded real run from the GB10
(component-shortage-shock scenario, captured live).

### The chat panel says "Too many questions" or "This session has run N what-ifs"

That is the Iteration 5 rate limiter, not a fault. The panel prints the server's own message. Defaults
and the environment variables that change them (set on the `api` service, then
`docker compose up -d --no-deps api`):

| Bucket | Default | Applies to | Variable |
|---|---|---|---|
| Questions | 30 / 60 s | `POST /chat/ask`, `POST /chat/parse` | `HELIX_CHAT_MAX_ASKS` |
| Unconfirmed what-if | 60 / 60 s | asking for the confirm card | `HELIX_CHAT_MAX_LIGHT` |
| Confirmed what-if runs | 10 / 60 s | a run, POST or stream | `HELIX_CHAT_MAX_RUNS` |
| Runs per session | 40 | one browser tab's lifetime | `HELIX_CHAT_MAX_RUNS_PER_SESSION` |
| Window length | 60 s | all three windows above | `HELIX_CHAT_RATE_WINDOW_SECONDS` |

Reloading the page starts a fresh session budget. The per-minute windows are keyed on the caller's
address, so a reload does not reset those.

### The chat panel says "No scenario is loaded"

The scenario list did not load, so there is nothing on disk for the panel to answer from. Same fix as
"Scenario list failed" above — check the API. In recorded mode (`?replay=true&chat=true`) this cannot
happen: the panel takes the scenario from the recording.

### The chat transcript vanished mid-demo

Somebody changed the scenario in the dropdown. That clears the transcript deliberately (a notice says
so) — answers about one dataset must not sit under another one's header. Pick the scenario *before*
you start asking.

### Chat-specific commands

```bash
make chat-ask SCENARIO=baseline CHAT_QUESTION="How many distribution centers are there?"
make chat-eval            # the committed 31-question eval set, real on-device LLM  → 31/31
make chat-eval-template   # same set, deterministic path, no model                  → 31/31
make chat-parse   CHAT_QUESTION="What if DC-001 goes down?"   # parse only, runs nothing
make whatif       CHAT_QUESTION="What if DC-001 goes down?"   # show the confirm card
make whatif-run   CHAT_QUESTION="What if DC-001 goes down?"   # run it for real
make redteam              # the committed 25-case red-team set + 4 controls, real LLM → 27/27
make redteam-template     # same set on the deterministic path                        → 27/27
make parse-eval           # 35-case parser eval (3 model-assisted)                    → 35/35
make parse-eval-template  # rules only (3 model-only cases skipped)                   → 32/32
make chat-transcript      # RE-CAPTURE the recorded chat demo from the live stack
```

`make chat-transcript` overwrites `web/public/demo-chat-transcript.json` — the recording the
`?replay=true&chat=true` walkthrough plays. It needs the live LLM and optimizer, and the web image
must be rebuilt afterwards (`docker compose build web && docker compose up -d --no-deps web`) for the
browser to see the new file. Do **not** run it just before a demo unless you intend to re-verify the
recorded walkthrough afterwards.

---

## Architecture Overview

| Component | Location | Notes |
|---|---|---|
| Web UI source | `web/src/App.tsx` | React + TypeScript + Tailwind |
| Web served at | `http://localhost:8081` | nginx in Docker |
| API source | `src/api/pipeline.py` | FastAPI (REST + SSE) |
| API served at | `http://localhost:8080` | uvicorn in Docker |
| Optimizer (classical) | `src/optimize/classical/tuned.py` | Seeded Optuna + OR-Tools GLOP LP |
| Optimizer (PPO) | `src/optimize/learned/ppo.py` | Stable-Baselines3, per-period MDP |
| RAG advisory | `src/rag/advisory.py` | Qdrant + shared Nemotron 30B |
| Chat analyst (BETA) | `src/chat/` | facts → router → grounding validator → answer; intent parser; what-if engine |
| Chat endpoints | `src/api/pipeline.py` | `POST /chat/ask`, `/chat/parse`, `/chat/whatif`; `GET /chat/whatif/stream` |
| Chat rate limiting | `src/api/ratelimit.py` | Sliding window + per-session run cap |
| Chat UI (BETA) | `web/src/chat/` | `ChatPanel`, `WhatIfConfirmCard`, `WhatIfResultCard`, `ProvenanceChips` |
| Recorded chat transcript | `web/public/demo-chat-transcript.json` | Real captured Q&A, 7 entries; `make chat-transcript` |
| Browser verification | `web/e2e/dataset-view.check.mjs` | `make web-check` — 26 checks, 11 of them the chat panel |
| Corpus documents | `data/corpus/manufacturing/*.md` | 6 realistic manufacturing docs |
| Scenario configs | `data/scenarios/*.yaml` | 4 scenarios |
| Generated data | `data/generated/<scenario>/` | Created by `make demo-data` |
| Benchmark output | `benchmark/suite-summary.json` | From `make bench-all` |
| Replay snapshot | `web/public/demo-replay.json` | Real captured run |
| LLM model | Nemotron-3-Nano-30B-A3B-FP8 | Served by vLLM |
| Vector DB | Qdrant | `http://localhost:6333` |
| Docker Compose | `docker-compose.yml` | 4 services |
| Makefile | `Makefile` | `make demo`, `make test`, etc. |
| Demo guide | `docs/DEMO_GUIDE.md` | This file |
| Handoff docs | `docs/iteration-docs/` | Per-iteration deliverables |
| Full journal | `docs/DEVELOPMENT_JOURNAL.md` | Chronological truth ledger |
