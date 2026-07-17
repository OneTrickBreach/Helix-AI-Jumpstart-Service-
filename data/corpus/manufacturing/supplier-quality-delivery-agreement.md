---
source_id: supplier-quality-delivery-agreement
source_type: supplier_doc
title: Supplier Quality & Delivery Agreement — Tier-1 Components
---

# Supplier Quality & Delivery Agreement (Tier-1 Components)

**Scope.** This agreement governs inbound raw and sub-assembly components
supplied to the plant from Tier-1 suppliers. It sets the delivery,
lead-time, and capacity commitments that planning treats as the ground truth
when sizing safety stock and reorder points.

## Lead time and delivery commitments
- Standard replenishment lead time for cataloged components is **14–21 days**
  from purchase-order acknowledgement to dock receipt.
- Suppliers must acknowledge orders within **2 business days**. Unacknowledged
  orders are not counted as in-transit inventory for planning purposes.
- During a declared allocation or shortage event, suppliers may extend lead
  time and impose per-period allocation caps. Planning must assume the
  **effective capacity for that lane can drop to zero** for the duration of the
  event and cannot be recovered by reordering alone.

## Capacity and allocation
- Each inbound lane has a committed capacity per period. Orders above the
  committed capacity are best-effort and must not be assumed fillable.
- When a component is on allocation, the supplier fills against a fair-share
  percentage of historical consumption, not against the current order size.
  Over-ordering does **not** increase the allocated quantity and inflates
  cancellation and holding cost.

## Quality and returns
- Incoming lots are subject to sampling inspection; rejected lots do not count
  toward fill and are re-ordered at standard lead time.
- Expedite (air/premium) freight is available for critical components at a
  significant per-unit cost premium and should be reserved for genuine
  service-risk situations, not routine replenishment.

## Planning implications
- Treat committed capacity and lead time as constraints, not targets.
- Under a component-shortage shock, the binding limitation is **supply
  availability**, not inventory policy; lost sales caused by zero supply cannot
  be recovered by ordering more.
