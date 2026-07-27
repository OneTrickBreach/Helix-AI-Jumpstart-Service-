---
source_id: component-shortage-playbook
source_type: playbook
title: Component Shortage Response Playbook
---

# Component Shortage Response Playbook

**Trigger.** A supplier declares allocation, a lane's effective capacity drops
toward zero, or inbound receipts fall materially below the plan for a critical
component.

## Immediate assessment
1. Identify which finished goods depend on the constrained component via the BOM.
2. Classify the constraint: is the limit **supply availability** (nothing to
   order) or **inventory policy** (stock on hand mis-positioned)? These require
   different responses and should be stated plainly to planners.
3. Quantify unavoidable lost sales: demand that cannot be met because supply,
   not policy, is gating. Do not present recoverable and unrecoverable shortfall
   as the same number.

## Response levers (in priority order)
- **Reallocate existing inventory** to the highest service-tier / highest-margin
  finished goods before ordering more.
- **Lower order-up-to and batch multipliers** for the constrained component so
  the plan does not accumulate ordering and holding cost for units the supplier
  cannot deliver during the allocation window.
- **Qualify alternate lanes or substitute components** only where the BOM and
  quality agreement allow.
- **Reserve expedite freight** for genuine service-risk finished goods, not for
  routine replenishment.

## What not to do
- Do not over-order a component on allocation: fair-share fill is based on
  historical consumption, so a larger order does not increase delivered units
  and inflates cancellation, holding, and expedite cost.
- Do not claim an inventory-policy change "recovered" sales that were lost to
  zero supply. Under a genuine zero-supply shock the tuned policy may only be
  able to reduce cost, not restore fill.

## Reporting
- Report the benchmark-selected plan's objective, fill rate, and days of
  inventory as computed by the optimizer. Narrative rationale is advisory and
  must not restate or override those numbers.
