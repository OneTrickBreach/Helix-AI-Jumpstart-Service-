# Helix AI Jumpstart — Complete Demo Guide

> **Audience:** You (Ishan), presenting to Ryan Spurr or recording a screen demo.
> This guide assumes you know nothing about how the frontend works. Follow it
> literally, step by step. Every number on screen is from a real on-device run on
> your NVIDIA GB10, not fake data.

---

## Quick reference

| What               | Where                                        |
|--------------------|----------------------------------------------|
| Web UI             | **http://localhost:8081**                     |
| Recorded replay    | **http://localhost:8081?replay=true**         |
| API (direct)       | http://localhost:8080                         |
| One-command launch | `make demo`                                  |
| Full demo guide    | This file                                    |
| Hardware           | NVIDIA GB10 (arm64, Grace Blackwell, ~121 GiB unified memory) |

---

## Part 0 — Before the demo (do this ahead of time)

### 0.1 Make sure the stack is up

Open a terminal on the GB10 and run:

```bash
cd ~/projects/Helix-AI-Jumpstart-Service-
docker compose ps
```

You should see **four services** running and healthy:
- `api` — the Python/FastAPI backend (port 8080)
- `web` — the React UI served by nginx (port 8081)
- `llm` — vLLM serving Nemotron 30B (port 8000)
- `vectordb` — Qdrant vector database (port 6333)

**If any service is down or unhealthy**, run:

```bash
make up
```

