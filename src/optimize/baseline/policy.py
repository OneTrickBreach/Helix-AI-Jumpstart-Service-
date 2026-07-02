"""Deterministic reorder-point baseline with greedy lane selection."""

from __future__ import annotations

from src.ingest.state import ScenarioState
from src.optimize.common import PolicyParams, build_plan


def optimize_baseline(state: ScenarioState, forecast: dict) -> dict:
    return build_plan(
        state=state,
        forecast=forecast,
        params=PolicyParams(
            safety_stock_multiplier=1.0,
            order_up_to_multiplier=1.0,
            order_batch_multiplier=1.0,
        ),
        method="baseline_sS_greedy",
        lane_engine="greedy",
    )
