# Iteration 6b — custom dataset (the network tier) screenshots

Captured from the live stack on the GB10 on **2026-08-24** by `make web-check`
(headless Chromium, 1920×1080, real layout — not mockups).

| File | What it shows |
|---|---|
| `network-group.png` | **The Network group as a planner first meets it.** The positional-ID caveat, then the two honesty classes rendered distinctly: 3 node counts under *"…the optimizer has no per-node capacity — so this is NOT a resilience test"*, and 4 problem-size counts under *"…never against the recorded baseline"*. Bounds shown as hints under each field |
| `network-zero-dc-refusal.png` | 🔴 **The demo beat.** Typing `0` into Distribution centers is *not clamped* — it reaches the measured refusal quoting **68,565.25 at 92.01% fill**, ending *"That is a limit of the model, not a fact about your network."* **Save & run is disabled** while it stands |
| `network-group-result.png` | Ryan's own sentence delivered: warehouses `2 → 1`, saved and run in the panel, **81,663** on the results screen with the CUSTOM SCENARIO banner and **no** not-comparable caveat — because a node count *is* comparable |
| `network-resized-not-comparable.png` | 🔴 The other half of guardrail 4: 7 customers scores **66,548**, and the amber **"Not comparable to the recorded baseline"** block sits directly above the numbers, naming 81,789.36. The within-run naive-vs-classical tiles (−4.4%) are below it, which is the comparison that *is* valid |
| `network-onedc-dataset-view.png` | A 1-DC dataset on the Iteration 4 dataset view. **No dataset code was changed** — `NetworkMap` redraws on its own (17 nodes → 16) and the summary reads *"through **1** distribution center"* |

## Regenerating

🔴 **All five are written by `make web-check`** and every one is asserted, not just
captured — the run fails if the refusal stops quoting its measured figures, if the
caveat stops naming 81,789.36, or if the inert count ever appears as a live control.

This is deliberately unlike the [Iteration 6a set](../iteration6a/README.md), where
only 2 of 6 regenerate and the other 4 were one-off captures. Extending the check
script was the better fix and it was done here.

`make web-check` writes to the gitignored `web/e2e/shots/`; these are copies.

---

*Iteration 6b, Phase 4. Talk track: [`../../../DEMO_GUIDE.md`](../../../DEMO_GUIDE.md) Option E.
Finding: [`../../Modelling_Finding_The_Optimizer_Has_No_Node.md`](../../Modelling_Finding_The_Optimizer_Has_No_Node.md).*
