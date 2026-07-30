# Iteration 3 — Plan of Action (Helix AI Jumpstart SCO Prototype, GB10)

**Prepared for:** Ryan Spurr | Helix, Connection Inc.
**From:** Ishan (AI Intern)
**Authority:** Ryan delegated a full free hand ("proceed unless you have issues"). Scope and technical
calls below are made by Ishan and documented here; Ryan is informed, not gating.
**Predecessor:** Iteration 2 (Points 3 & 4) — built, containerized, verified on-device, merged to `main` 2026-07-10.
**Objective:** move the verified PoC to a **workable, presentable, demo/pilot-ready** state — optimizing
for a credible sell, not research purity.

---

## 0. Read-First: what Iteration 3 is and is NOT

All four whiteboard points are complete. Iteration 1 = Points 1 & 2; Iteration 2 = Points 3 & 4,
including the seeded generator, the naive baseline, the tuned classical solver, and the PPO candidate.
Iteration 3 is therefore **not** "make data / build baseline / add RL" — that shipped. It is
**productization + demo polish + one honest RL fair-shot**.

**Carry-forward guardrails (unchanged, non-negotiable):**
- PPO is *recommended, not mandated*; on-device evidence decides. Iteration 2: PPO lost all four; tuned classical is the default.
- Naive/untuned baseline = the legitimate "collapses under non-stationarity" target. A tuned classical solver does **not** collapse.
- The ~94% paper figure is a baseline-collapse + rescaled-metric artifact; never a flat saving.
- Binding constraint is memory **bandwidth (~273 GB/s)**, not the 128 GB capacity.
- No hospital service-level RL claim. Data stays on-device. Flag prompt-injection, never execute.

*Repo hygiene note: the RL paper in `refs/` is the shareable Singh & Biswas class version (README §15). Resolved.*

---

## 1. Decisions made under delegated authority (proceed; flag only if an issue surfaces)

| Decision | Call | Rationale |
|---|---|---|
| **Iteration 3 scope** | Productization-leaning (demo, real-corpus RAG, polish) + one RL fair-shot | "Workable/presentable" is the goal; research depth serves the demo, not the reverse |
| **PoC vs production** | Stay **PoC → pilot/demo-ready**; not production GA this iteration | GA needs real customer-data onboarding + hardening (see §4); too large for one iteration |
| **RL methods** | Keep, give **one time-boxed fair shot**, then demote-not-delete on evidence | Fully dropping loses the paper grounding + the honest-benchmark selling point; blindly keeping ignores that PPO lost |
| **External framing** | **Evidence-led** (three-tier honest benchmark as the story) | Contradicting on-device results would burn hard-earned credibility |
| **Target metric for RL shot** | Cost **and** CVaR tail risk | A mean win that hides a shock tail is not a resilience win |

---

## 2. EXECUTION PROTOCOL — read this before running any phase (AGENT)

This plan is built to be executed **one phase per session**, not all at once.

- Execute **exactly ONE phase per run.** Do its tasks, hit its Definition of Done, then **STOP.**
- **Do NOT begin the next phase** until Ishan explicitly says go. The starter prompt names the current phase.
- At every STOP checkpoint you MUST, in order:
  1. **Brutal-truth review** — re-examine everything you did this phase against the guardrails and the
     *actual on-device behavior* (not your own build report). Assume something is wrong and go find it;
     fix any real defect before proceeding. This is standing project practice and has repeatedly caught
     real bugs (fake routing, hardcoded tie-breaks, fake progress events).
  2. **Commit** the work with a clear message.
  3. **Add a `DEVELOPMENT_JOURNAL.md` entry** (newest at TOP): what changed, why, verified real results
     (not assumed), the review findings + any fixes, git ref, open follow-ups. Mandatory project practice.
  4. **Report** a short summary to Ishan and wait.
- **Operational gotcha (from the journal):** the `api` container bakes `src/` in via `COPY` — it is not
  bind-mounted. After ANY `src/` change, run `docker compose build api && docker compose up -d --no-deps api` 
  before `make test` / `make run` / `make bench-all`, or you silently test stale code.
- If you hit a guardrail conflict or a real blocker, **stop and report** — do not work around it.
- Phases are dependency-ordered. Do not skip ahead; a later phase assumes earlier ones are green.