This rebuilds and starts everything. Wait ~2 minutes for `llm` to load the model
(it's a 30B parameter model). You can watch the logs:

```bash
make log-llm      # watch for "Uvicorn running on http://0.0.0.0:8000"
```

### 0.2 Generate the synthetic data

The optimizer needs scenario data (suppliers, SKUs, demand, lanes) to exist
before a run. Generate it for all four scenarios:

```bash
make demo-data
```

This takes about 5 seconds. It generates seeded synthetic manufacturing data
(seed 12345) for: `baseline`, `component-shortage-shock`, `demand-surge`,
`stress-large`.

### 0.3 Verify everything works (optional but recommended)

```bash
make test          # should show 58 passed (2 GPU-probe tests may fail on
                   # the known NVML issue — that's cosmetic, not real)
```

### 0.4 One-command launch (combines 0.1 + 0.2 + opens the URL)

```bash
make demo
```

This generates data, rebuilds the web UI, and prints the URL.

---

## Part 1 — The recorded demo (safe fallback, no GPU needed)

Use this if:
- The GPU is having issues (NVML wedge, OOM, etc.)
- You want to show results instantly without waiting 3–5 minutes
- You're doing a quick screen-share and time is tight

### Step 1: Open the replay URL

In your browser (on the GB10 or any machine that can reach it):

```
http://localhost:8081?replay=true
```

Or from a remote machine, replace `localhost` with the GB10's IP address.

### Step 2: Watch it load

The UI will show the stage stepper animating through each stage (ingest →
forecast → baseline → classical → ppo → rag → done) in about 2 seconds, then
display the full results.

### What you see (top to bottom)

1. **"Why This Plan" summary card** (green-bordered, at the top)
   - Scenario: "Component Shortage Shock"
   - Winner: Classical
   - Three key metrics: Total cost, Fill rate, Days of inventory
   - Before vs After with % change
   - A one-line advisory summary
   - Fine print: "All numbers from the on-device optimizer benchmark"

2. **Before vs After metric cards** — 8 cards showing cost breakdown (holding,
   ordering, transport, backorder, lost sale) + fill rate + days of inventory.
   Green arrows = improvement, red = regression.

3. **Approaches table** — baseline vs classical vs PPO side-by-side. The winner
   row is highlighted green.

4. **On-device resource panel** — peak memory, solve latency, GPU/CPU
   utilization. Shows this ran on real hardware.

5. **Objective bar chart** — visual comparison of the three approaches.

6. **Advisory rationale** — the LLM-generated explanation of *why* the classical
   plan was selected, grounded in real supply-chain documents (supplier
   agreements, SOPs, shortage playbooks). Citations like [C2] reference the
   source documents.

### What to say (talk track)

> "This is the Helix AI Jumpstart SCO prototype running entirely on a single
> NVIDIA GB10 at the edge. What you're seeing is a supply-chain optimization
> scenario — a component shortage shock — where we compare three approaches:
> an untuned baseline, a tuned classical solver, and a reinforcement learning
> agent (PPO).
>
> The tuned classical solver won with a 7% cost reduction and improved fill
> rate. PPO lost — we report that honestly. The advisory panel at the bottom
> is an LLM (Nemotron 30B, running on this same box) explaining *why* the plan
> is reasonable, grounded in the customer's own supplier documents and SOPs.
> The LLM never computes the numbers — it only explains them.
>
> Everything here — the data generation, the optimization, the RAG retrieval,
> the LLM inference — runs on-device. No cloud. Customer data never leaves the
> box."

---

## Part 2 — The live demo (real-time, on GPU)

Use this for maximum credibility — the audience watches the pipeline run in
real time on the GB10.

### Step 1: Open the web UI

```
http://localhost:8081
```

### Step 2: Select the scenario

In the **Scenario** dropdown, pick: **`component-shortage-shock`**

This is the best demo scenario because:
- It has a dramatic supply constraint (zero-supply shock on a component)
- The optimizer has to make hard trade-offs (can't recover lost sales)
- The advisory rationale cites the shortage playbook and supplier agreement
- Classical wins clearly (7.2% cost reduction)

### Step 3: Set parameters (leave defaults)

- **Horizon:** 8 (8 planning periods)
- **PPO timesteps:** 128 (fast enough for a demo, serious enough to be fair)
- **Top K:** 5 (5 retrieved documents for the advisory)

These are the defaults. Don't change them unless asked.

### Step 4: Click "Run"

The **stage stepper** at the top starts animating:

| Stage      | What happens                                    | Time     |
|------------|-------------------------------------------------|----------|
| **ingest** | Loads the scenario (suppliers, SKUs, lanes, demand) | ~1 sec   |
| **forecast** | Generates finished-goods demand forecast        | ~1 sec   |
| **baseline** | Runs the naive (untuned) baseline optimizer     | ~5–10 sec |
| **classical** | Runs the tuned classical solver (seeded Optuna) | ~5–10 sec |
| **ppo**    | Trains the PPO reinforcement learning agent     | ~30–90 sec |
| **rag**    | Retrieves documents + LLM generates advisory   | ~15–30 sec |
| **done**   | Results displayed                                | instant  |

**Total: ~2–4 minutes.** While it's running, you can narrate:

> "What you're seeing is the real pipeline executing on the GB10 right now.
> It's comparing three optimization approaches head-to-head: a naive baseline,
> a tuned classical solver, and a PPO reinforcement learning agent. Each one
> is profiled for memory, latency, and cost. After the optimization, it
> retrieves relevant documents from the on-device vector database and asks the
> LLM to explain the winning plan."

### Step 5: Read the results

Same layout as the recorded demo (see Part 1, "What you see"). The key
difference: every number was just computed live, not pre-recorded.

### Step 6: Try another scenario (if time permits)

Switch to **`demand-surge`** and run again. The results will differ (different
shock, different trade-offs) but classical still wins. This shows the system
generalizes across scenario types.

---

## Part 3 — Deep-dive talking points

Use these if Ryan asks follow-up questions or you want to go deeper.

### "Why does PPO lose?"

> "PPO is a reinforcement learning agent. In this prototype, it's exploring a
> policy space over 128 timesteps — enough for a fair evaluation, but the
> supply chain problem is structured enough that a well-tuned classical solver
> with seeded Optuna search already finds near-optimal parameters. PPO hasn't
> found an advantage yet. We report this honestly rather than hiding it — the
> benchmark is the story, and the evidence says classical wins today. If we
> gave PPO more training time or restructured the MDP (Phase 4 in the plan),
> it might catch up, but we ship on evidence, not hope."

### "Is the ~7% cost reduction real?"

> "Yes, but it's 7% *relative to the naive untuned baseline* — not 7% of the
> customer's actual costs. The naive baseline uses neutral multipliers (all
> 1.0) and represents what happens if you don't tune your inventory policy.
> A tuned solver with Optuna search finds better safety-stock, order-up-to,
> and batch parameters. Under a component shortage shock, the tuned plan
> can't recover lost sales (the supply is genuinely zero), but it reduces
> holding and ordering costs. The 94% figure you might see in papers is a
> different metric under different conditions — we don't claim it as a flat
> saving."

### "What about the LLM advisory?"

> "The advisory panel uses Nemotron 30B running on-device via vLLM. It
> retrieves relevant documents from a Qdrant vector database — supplier
> agreements, SOPs, shortage playbooks — and asks the model to explain why
> the winning plan is reasonable. Critically, the LLM never computes or
> changes the numbers. All the metrics come from the optimizer. The LLM
> just explains them in planner-readable language. We also scan every
> retrieved chunk for prompt injection — if someone tampered with a
> document, it's flagged and excluded, never executed."

### "Does this scale?"

> "The current prototype runs entirely on one GB10. Device peak is about
> 67 GiB of the ~121 GiB usable unified memory pool — over 50 GiB of
> headroom. Even the stress-large scenario (which is 4x the data volume)
> stays single-node. The binding constraint is memory bandwidth (~273 GB/s),
> not capacity. If we needed to scale beyond one node, the GB10 supports
> 2-node NVLink/RoCE clustering, but the ceiling hasn't been hit yet."

### "What's next?"

> "This is demo/pilot-ready — Iteration 3. The next step (Iteration 4)
> is production: real customer-data onboarding (ETL, schema mapping, access
> control), hardening, multi-tenant isolation, and packaging as a shippable
> appliance. We're also giving PPO a fair MDP rebuild (Phase 4 in the plan)
> — if it wins on evidence, it ships; if not, it stays evaluated-not-shipped."

---

## Troubleshooting

### "The web UI shows a blank page or 'Scenario list failed'"

The API isn't responding. Check:

```bash
docker compose ps        # are all 4 services running?
curl http://localhost:8080/health   # does the API respond?
make up                  # restart everything
```

### "The run hangs on the 'ppo' stage for a long time"

PPO training with 128 timesteps can take 30–90 seconds. This is normal. If it
goes past 3 minutes, check the API logs:

```bash
make log-api
```

### "The advisory says 'benchmark_template_after_short_llm_output'"

The LLM hit a token limit or failed to generate. This is the safety fallback —
the numbers are still real, only the explanatory text is a template. Restart
the LLM container if this persists:

```bash
docker compose restart llm
# Wait 2 minutes for model reload
```

### "GPU not visible in the On-device panel"

This is the known NVML probe issue on the GB10 after container recreation.
The GPU (CUDA) is actually working — the optimizer and LLM both use it. The
health probe just can't read the NVML handle. You can mention this honestly:

> "The GPU probe shows unavailable because of a known NVML initialization
> issue after container recreation — but you can see the LLM generated the
> advisory in ~15 seconds at 47 tokens/sec, which proves the GPU is working."

### "I want to show results instantly without waiting"

Use the recorded replay:

```
http://localhost:8081?replay=true
```

Or click the **Replay** button in the UI header. This loads a pre-recorded
real run from the GB10 (component-shortage-shock scenario, captured live).

---

## Appendix: What lives where

| Component             | Location                                         |
|-----------------------|--------------------------------------------------|
| Web UI source         | `web/src/App.tsx` (React + TypeScript + Tailwind) |
| Web served at         | `http://localhost:8081` (nginx in Docker)         |
| API source            | `src/api/pipeline.py` (FastAPI)                  |
| API served at         | `http://localhost:8080` (uvicorn in Docker)       |
| Optimizer (classical) | `src/optimize/classical/tuned.py`                |
| Optimizer (PPO)       | `src/optimize/learned/ppo.py`                    |
| RAG advisory          | `src/rag/advisory.py`                            |
| Corpus documents      | `data/corpus/manufacturing/*.md`                 |
| Scenario configs      | `data/scenarios/*.yaml`                          |
| Generated data        | `data/generated/<scenario>/` (created by `make demo-data`) |
| Benchmark output      | `benchmark/suite-summary.json` (from `make bench-all`) |
| Replay snapshot       | `web/public/demo-replay.json`                    |
| LLM model             | Nemotron-3-Nano-30B-A3B-FP8 (served by vLLM)    |
| Vector DB             | Qdrant at `http://localhost:6333`                |
| Docker Compose        | `docker-compose.yml` (4 services)                |
| Makefile              | `Makefile` (`make demo`, `make test`, etc.)      |
