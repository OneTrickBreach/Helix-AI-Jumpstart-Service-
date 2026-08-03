"""Statistical demand forecast baseline.

Finished-good customer demand is forecast directly per customer/SKU using
`statsforecast`: AutoETS for smooth-ish series, CrostonSBA for intermittent
/lumpy series (selected per series by the fraction of zero-demand periods).
Component demand is derived later through the BOM so component plans remain
tied to the finished-good demand signal instead of independently forecasting
correlated derived rows.
"""

from __future__ import annotations

import math

import polars as pl
from statsforecast import StatsForecast
from statsforecast.models import AutoETS, CrostonSBA

from src.ingest.state import ScenarioState

LUMPY_ZERO_FRACTION_THRESHOLD = 0.35


def zero_fraction(values: list[float]) -> float:
    """Fraction of periods with no demand. Decides CrostonSBA vs AutoETS per series.

    Public because the dataset overview (`src/dataset/overview.py`) reports the same
    split; sharing this keeps what the view says about forecasting in step with what
    the forecaster actually does.
    """
    if not values:
        return 1.0
    nonzero = sum(1 for value in values if value > 0)
    return 1.0 - (nonzero / len(values))


def forecast_finished_goods(state: ScenarioState, horizon: int = 8) -> dict:
    fg = (
        state.demand.filter(pl.col("demand_type") == "finished_good_customer")
        .group_by(["node_id", "sku_id", "period"])
        .agg(pl.sum("quantity_units").alias("quantity_units"))
        .sort(["node_id", "sku_id", "period"])
    )

    history_by_series: dict[tuple[str, str], list[float]] = {
        (customer_id, sku_id): [float(v) for v in frame.sort("period")["quantity_units"].to_list()]
        for (customer_id, sku_id), frame in fg.group_by(["node_id", "sku_id"], maintain_order=True)
    }
    lumpy_series = {
        key for key, values in history_by_series.items() if zero_fraction(values) >= LUMPY_ZERO_FRACTION_THRESHOLD
    }

    long_df = fg.select(
        (pl.col("node_id") + "::" + pl.col("sku_id")).alias("unique_id"),
        pl.col("period").alias("ds"),
        pl.col("quantity_units").cast(pl.Float64).alias("y"),
    ).to_pandas()

    max_history = max((len(v) for v in history_by_series.values()), default=1)
    season_length = max(2, min(52, max_history // 2))
    sf = StatsForecast(models=[AutoETS(season_length=season_length), CrostonSBA()], freq=1, n_jobs=1)
    forecast_df = sf.forecast(df=long_df, h=horizon).sort_values(["unique_id", "ds"])

    rows: list[dict] = []
    for record in forecast_df.to_dict("records"):
        customer_id, sku_id = record["unique_id"].split("::", 1)
        key = (customer_id, sku_id)
        use_croston = key in lumpy_series
        raw_value = record["CrostonSBA"] if use_croston else record["AutoETS"]
        method = "statsforecast_croston_sba" if use_croston else "statsforecast_auto_ets"
        quantity = max(0.0, float(raw_value))
        history = history_by_series.get(key, [])
        history_mean = sum(history) / len(history) if history else 0.0
        rows.append(
            {
                "customer_id": customer_id,
                "sku_id": sku_id,
                "period": int(record["ds"]),
                "forecast_quantity_units": round(quantity, 6),
                "method": method,
                "history_mean_units": round(history_mean, 6),
            }
        )
    rows.sort(key=lambda row: (row["customer_id"], row["sku_id"], row["period"]))

    forecast_result_df = pl.DataFrame(rows)
    if forecast_result_df.select(pl.col("forecast_quantity_units").is_nan().any()).item():
        raise ValueError("Forecast contains NaN values")

    historical_total = float(
        state.demand.filter(pl.col("demand_type") == "finished_good_customer")
        .select(pl.sum("quantity_units"))
        .item()
    )
    forecast_total = float(forecast_result_df.select(pl.sum("forecast_quantity_units")).item())
    periods = max(state.horizon(), 1)
    historical_per_horizon = historical_total / periods * horizon
    ratio = forecast_total / historical_per_horizon if historical_per_horizon else math.inf

    return {
        "scenario": state.scenario,
        "horizon": horizon,
        "grain": ["customer_id", "sku_id"],
        "component_demand_strategy": "derived_from_finished_good_forecast_via_bom",
        "rows": rows,
        "summary": {
            "series_count": len({(row["customer_id"], row["sku_id"]) for row in rows}),
            "row_count": len(rows),
            "forecast_total_units": round(forecast_total, 6),
            "historical_total_units": round(historical_total, 6),
            "forecast_vs_recent_history_ratio": round(ratio, 6),
        },
    }
