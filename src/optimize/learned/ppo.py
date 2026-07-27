"""PPO learned candidate for the Phase 3 benchmark.

Phase 4 rebuild: the env is now a true per-period MDP.  The agent observes
inventory state each period and outputs adaptive (s,S) multipliers.  After
training, a single deterministic episode produces the plan.
"""

from __future__ import annotations

from src.ingest.state import ScenarioState
from src.optimize.common import PolicyParams, build_plan
from src.optimize.learned.env import MultiEchelonInventoryEnv


def optimize_ppo_candidate(
    state: ScenarioState,
    forecast: dict,
    total_timesteps: int = 128,
) -> dict:
    horizon = min(8, max(1, total_timesteps // 16))
    env = MultiEchelonInventoryEnv(state, horizon=horizon)
    training: dict = {
        "engine": "stable-baselines3",
        "total_timesteps": total_timesteps,
        "mdp": "per_period",
        "fallback": False,
    }

    try:
        from stable_baselines3 import PPO

        model = PPO(
            "MlpPolicy",
            env,
            verbose=0,
            n_steps=horizon,
            batch_size=min(horizon, 8),
            n_epochs=10,
            learning_rate=3e-4,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,
            policy_kwargs={"net_arch": [64, 64]},
            device="cpu",
        )
        model.learn(total_timesteps=total_timesteps)

        obs, _ = env.reset()
        for _ in range(horizon):
            action, _ = model.predict(obs, deterministic=True)
            obs, _reward, terminated, _truncated, _info = env.step(action)
            if terminated:
                break

        plan = env.extract_plan()

    except Exception as exc:
        training = {
            "engine": "deterministic_policy_fallback",
            "total_timesteps": 0,
            "mdp": "per_period",
            "fallback": True,
            "reason": f"{type(exc).__name__}: {exc}",
        }
        params = PolicyParams(
            safety_stock_multiplier=0.95,
            order_up_to_multiplier=1.0,
            order_batch_multiplier=0.8,
        )
        plan = build_plan(
            state=state,
            forecast=forecast,
            params=params,
            method="ppo_candidate",
            lane_engine="ortools",
        )

    plan["training"] = training
    return plan
