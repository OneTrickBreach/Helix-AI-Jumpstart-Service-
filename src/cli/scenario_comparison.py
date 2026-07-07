"""Planner-facing CLI over the secure scenario-comparison API."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import httpx


API_BASE_ENV = "HELIX_API_BASE_URL"
API_KEY_ENV = "HELIX_API_KEY"
DEFAULT_API_BASE = "http://localhost:8080"
COST_METRICS = ("total_cost", "holding", "ordering", "transport", "backorder", "lost_sale")


def _client() -> httpx.Client:
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        raise SystemExit(f"{API_KEY_ENV} is required")
    return httpx.Client(
        base_url=os.environ.get(API_BASE_ENV, DEFAULT_API_BASE),
        timeout=600.0,
        headers={"X-API-Key": api_key},
    )


def _unwrap(response: httpx.Response) -> dict[str, Any]:
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "ok":
        raise RuntimeError(f"Unexpected API response: {payload}")
    return payload["data"]


def list_scenarios() -> int:
    with _client() as client:
        data = _unwrap(client.get("/scenarios"))
    print("Available scenarios")
    for item in data["scenarios"]:
        marker = "generated" if item.get("generated") else "config-only"
        description = item.get("description") or "No description provided"
        print(f"- {item['scenario']} ({marker})")
        print(f"  {description}")
    return 0


def _metric_delta(before: float, after: float, metric: str) -> tuple[str, str]:
    if metric == "fill_rate":
        delta = (after - before) * 100.0
        arrow = "up" if delta >= 0 else "down"
        good = delta >= 0
        return f"{arrow} {delta:+.2f} pts", "good" if good else "bad"
    if before == 0:
        return "n/a", "neutral"
    delta = (after - before) / before
    lower_is_better = metric in COST_METRICS or metric == "days_of_inventory"
    arrow = "up" if delta >= 0 else "down"
    good = delta <= 0 if lower_is_better else delta >= 0
    return f"{arrow} {delta:+.2%}", "good" if good else "bad"


def _fmt_money(value: float) -> str:
    return f"${value:,.2f}"


def _fmt_metric(metric: str, value: float) -> str:
    if metric == "fill_rate":
        return f"{value * 100:.2f}%"
    if metric in COST_METRICS:
        return _fmt_money(value)
    return f"{value:,.2f}"


def _row(name: str, before: float, after: float, metric: str) -> str:
    delta, direction = _metric_delta(before, after, metric)
    return f"{name:<22} { _fmt_metric(metric, before):>14} { _fmt_metric(metric, after):>14} {delta:>15} {direction:>8}"


def _print_before_after(benchmark: dict[str, Any]) -> None:
    winner = benchmark["winner"]["approach"]
    baseline_metrics = benchmark["plans"]["baseline"]["metrics"]
    after_metrics = benchmark["plans"][winner]["metrics"]
    baseline_cost = baseline_metrics.get("cost_breakdown", {})
    after_cost = after_metrics.get("cost_breakdown", {})

    print(f"\nScenario: {benchmark['scenario']}")
    if winner == "baseline":
        print("Winner: baseline already best; no improvement found by evidence.")
    else:
        print(f"Winner: {winner} by evidence")
    print(f"PPO outcome: {benchmark.get('ppo_outcome', 'unknown')}")

    print("\nBefore / After")
    print(f"{'Metric':<22} {'Before':>14} {'After':>14} {'Delta':>15} {'Signal':>8}")
    print("-" * 78)
    print(_row("Total cost", baseline_metrics["total_cost"], after_metrics["total_cost"], "total_cost"))
    for key in ["holding", "ordering", "transport", "backorder", "lost_sale"]:
        print(_row(key.replace("_", " ").title(), baseline_cost.get(key, 0.0), after_cost.get(key, 0.0), key))
    print(_row("Fill rate", baseline_metrics["fill_rate"], after_metrics["fill_rate"], "fill_rate"))
    print(_row("Days inventory", baseline_metrics["days_of_inventory"], after_metrics["days_of_inventory"], "days_of_inventory"))


def _print_approaches(benchmark: dict[str, Any]) -> None:
    print("\nApproaches")
    print(f"{'Approach':<12} {'Objective':>12} {'Total Cost':>14} {'Fill':>9} {'Days Inv':>10} {'Latency':>10}")
    print("-" * 74)
    winner = benchmark["winner"]["approach"]
    for row in benchmark["comparison"]:
        marker = "*" if row["approach"] == winner else " "
        print(
            f"{marker}{row['approach']:<11} "
            f"{row['objective']:>12,.2f} "
            f"{_fmt_money(row['total_cost']):>14} "
            f"{row['fill_rate'] * 100:>8.2f}% "
            f"{row['days_of_inventory']:>10.2f} "
            f"{row['latency_seconds']:>9.3f}s"
        )


def _print_resources(benchmark: dict[str, Any]) -> None:
    winner = benchmark["winner"]["approach"]
    profile = benchmark["resource_profiles"][winner]
    print("\nOn-device resource profile")
    print(f"- Peak unified memory: {_number(profile.get('peak_unified_memory_mb')):,.2f} MB")
    print(f"- Effective bandwidth: {_number(profile.get('effective_memory_bandwidth_gbps')):,.2f} GB/s")
    print(f"- Solve latency: {_number(profile.get('wall_clock_seconds')):,.3f}s")
    print(f"- GPU utilization: {_number(profile.get('gpu_utilization_percent')):,.2f}%")
    print(f"- CPU utilization: {_number(profile.get('cpu_utilization_percent')):,.2f}%")


def _print_rationale(rationale: dict[str, Any]) -> None:
    print("\nADVISORY ONLY")
    flags = rationale.get("prompt_injection_flags") or []
    if flags:
        print("Prompt-injection flags surfaced:")
        for flag in flags:
            print(f"- {flag.get('title')} [{flag.get('pattern')}]")
    print(rationale.get("advisory_rationale", "No advisory rationale returned."))
    citations = rationale.get("citations") or []
    if citations:
        print("\nCitations")
        for citation in citations:
            flagged = " flagged" if citation.get("prompt_injection_flagged") else ""
            print(f"- {citation.get('citation_id')}: {citation.get('title')} ({citation.get('source_type')}){flagged}")


def _number(value: Any) -> float:
    return float(value) if value is not None else 0.0


def run_scenario(args: argparse.Namespace) -> int:
    body = {
        "scenario": args.scenario,
        "horizon": args.horizon,
        "ppo_timesteps": args.ppo_timesteps,
        "top_k": args.top_k,
    }
    with _client() as client:
        data = _unwrap(client.post("/scenario-comparison", json=body))
    benchmark = data["benchmark"]
    rationale = data["rationale"]
    _print_before_after(benchmark)
    _print_approaches(benchmark)
    _print_resources(benchmark)
    _print_rationale(rationale)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List API-discovered scenarios")
    run = sub.add_parser("run", help="Run a scenario comparison through the API")
    run.add_argument("--scenario", required=True)
    run.add_argument("--horizon", type=int, default=8)
    run.add_argument("--ppo-timesteps", type=int, default=128)
    run.add_argument("--top-k", type=int, default=5)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "list":
            return list_scenarios()
        if args.command == "run":
            return run_scenario(args)
    except httpx.HTTPStatusError as exc:
        print(f"API request failed: {exc.response.status_code} {exc.response.text}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
