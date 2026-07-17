---
source_id: inbound-logistics-sop
source_type: sop
title: Inbound Logistics & Lane Selection SOP
---

# Inbound Logistics & Lane Selection SOP

**Purpose.** Standardize how planners choose inbound and inter-facility lanes so
that routing decisions are auditable and cost-minimizing under capacity limits.

## Lane selection principles
1. Prefer the **lowest landed-cost lane** (unit cost + distance × per-km cost)
   that has sufficient effective capacity for the required period flow.
2. When the cheapest lane cannot carry the full required flow, **split the flow
   across lanes** by a capacitated min-cost allocation rather than forcing the
   entire volume onto one lane. Committing 100% of volume to a single lane that
   cannot carry it produces an infeasible plan and hidden expedite cost.
3. Never assume a lane whose effective capacity has dropped to zero (shock or
   maintenance) can move volume in that period.

## Lead-time handling
- Use the effective (period-adjusted) lead time, not the catalog lead time,
  whenever a period override is present.
- Longer effective lead time increases the required safety stock for the same
  service target; document the assumption when it changes.

## Cost accounting
- Transport cost is charged on ordered units moved and must be included in the
  plan objective alongside holding, ordering, backorder, and lost-sale cost.
- Expedite freight is an exception path, logged and reviewed, not a default.

## Solver note
- The classical routing path solves a small transportation LP per lane type
  (OR-Tools) to allocate required flow across candidate lanes under their
  capacities. This is the auditable default. GPU routing (cuOpt) is not
  available on the current arm64/CUDA stack; the CPU LP is the honest fallback.
