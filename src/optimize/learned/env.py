"""Small Gym-compatible multi-echelon inventory environment."""

from __future__ import annotations

import numpy as np

try:
    import gymnasium as gym
    from gymnasium import spaces
except Exception:  # pragma: no cover - exercised only when gymnasium is absent.
    gym = None
    spaces = None

from src.forecast.statistical import forecast_finished_goods
from src.ingest.state import ScenarioState
from src.optimize.common import PolicyParams, build_plan


class MultiEchelonInventoryEnv(gym.Env if gym else object):
    metadata = {"render_modes": []}

    def __init__(self, state: ScenarioState, horizon: int = 8):
        self.state = state
        self.horizon = horizon
        self.forecast = forecast_finished_goods(state, horizon=horizon)
        self.series = sorted({(row["customer_id"], row["sku_id"]) for row in self.forecast["rows"]})
        self.step_index = 0
        self.last_objective = 0.0
        n = max(1, len(self.series))
        if spaces:
            self.observation_space = spaces.Box(low=0.0, high=1e6, shape=(n * 3,), dtype=np.float32)
            self.action_space = spaces.Box(low=0.65, high=1.45, shape=(3,), dtype=np.float32)

    def _obs(self) -> np.ndarray:
        rows_by_series = {}
        for row in self.forecast["rows"]:
            rows_by_series.setdefault((row["customer_id"], row["sku_id"]), []).append(
                float(row["forecast_quantity_units"])
            )
        obs = []
        for key in self.series:
            values = rows_by_series[key]
            mean = sum(values) / len(values) if values else 0.0
            spread = max(values) - min(values) if values else 0.0
            obs.extend([mean, spread, float(self.step_index)])
        return np.asarray(obs, dtype=np.float32)

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        if seed is not None and gym:
            super().reset(seed=seed)
        self.step_index = 0
        self.last_objective = 0.0
        return self._obs(), {}

    def step(self, action):
        action = np.asarray(action, dtype=np.float32).reshape(-1)
        if action.size < 3:
            action = np.pad(action, (0, 3 - action.size), constant_values=1.0)
        params = PolicyParams(
            safety_stock_multiplier=float(np.clip(action[0], 0.65, 1.45)),
            order_up_to_multiplier=float(np.clip(action[1], 0.65, 1.45)),
            order_batch_multiplier=float(np.clip(action[2], 0.65, 1.45)),
        )
        plan = build_plan(
            state=self.state,
            forecast=self.forecast,
            params=params,
            method="ppo_candidate",
            lane_engine="ortools",
        )
        self.last_objective = float(plan["metrics"]["objective"])
        self.step_index += 1
        terminated = self.step_index >= self.horizon
        reward = -self.last_objective
        return self._obs(), float(reward), terminated, False, {"plan": plan}
