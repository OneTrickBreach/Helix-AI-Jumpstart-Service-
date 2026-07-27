---
source_id: demand-surge-playbook
source_type: playbook
title: Demand Surge Response Playbook
---

# Demand Surge Response Playbook

**Trigger.** Forecast or actual customer demand for one or more finished goods
rises sharply above the planning baseline (promotion, seasonal spike, competitor
stockout).

## Assessment
1. Confirm the surge is demand-side, not a data artifact, before re-planning.
2. Check whether upstream component supply and inbound lane capacity can support
   the higher finished-good build rate. A demand surge is only actionable if
   supply can follow it.
3. Identify the service-tier exposure: which surging items carry the highest
   fill-rate targets and penalties for missing them.

## Response levers
- **Raise safety stock and order-up-to levels** for surging items ahead of the
  demand, sized to the higher mean and variance of demand over the lead time.
- **Pull forward replenishment** within committed lane capacity; split flow
  across lanes when the cheapest lane saturates.
- **Protect high-tier items first** when capacity is contended.

## Cost and risk trade-off
- Higher safety stock reduces lost-sale and backorder cost but raises holding
  cost; the optimizer balances these in the objective. The right level is the
  one that minimizes total objective for the observed demand, not the maximum
  possible stock.
- A mean-cost improvement that hides a worse shock tail is not a resilience win.
  Where tail risk matters, review CVaR alongside mean cost.

## Reporting
- The plan's numeric outcome (objective, fill rate, days of inventory) comes
  from the optimizer benchmark. Advisory narrative explains the drivers; it does
  not compute the numbers.