---

## 3. Phases

### Phase 0 — Orientation & green baseline *(cheap; no feature code)*
- **Objective:** load context and confirm the repo is in a known-good state before changing anything.
- **Tasks:** read `README.md`, `DEVELOPMENT_JOURNAL.md`, this PoA, and `.devin/rules/helix-sco.md`.
  Bring the stack up and run the existing suite to establish a baseline: `make up` → `make test` 
  (expect 49/49) → `make bench-all`. Record the current four-scenario numbers.
- **DoD:** stack healthy; 49/49 pass; a baseline `suite-summary` captured for later before/after comparison.
- **⏹ STOP / CHECKPOINT:** brutal-truth review (re-check this phase's work against the guardrails and real on-device behavior; assume something is wrong, find it, fix it) → commit → journal (incl. review findings) → report → wait for go.

### Phase 1 — Reproducibility & integrity hardening *(protects every later before/after and the demo)*
- **Objective:** make results deterministic and honestly labeled so a live demo can't contradict itself.
- **Tasks:**
  - **Seed Optuna** in `optimize_classical` — tuned-classical objectives currently drift run-to-run,
    undercutting the "seeded/reproducible" promise and making a live demo look inconsistent.
  - **Per-scenario process-RSS** — the current `peak_process_rss_mb` saturates after scenario 1
    (process-lifetime high-water mark); make it per-scenario or keep the device-level column authoritative and clearly primary.
  - **Triage `npm audit`** findings in the web dependency tree.
- **DoD:** two consecutive `make bench-all` runs produce identical classical objectives; memory reporting
  is per-scenario and unambiguous; audit findings triaged (fixed or documented).
- **⏹ STOP / CHECKPOINT:** brutal-truth review (re-check this phase's work against the guardrails and real on-device behavior; assume something is wrong, find it, fix it) → commit → journal (incl. review findings) → report → wait for go.

### Phase 2 — RAG on a real corpus *(customer-visible value)*
- **Objective:** ground the advisory layer on real documents instead of a synthesized corpus.
- **Tasks:** ingest a small real (or realistic sample) supplier-docs / SOPs / planner-notes set. Keep the
  hard **ADVISORY-ONLY** boundary (LLM explains; never computes/overrides a metric). Keep retrieval-time
  prompt-injection scanning. Add the **Qdrant TTL / cleanup path** for stale `extra-N` points (journal follow-up).
- **DoD:** `/rag/rationale` returns grounded, cited rationale over the real docs; every retrieved chunk is
  injection-scanned; no stale-point accumulation across repeated calls; advisory/metrics boundary intact.
- **⏹ STOP / CHECKPOINT:** brutal-truth review (re-check this phase's work against the guardrails and real on-device behavior; assume something is wrong, find it, fix it) → commit → journal (incl. review findings) → report → wait for go.

### Phase 3 — Demo & narrative layer *(the "presentable" headline; ships on the classical default)*
- **Objective:** a clean, repeatable ~10-minute live demo on the GB10 telling the "rack → desk" story end to end.
- **Tasks:** scripted demo path (pick scenario → run → live SSE progress → before/after cards → on-device
  memory panel → advisory rationale); a one-screen "why this plan" summary; a **recorded fallback run** in
  case of live-GPU flakiness; a short pitch deck aligned to the *real* numbers only.
- **DoD:** demo runs start-to-finish from one command; every on-screen number traces to a real run; a
  non-technical viewer gets the value in the first two minutes.
- **⏹ STOP / CHECKPOINT:** brutal-truth review (re-check this phase's work against the guardrails and real on-device behavior; assume something is wrong, find it, fix it) → commit → journal (incl. review findings) → report → wait for go.

### Phase 4 — RL fair-shot *(time-boxed; demote-not-delete; abandonable without touching the demo)*
- **Objective:** give PPO the fair test it never got, then decide by evidence.
- **Tasks:** rebuild `src/optimize/learned/env.py` as a **true per-period MDP** (per-period state, action,
  lead-time receipt queue, backlog aging) instead of a whole-horizon parameter search. Re-run head-to-head
  on the shock/surge scenarios. Add **CVaR-aware** evaluation for the tail.
- **Outcome handling:** wins a scenario fairly → fold it into the demo (Phase 3) as an addendum. Still
  loses → demote to "evaluated, not shipped," keep visible in the harness; classical stays default.
- **Time-box:** hard cap (~1 week). If it slips, ship without it; the demo is unaffected.
- **DoD:** a fair, documented re-run exists; the keep/demote decision is recorded with real numbers.
- **⏹ STOP / CHECKPOINT:** brutal-truth review (re-check this phase's work against the guardrails and real on-device behavior; assume something is wrong, find it, fix it) → commit → journal (incl. review findings) → report → wait for go.

### Phase 5 — Scale study *("desk → cluster" proof)*
- **Objective:** find the real single-node ceiling; validate the 2-node path only if warranted.
- **Tasks:** push a larger-than-prototype workload to find the real ~121 GiB single-node limit. Validate
  the 2-node 256 GB RoCE/NCCL path **only if** the ceiling is hit and a second unit + 200G DAC are available.
- **DoD:** documented single-node ceiling from real runs; 2-node either validated or explicitly deferred with reason.
- **⏹ STOP / CHECKPOINT:** brutal-truth review (re-check this phase's work against the guardrails and real on-device behavior; assume something is wrong, find it, fix it) → commit → journal (incl. review findings) → report → wait for go.

### Phase 6 — cuOpt re-check *(low effort)*
- **Objective:** confirm whether GPU routing is available yet on this stack.
- **Tasks:** re-check NGC for a current arm64/CUDA-13 cuOpt build. If it runs, benchmark GPU routing vs.
  OR-Tools CPU honestly. If not, keep OR-Tools and record the dated availability check.
- **DoD:** a dated NGC check in the journal; benchmark only if a real build runs.
- **⏹ STOP / CHECKPOINT:** brutal-truth review (re-check this phase's work against the guardrails and real on-device behavior; assume something is wrong, find it, fix it) → commit → journal (incl. review findings) → report → wait for go.

### Phase 7 — Production track *(DEFERRED — now **Iteration 6**; do NOT execute this iteration)*
> **Renumbered 2026-07-30.** Ryan's demo feedback inserted two iterations ahead of this track:
> Iteration 4 (dataset transparency) and Iteration 5 (conversational what-if). The production
> track below is now Iteration 6.

- Real customer-data onboarding/ETL, HA, multi-tenant isolation, security hardening, licensing
  (NFR/NVAIE), shippable appliance image, multi-vertical validation.
- **Listed only** so the boundary is deliberate, not drift. If Ishan reclassifies, this becomes its own plan.

---

## 4. Is Iteration 3 the last iteration? (honest roadmap)

**Short answer: no.** Iteration 3 gets you to *demo-ready / pilot-ready* — a workable, presentable
prototype with a credible sell. It does **not** get you to a *finished, shippable, marketable product*.

| Stage | State | Iteration |
|---|---|---|
| PoC (synthetic data, one vertical, verified on-device) | ✅ Done | Iteration 2 |
| **Pilot/demo-ready** (polished demo, real-corpus RAG, reproducible, RL fairly settled) | 🎯 This plan | **Iteration 3** |
| Dataset transparency layer (read-only "Know Your Data" view) | 🎯 In progress | Iteration 4 |
| Conversational scenario/what-if analyst | 📝 Planned | Iteration 5 |
| Production / GA (real customer-data onboarding, hardening, multi-vertical, licensing, packaging) | ⏳ Not started | Iteration 6 |

**The gap between Iteration 3 and a marketable product** — what a paying customer needs that is out of scope here:
- **Real customer-data onboarding.** The core promise is "customer plugs in *their* data." Today it is
  synthetic-only; real ETL / schema-mapping / validation is a whole workstream (Phase 7 / Iteration 6).
- **Production hardening:** HA, multi-tenant isolation, security, install/update tooling, a shippable appliance image.
- **Multi-vertical:** only Manufacturing is built; Retail / Wholesale / Hospitals remain just the market map.
- **Commercial wrap:** licensing (NFR/NVAIE), pricing, support, SLAs.

**Bottom line:** Iteration 3 makes it *sellable as a story and demoable on the box* — enough to win design
partners or an internal go/no-go. The finished product is the production track (now **Iteration 6**)
beyond that; Iterations 4 and 5 sit in between, sharpening the demo rather than shipping the product.
