---
source_id: sop-inventory-policy
source_type: sop
title: S&OP Inventory Policy — Safety Stock, Reorder Point, Order-Up-To
---

# S&OP Inventory Policy (Safety Stock, Reorder Point, Order-Up-To)

**Purpose.** Define how the (s, S)-style inventory policy parameters are set and
tuned so that plans are comparable and reproducible across runs.

## Policy parameters
- **Safety stock** buffers demand and lead-time variability for a service
  target. It scales with the fill-rate target, demand standard deviation, and
  the square root of the lead time.
- **Reorder point (s)** = expected demand over the lead time + safety stock.
- **Order-up-to (S)** = reorder point + a review-period demand allowance.
- **Order batch multiplier** scales order quantities to reflect minimum-order or
  batching constraints.

## Baseline vs tuned classical
- The **naive baseline** uses neutral multipliers (all 1.0). It is the
  legitimate "collapses under non-stationarity" reference, not a straw man.
- The **tuned classical** solver searches the multiplier space (seeded Optuna,
  seed 12345, so results are reproducible run-to-run) and simulates the policy
  period-by-period across the horizon with a lead-time receipt queue. A tuned
  classical solver does **not** collapse and is the current default.
- PPO is a **candidate, not a mandate**; it ships only if on-device evidence
  shows it wins. To date it has not beaten tuned classical and is reported
  honestly when it loses.

## Reproducibility
- Data generation and the tuning search are seeded. Two identical runs must
  produce identical objectives; a plan whose numbers drift run-to-run is a
  defect, not a result.

## Authority of numbers
- Objective, fill rate, days of inventory, and cost breakdown are produced by
  the optimizer benchmark. Any advisory or narrative layer explains these values
  and must never recompute or override them.
