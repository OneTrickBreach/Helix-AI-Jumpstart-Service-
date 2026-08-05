# Helix AI Jumpstart — Handoff Reference

> **Status:** Iteration 4 (dataset transparency) merged to `main` 2026-08-03. **Iteration 5 (Beta) —
> the conversational analyst — is complete on `feat/iteration5-beta-conversational-analyst`
> (2026-08-05) and awaiting merge.** `make test` → **347 passed + 2 xpassed** (349 total); web
> **62 Vitest**, **26/26** browser checks. Tuned classical still wins all four scenarios, bit-identical.
> 🔴 Ryan has not reviewed Iteration 4 or 5 — the chat surface carries a visible `BETA` chip.

_Last updated: **2026-08-05** (Iteration 5 Phase 6)_

## Quick start

```bash
make up                       # build + start all four arm64 services (GPU on api/llm)
make test                     # full regression suite (349 tests on-device)
make demo                     # generate data, rebuild web, print every demo URL
make bench-all                # all four scenarios → benchmark/suite-summary.{json,md}
make run SCENARIO=baseline    # single scenario end-to-end plan + metrics
make web-test                 # 62 Vitest tests, run from the committed lockfile
make web-check                # 26 headless-Chromium checks against the running stack
```

Open **`http://localhost:8081`** for the planner UI. Pick a scenario and run it. The **Before**
column is the reorder-point/shortest-route baseline; **After** is the approach selected by the
measured objective. Signed deltas are computed from those returned values. The rationale is
**ADVISORY ONLY** and cannot change numeric plans or metrics.

| Surface | URL |
|---|---|
| Planner UI (live) | `http://localhost:8081` |
| Pre-recorded real run (no GPU) | `http://localhost:8081?replay=true` |
| Dataset view — Iteration 4 | `http://localhost:8081?view=dataset&scenario=component-shortage-shock` |
| Dataset view (recorded) | `http://localhost:8081?view=dataset&replay=true` |
| **"Ask the plan" chat — Iteration 5 (BETA)** | `http://localhost:8081?chat=true` |
| Chat, recorded transcript (no GPU) | `http://localhost:8081?replay=true&chat=true` |

For the full demo walkthrough with talk tracks: [`docs/DEMO_GUIDE.md`](DEMO_GUIDE.md) — Option D is
the chat panel.

## Iteration 5 (BETA) — the conversational analyst

```bash
make chat-ask SCENARIO=baseline CHAT_QUESTION="How many distribution centers are there?"
make chat-eval / make chat-eval-template     # 31-question eval set, with / without the real model
make chat-parse   CHAT_QUESTION="..."        # read a sentence into a validated perturbation
make whatif       CHAT_QUESTION="..."        # show the confirm-before-run card (runs nothing)
make whatif-run   CHAT_QUESTION="..."        # run the perturbation on the real optimizer
make redteam / make redteam-template         # 25 red-team cases + 4 controls → 27/27 both modes
make parse-eval / make parse-eval-template   # 35-case parser eval → 35/35 · 32/32 (+3 skipped)
make chat-transcript                         # RE-CAPTURE web/public/demo-chat-transcript.json
```

| Endpoint (authenticated router) | What it does |
|---|---|
| `POST /chat/ask` | Grounded read-only Q&A. Runs no optimizer, mutates nothing. |
| `POST /chat/parse` | Sentence → validated perturbation, clarifying question, or refusal. Executes nothing. |
| `POST /chat/whatif` | `confirmed=false` returns the card; `confirmed=true` runs the real pipeline on an in-memory overlay. |
| `GET /chat/whatif/stream` | Same run with truthful SSE stage events (incl. `cache/hit`). Rate-limit refusals arrive **in-band** as an SSE `error` event, because `EventSource` cannot read a status code. |

**Rate limits** (all env-configurable on the `api` service; a runaway-load guard for a single-user
demo, **not** an anti-abuse control):

