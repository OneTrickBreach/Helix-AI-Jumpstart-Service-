"""Optuna-tuned (s,S) optimizer."""

from __future__ import annotations

from src.ingest.state import ScenarioState
from src.optimize.baseline.policy import optimize_baseline
from src.optimize.common import PolicyParams, build_plan


def _candidate_params() -> list[PolicyParams]:
    return [
        PolicyParams(0.8, 0.9, 0.95),
        PolicyParams(0.9, 1.0, 0.9),
        PolicyParams(1.0, 1.1, 0.85),
        PolicyParams(1.15, 1.0, 0.8),
        PolicyParams(1.25, 1.2, 0.75),
        PolicyParams(1.4, 0.9, 0.7),
    ]


def optimize_classical(state: ScenarioState, forecast: dict, n_trials: int = 12) -> dict:
    baseline = optimize_baseline(state, forecast)
    best_plan = baseline
    best_value = float(baseline["metrics"]["objective"])
    trials: list[dict] = [
        {
            "number": 0,
            "params": baseline["policy"],
            "objective": best_value,
            "source": "baseline_seed",
        }
    ]

    try:
        import optuna

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        def objective(trial: optuna.Trial) -> float:
            params = PolicyParams(
                safety_stock_multiplier=trial.suggest_float("safety_stock_multiplier", 0.7, 1.45),
                order_up_to_multiplier=trial.suggest_float("order_up_to_multiplier", 0.75, 1.3),
                order_batch_multiplier=trial.suggest_float("order_batch_multiplier", 0.65, 1.0),
            )
            plan = build_plan(
                state=state,
                forecast=forecast,
                params=params,
                method="classical_tuned_sS_ortools",
                lane_engine="ortools",
            )
            return float(plan["metrics"]["objective"])

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=max(1, n_trials), show_progress_bar=False)
        params = PolicyParams(**study.best_params)
        plan = build_plan(
            state=state,
            forecast=forecast,
            params=params,
            method="classical_tuned_sS_ortools",
            lane_engine="ortools",
        )
        best_plan = plan if float(plan["metrics"]["objective"]) <= best_value else best_plan
        trials.extend(
            {
                "number": trial.number + 1,
                "params": trial.params,
                "objective": trial.value,
                "source": "optuna",
            }
            for trial in study.trials
            if trial.value is not None
        )
    except Exception as exc:
        for idx, params in enumerate(_candidate_params(), start=1):
            plan = build_plan(
                state=state,
                forecast=forecast,
                params=params,
                method="classical_tuned_sS_ortools",
                lane_engine="ortools",
            )
            value = float(plan["metrics"]["objective"])
            trials.append(
                {
                    "number": idx,
                    "params": {
                        "safety_stock_multiplier": params.safety_stock_multiplier,
                        "order_up_to_multiplier": params.order_up_to_multiplier,
                        "order_batch_multiplier": params.order_batch_multiplier,
                    },
                    "objective": value,
                    "source": f"fallback_grid:{type(exc).__name__}",
                }
            )
            if value <= best_value:
                best_value = value
                best_plan = plan

    best_plan = {**best_plan}
    best_plan["method"] = "classical_tuned_sS_ortools"
    best_plan["tuning"] = {
        "trials": trials,
        "best_objective": float(best_plan["metrics"]["objective"]),
        "baseline_objective": float(baseline["metrics"]["objective"]),
        "matched_or_beat_baseline": float(best_plan["metrics"]["objective"])
        <= float(baseline["metrics"]["objective"]),
    }
    return best_plan
