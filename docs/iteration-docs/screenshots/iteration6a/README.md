# Iteration 6a — custom scenario panel screenshots

Captured from the live stack on the GB10 (headless Chromium, 1920×1080, real layout — not mockups).
Committed on **2026-08-21** during Iteration 6b Phase 0: Iterations 4 and 5 each have a screenshot
set, 6a had none, and these outlive the internship (ends 2026-08-28).

| File | What it shows |
|---|---|
| `custom-scenario-result.png` | A custom scenario after **Save & run** — the **CUSTOM SCENARIO · NOT A RECORDED BENCHMARK RESULT** banner, the same results screen the four recorded scenarios use, and PPO/Rag greyed out with `PPO outcome: not_evaluated` |
| `custom-scenario-noop-warning.png` | 🔴 **The honesty beat.** The amber *"This disruption will not change the answer"* block, shown **before** the run — *"the optimizer reads lane capacity at period 52 only, and this disruption runs from period 18 to 27 … Do not read an unchanged result as resilience."* Also shows **WHAT YOU CHANGED (1)** and the run estimate with its per-step basis lines |
| `custom-delete-and-run-options.png` | The **"A custom run will include:"** row with its two opt-ins — PPO candidate (+~2.7 s) and Written rationale (+~20 s) — which is what keeps the header's PPO-timesteps and Top-K controls honest |
| `custom-delete-button.png` | The **Delete** button beside the dropdown, on the scenario you are actually looking at. This one exists because a reviewer with a custom scenario selected reported seeing no delete affordance at all |
| `custom-from-dataset-view.png` | The panel opened **from the dataset view** — beside it, never over it, so Ryan's network map stays on screen |
| `custom-scenario-dataset-view.png` | A saved custom scenario rendered by the Iteration 4 dataset view, including *"What makes this scenario different"*. **No dataset code was changed to make this work** |

## 🔴 How to regenerate — read this before trusting a re-run

Unlike the Iteration 4 set, **these are not all reproducible from `make web-check`.** Verified by
timestamp on 2026-08-21: a full `make web-check` run (38/38 PASS) rewrote **two** of these six and left
the other four untouched.

| Reproducible by `make web-check` | One-off captures from the 6a Phase 4 review |
|---|---|
| `custom-scenario-result.png` | `custom-delete-and-run-options.png` |
| `custom-scenario-noop-warning.png` | `custom-delete-button.png` |
| | `custom-from-dataset-view.png` |
| | `custom-scenario-dataset-view.png` |

The four on the right were taken with ad-hoc scripts during the 6a Phase 4 browser review (the pass
that found four defects only a browser could find). The committed
[`web/e2e/dataset-view.check.mjs`](../../../../web/e2e/dataset-view.check.mjs) writes only the two on the
left — it *checks* the states the other four show, but does not screenshot them.

So: `make web-check` refreshes two of these six. Recreating the other four means re-driving those
states by hand, or extending the check script to screenshot them. **Extending the script is the better
fix and is not done** — noted here rather than left as a false "just re-run `make web-check`"
instruction, which is what the Iteration 4 README would have implied.

`make web-check` writes to the gitignored `web/e2e/shots/`; these are copies.

---

*Iteration 6b, Phase 0. Predecessor: Iteration 6a, merged to `main` as `ad17cc5`.
Talk track: [`../../../DEMO_GUIDE.md`](../../../DEMO_GUIDE.md) Option E.*
