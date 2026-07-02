"""PPO learned candidate for the Phase 3 benchmark."""

from __future__ import annotations

from src.ingest.state import ScenarioState
from src.optimize.common import PolicyParams, build_plan
from src.optimize.learned.env import MultiEchelonInventoryEnv


def optimize_ppo_candidate(
    state: ScenarioState,
    forecast: dict,
    total_timesteps: int = 128,
) -> dict:
    env = MultiEchelonInventoryEnv(state, horizon=min(8, max(1, total_timesteps // 16)))
    training = {"engine": "stable-baselines3", "total_timesteps": total_timesteps, "fallback": False}
    try:
        from stable_baselines3 import PPO

        model = PPO(
            "MlpPolicy",
            env,
            verbose=0,
            n_steps=16,
            batch_size=16,
            learning_rate=0.001,
            gamma=0.95,
            policy_kwargs={"net_arch": [32, 32]},
            # This is a 3-dimensional continuous-action MLP policy on a tiny
            # env - SB3 itself warns against GPU here (CUDA context overhead
            # dominates, latency/memory get worse, not better). CPU is the
            # right-sized choice; save the GPU for the shared LLM/embeddings.
            device="cpu",
        )
        model.learn(total_timesteps=total_timesteps)
        obs, _ = env.reset()
        action, _ = model.predict(obs, deterministic=True)
        action_values = [float(value) for value in action]
    except Exception as exc:
        training = {
            "engine": "deterministic_policy_fallback",
            "total_timesteps": 0,
            "fallback": True,
            "reason": f"{type(exc).__name__}: {exc}",
        }
        action_values = [0.95, 1.0, 0.8]

    params = PolicyParams(
        safety_stock_multiplier=action_values[0],
        order_up_to_multiplier=action_values[1],
        order_batch_multiplier=action_values[2],
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
