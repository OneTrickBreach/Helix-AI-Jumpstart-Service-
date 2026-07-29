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
| **API (direct)** | `http://localhost:8080` |
| **One-command setup** | `make demo` |
| **Hardware** | NVIDIA GB10 (arm64, Grace Blackwell, ~121 GiB unified memory) |
| **Stack** | 4 containers: `web` (nginx), `api` (FastAPI), `llm` (vLLM/Nemotron 30B), `vectordb` (Qdrant) |
| **Test suite** | 69 passed + 2 xpassed (71 total) |
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
`http://localhost:8081?replay=true`.

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
make test          # 69 passed, 2 xpassed (71 total)
```

The 2 xpassed tests are GPU-probe tests for a known NVML initialization issue after container
recreation — CUDA is working (the LLM and optimizer both use it). This is documented and expected.

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
real live run on this GB10.

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
- Classical wins clearly (7.2% cost reduction)

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

> "The current prototype runs entirely on one GB10. Peak is about 65–68 GiB of the ~121 GiB usable
> unified memory pool — over 55 GiB of headroom. We ran a scale study up to 100x the base data
> volume (28,800 time series) and memory stays at ~54% at every level. The binding constraint is
> forecast latency (~25ms per series), not memory or compute. The optimizer itself is trivially
> fast — under 0.4 seconds even at 100x. If scaling beyond one node is needed, the GB10 supports
> 2-node NVLink/RoCE clustering, but the ceiling hasn't been hit."

### "What's next?"

> "This is demo/pilot-ready — Iteration 3. The next step (Iteration 4) is production: real
> customer-data onboarding (ETL, schema mapping, access control), hardening, multi-tenant
> isolation, and packaging as a shippable appliance. cuOpt is now available for this platform and
> ready for future fleet-routing use cases with 100+ stops, if a customer needs it."

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
> recreation — but the LLM generated the advisory in ~15 seconds at 47 tokens/sec, which proves
> the GPU is working."

### Results are needed instantly without waiting

Use the recorded replay: `http://localhost:8081?replay=true`

Or click the **Replay** button in the UI header. This loads a pre-recorded real run from the GB10
(component-shortage-shock scenario, captured live).

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