| Bucket | Default | Variable |
|---|---|---|
| Questions (`/chat/ask`, `/chat/parse`) | 30 / 60 s | `HELIX_CHAT_MAX_ASKS` |
| Unconfirmed what-if (card only) | 60 / 60 s | `HELIX_CHAT_MAX_LIGHT` |
| Confirmed what-if runs | 10 / 60 s | `HELIX_CHAT_MAX_RUNS` |
| Runs per browser session | 40 | `HELIX_CHAT_MAX_RUNS_PER_SESSION` |
| Window length | 60 s | `HELIX_CHAT_RATE_WINDOW_SECONDS` |

**Measured on-device (2026-08-05):** a grounded model-written answer is **median 7.9 s, range
2.9–24.1 s** over 11 questions (the model narrates at ~48 tokens/s; the data work is milliseconds).
Glossary, refusal and premise-correction answers are **~0.06 s** — no model is called. A what-if is
**0.5–1.4 s** on the three small scenarios (warm to cold), **19.4 s** cold on `stress-large` (its
288-series forecast; the optimizer itself is 0.4 s, and a second what-if on that scenario is 0.8–1.4 s
once the forecast is cached), and **0.0 s** when the identical perturbation is served from cache.

**What it refuses, on purpose:** anything outside the three whitelisted perturbations
(`node_outage`, `lane_disruption`, `demand_multiplier`) — including compound perturbations, BOM
edits, objective changes and the five deferred perturbation types — plus business-outcome
forecasting, hospital/clinical service-level claims, "make the numbers look better", action or secret
requests, and prompt injection in the user's own message. Every refusal states what it *can* do and
contains no numbers.

## Current results (2026-08-05, seed 12345 — bit-identical since Iteration 4 Phase 0)

| Scenario | Baseline obj | Classical obj | Improvement | PPO | Winner |
|---|---:|---:|---:|---|---|
| `baseline` | 88,023 | **81,789** | **−7.1%** | lost (102,805) | classical |
| `component-shortage-shock` | 102,835 | **95,445** | **−7.2%** | lost (113,585) | classical |
| `demand-surge` | 100,735 | **94,165** | **−6.5%** | lost (115,162) | classical |
| `stress-large` | 2,622,335 | **2,521,615** | **−3.8%** | lost (2,867,271) | classical |

**PPO** was given a fair shot (Phase 4: per-period MDP, CVaR-75 tail-risk eval) and **lost all four
on both objective and tail risk**. Status: "evaluated, not shipped." Kept visible in the benchmark
for transparency.

## On-device envelope

| Metric | Value |
|---|---|
| Device peak memory | **73.2–74.1 GiB** of ~121 GiB usable (46.9–47.8 GiB headroom) — `make bench-all`, 2026-08-05T14:46Z |
| 90% envelope flag | Clear at all tested scales (up to 100x / 28,800 series) |
| LLM throughput | ~48 tokens/s (Nemotron 30B FP8, vLLM `v0.26.0` pinned by digest) |
| Scale ceiling | Forecast latency (~25ms/series), not memory |
| Single-node holds | Yes — 2-node path deferred, not needed |

The device figure rose from Iteration 3's 65–68 GiB when `make up` re-pulled the then-unpinned vLLM
base image, **not** because the app grew; the image is now pinned by digest. It is a whole-host
measurement and has been observed swinging 69–76 GiB for unchanged code, so read it as "flag clear,
headroom ample" rather than as a precise regression signal.

## Read the on-device panel honestly

- **API process peak RSS** is one process, not whole-device memory.
- **Allocation-rate proxy** is a start/end RSS delta divided by latency. It is not DRAM bandwidth.
- **Device peak memory** is sampled system-wide unified-memory use from `/proc/meminfo`. Compare
  with ~121 GiB usable, not the nominal 128 GB label.
- **GPU utilization** is unavailable when the GB10 in-container `nvidia-smi` query returns N/A.
  Null is the correct value.
- The ~273 GB/s figure is the known hardware bandwidth limit. The shared FP8 MoE LLM is the
  bandwidth-sensitive component; the suite does not pretend its allocation proxy is a direct
  bandwidth counter.

## Solver status

