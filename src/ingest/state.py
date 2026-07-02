"""Polars-backed loader for Phase 1 generated Manufacturing scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = REPO_ROOT / "data" / "generated"
REQUIRED_TABLES = {
    "nodes": "nodes.csv",
    "skus": "skus.csv",
    "bom": "bom.csv",
    "demand": "demand.csv",
    "production_lines": "production_lines.csv",
    "lanes": "lanes.csv",
    "lane_periods": "lane_periods.csv",
    "service_targets": "service_targets.csv",
    "initial_inventory": "initial_inventory.csv",
}


@dataclass(frozen=True)
class ScenarioState:
    scenario: str
    root: Path
    nodes: pl.DataFrame
    skus: pl.DataFrame
    bom: pl.DataFrame
    demand: pl.DataFrame
    production_lines: pl.DataFrame
    lanes: pl.DataFrame
    lane_periods: pl.DataFrame
    service_targets: pl.DataFrame
    initial_inventory: pl.DataFrame

    def row_counts(self) -> dict[str, int]:
        return {name: getattr(self, name).height for name in REQUIRED_TABLES}

    def finished_goods(self) -> list[str]:
        return (
            self.skus.filter(pl.col("sku_type") == "finished_good")
            .select("sku_id")
            .to_series()
            .to_list()
        )

    def customers(self) -> list[str]:
        return (
            self.nodes.filter(pl.col("node_type") == "customer")
            .select("node_id")
            .to_series()
            .to_list()
        )

    def horizon(self) -> int:
        return int(self.demand.select(pl.max("period")).item())


def _read_csv(path: Path) -> pl.DataFrame:
    return pl.read_csv(path, null_values=[""])


def load_scenario_state(
    scenario: str,
    data_root: Path | str = DEFAULT_DATA_ROOT,
) -> ScenarioState:
    root = Path(data_root) / scenario
    missing = [filename for filename in REQUIRED_TABLES.values() if not (root / filename).exists()]
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise FileNotFoundError(f"Scenario '{scenario}' is missing generated files: {missing_list}")

    tables = {name: _read_csv(root / filename) for name, filename in REQUIRED_TABLES.items()}
    return ScenarioState(scenario=scenario, root=root, **tables)


def summarize_state(state: ScenarioState) -> dict:
    return {
        "scenario": state.scenario,
        "root": str(state.root),
        "row_counts": state.row_counts(),
        "customers": len(state.customers()),
        "finished_goods": len(state.finished_goods()),
        "horizon_periods": state.horizon(),
    }
