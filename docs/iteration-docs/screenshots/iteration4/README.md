# Iteration 4 — dataset view screenshots

Captured 2026-07-30 from the live stack on the GB10 by `make web-check`
(headless Chromium, 1920×1080, real layout — not mockups).

| File | What it shows |
|---|---|
| `dataset-baseline.png` | Level 1 for `baseline`: badge, one-sentence summary, six tiles, network map |
| `dataset-component-shortage-shock.png` | The demo scenario, with the two disrupted supplier lanes marked amber on the map |
| `dataset-demand-surge.png` | Demand-shock scenario (no lane disruption, so no amber lanes) |
| `dataset-stress-large.png` | 42 locations / 152 lanes, with `+N more` overflow blocks and 4 disrupted lanes |
| `dataset-error-state.png` | Unknown scenario in the URL — errors honestly instead of showing other data |

Regenerate any of these with `make web-check` (writes to the gitignored
`web/e2e/shots/`, including full-page and laptop-width variants).