- **Main optimizer:** OR-Tools GLOP (capacitated transportation LP in `select_ortools_lanes`).
- **cuOpt 26.06.00:** now available for arm64/CUDA-13 (verified 2026-07-27). Solves VRP, not LP —
  different problem class. VRP crossover at ~100 locations; OR-Tools wins at prototype scale (≤152
  lanes). cuOpt not added to requirements — remains optional for future 100+ stop fleet routing.
- **Smoke endpoint:** `/cuopt/health` and `/cuopt/solve` use cuOpt if installed, OR-Tools fallback
  otherwise. Updated for cuOpt 26.x API.

## Operational posture

This is a **development PoC** (confirmed at kickoff). Production licensing, multi-tenant isolation,
HA, deployment automation, fine-tuning, and larger-than-prototype scaling are intentionally out of
scope (see Phase 7 / Iteration 6 — the production track, renumbered 2026-07-30 when Iterations 4
(dataset transparency) and 5 (conversational what-if) were inserted ahead of it).

All data stays on the device. The LLM rationale is advisory only — it explains the plan; it never
computes or overrides a metric. Prompt injection in ingested text is flagged (including at retrieval
time), never executed. The same boundary governs the Iteration 5 chat surface: the model parses and
narrates, the deterministic pipeline computes, and a numeric validator enforces it.

## Known limits carried forward (state these; do not quietly fix them)

- 🔴 **Lane capacity reaches the optimizer at exactly one period** — `state.horizon()` =
  `max(demand.period)` = 52 (104 on `stress-large`). A capacity perturbation whose window excludes it
  is a measured no-op, and the chat layer reports it as one *with the mechanism*. Whether the
  optimizer should read capacity across the whole horizon is an open question for the sponsor;
  changing it would move every recorded objective.
- **The what-if caches are process-local and not thread-safe** (the rate limiter *is* lock-protected).
  Worst case is a lost cache entry, never corruption — every result is recomputed from immutable
  inputs. Production track.
- **The rate limiter trusts the proxy headers our own nginx sets.** A caller holding the API key and
  talking directly to `:8080` could forge them. Runaway-load guard for a single-user demo; real
  per-tenant quotas are Iteration 6.
- **The refusal patterns are patterns.** A paraphrase nobody wrote down reaches the grounded path,
  where the numeric validator is the next line of defence — which is how the real model stating an
  invented "50,000" was caught.
- **`make test` cannot refresh the demo's benchmark artifacts** and must not be made to: it writes to
  `HELIX_BENCHMARK_DIR` (a temp dir) via a session-scoped fixture, because it used to clobber the
  recorded run the UI and the chat layer quote. Refresh with `make bench-all`.
- **A talk-track rehearsal by a human has never happened.** Every number in the demo guide is
  machine-checked against a live payload or a committed artifact, but nobody has read the script out
  loud end to end.

## Key documents

- [`DEMO_GUIDE.md`](DEMO_GUIDE.md) — full demo walkthrough with talk tracks (Options A–D)
- [`DEVELOPMENT_JOURNAL.md`](DEVELOPMENT_JOURNAL.md) — chronological truth ledger
- [`iteration-docs/AI_Jumpstart_MVP_Iteration5_handoff.md`](iteration-docs/AI_Jumpstart_MVP_Iteration5_handoff.md) — **Iteration 5 (Beta) handoff — current**
- [`iteration-docs/AI_Jumpstart_MVP_Iteration4_handoff.md`](iteration-docs/AI_Jumpstart_MVP_Iteration4_handoff.md) — Iteration 4 handoff
- [`iteration-docs/AI_Jumpstart_MVP_Iteration3_handoff.md`](iteration-docs/AI_Jumpstart_MVP_Iteration3_handoff.md) — Iteration 3 handoff
- [`Iteration5_Plan_of_Action.md`](Iteration5_Plan_of_Action.md) — the current phase-by-phase blueprint
- [`Iteration3_Plan_of_Action.md`](Iteration3_Plan_of_Action.md) §4 — the honest prototype→product gap
- [`containerization.md`](containerization.md) — arm64 four-service stack details
- [`environment.md`](environment.md) — live GB10 device specs
