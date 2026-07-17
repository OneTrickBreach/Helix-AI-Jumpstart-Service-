---
source_id: planner-field-notes
source_type: planner_note
title: Planner Field Notes — Manufacturing SCO
---

# Planner Field Notes (Manufacturing SCO)

Working notes from planners operating the manufacturing supply chain. These are
observations and rules of thumb, not authoritative metrics.

- When a component goes on allocation, the first instinct to "order more" is
  usually wrong. Fair-share fill means the extra order just gets cancelled later
  and we eat holding and cancellation cost. Trim order-up-to instead.
- The naive baseline looks fine in a calm month and quietly falls apart the
  moment lead times or demand move. That is exactly why we keep a tuned solver
  and a shock scenario in the benchmark.
- Watch the difference between "we lost the sale because we had no stock in the
  right place" (fixable by policy) and "we lost the sale because the supplier
  had nothing to ship" (not fixable by policy). Reporting them as one number
  misleads the S&OP review.
- Splitting inbound flow across two lanes is usually cheaper than paying expedite
  on the single cheapest lane once it saturates. Let the LP allocate it.
- On a demand surge, raise safety stock *before* the peak, and only for items
  the upstream supply can actually support. Buffering an item whose component is
  constrained just moves the bottleneck.
- Trust the benchmark objective for the decision; use the written rationale to
  explain it to the business, not to change it.
