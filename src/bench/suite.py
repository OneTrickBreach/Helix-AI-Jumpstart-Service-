"""Phase 6 all-scenario benchmark suite with honest device-memory sampling."""

from __future__ import annotations

import argparse
import json
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from src.bench.profiler import BENCHMARK_DIR
from src.pipeline.bench import run_head_to_head
from src.rag.advisory import generate_advisory_rationale


SCENARIOS = (
    "baseline",
    "component-shortage-shock",
    "demand-surge",
    "stress-large",
)
USABLE_ENVELOPE_GIB = 121.0
ENVELOPE_FLAG_FRACTION = 0.90
DEVICE_MEMORY_METHOD = (
    "/proc/meminfo MemTotal-MemAvailable sampled inside the api container; "
    "on this GB10 the container observes the host unified CPU/GPU memory pool"
)


def _read_device_memory_bytes() -> tuple[int, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, raw = line.split(":", maxsplit=1)
        if key in {"MemTotal", "MemAvailable"}:
            values[key] = int(raw.strip().split()[0]) * 1024
    if set(values) != {"MemTotal", "MemAvailable"}:
        raise RuntimeError("MemTotal/MemAvailable unavailable in /proc/meminfo")
    return values["MemTotal"], values["MemTotal"] - values["MemAvailable"]


@contextmanager
def sample_device_memory(interval_seconds: float = 0.25) -> Iterator[dict[str, Any]]:
    """Continuously sample system-wide unified-memory use during a scenario."""
    result: dict[str, Any] = {
        "method": DEVICE_MEMORY_METHOD,
        "sample_interval_seconds": interval_seconds,
        "sample_count": 0,
        "total_bytes_observed": None,
        "peak_used_bytes": None,
        "error": None,
    }
    stop = threading.Event()

    def sample_once() -> None:
        try:
            total, used = _read_device_memory_bytes()
            result["total_bytes_observed"] = total
            current_peak = result["peak_used_bytes"]
            result["peak_used_bytes"] = used if current_peak is None else max(current_peak, used)
            result["sample_count"] += 1
        except Exception as exc:  # noqa: BLE001 - preserve measurement failure in output
            result["error"] = f"{type(exc).__name__}: {exc}"

    def worker() -> None:
        while not stop.wait(interval_seconds):
            sample_once()

    sample_once()
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        yield result
    finally:
        stop.set()
        thread.join(timeout=max(1.0, interval_seconds * 2))
        sample_once()


def envelope_assessment(
    peak_used_bytes: int | None,
    usable_envelope_gib: float = USABLE_ENVELOPE_GIB,
    flag_fraction: float = ENVELOPE_FLAG_FRACTION,
) -> dict[str, Any]:
    envelope_bytes = usable_envelope_gib * (1024**3)
    if peak_used_bytes is None:
        return {
            "usable_envelope_gib": usable_envelope_gib,
            "flag_threshold_fraction": flag_fraction,
            "flag_threshold_gib": usable_envelope_gib * flag_fraction,
            "peak_used_gib": None,
            "headroom_gib": None,
            "fraction_of_envelope": None,
            "approaches_envelope": None,
        }
    fraction = peak_used_bytes / envelope_bytes
    return {
        "usable_envelope_gib": usable_envelope_gib,
        "flag_threshold_fraction": flag_fraction,
        "flag_threshold_gib": round(usable_envelope_gib * flag_fraction, 3),
        "peak_used_gib": round(peak_used_bytes / (1024**3), 3),
        "headroom_gib": round((envelope_bytes - peak_used_bytes) / (1024**3), 3),
        "fraction_of_envelope": round(fraction, 6),
        "approaches_envelope": fraction >= flag_fraction,
    }


def summarize_scenario(
    benchmark: dict[str, Any],
    rationale: dict[str, Any],
    device_memory: dict[str, Any],
) -> dict[str, Any]:
    assessment = envelope_assessment(device_memory.get("peak_used_bytes"))
    winner = str(benchmark["winner"]["approach"])
    rows: list[dict[str, Any]] = []
    for comparison in benchmark["comparison"]:
        approach = str(comparison["approach"])
        profile = benchmark["resource_profiles"][approach]
        rows.append(
            {
                "scenario": benchmark["scenario"],
                "approach": approach,
                "objective": comparison["objective"],
                "total_cost": comparison["total_cost"],
                "fill_rate": comparison["fill_rate"],
                "days_of_inventory": comparison["days_of_inventory"],
                "latency_seconds": profile["wall_clock_seconds"],
                "peak_process_rss_mb": profile["peak_process_rss_mb"],
                "device_level_peak_memory_gib": assessment["peak_used_gib"],
                "allocation_rate_gbps_proxy": profile["allocation_rate_gbps_proxy"],
                "gpu_utilization_percent": profile["gpu_utilization_percent"],
                "gpu_metrics_status": profile["gpu_metrics_status"],
                "ppo_outcome": benchmark["ppo_outcome"],
                "winner": winner,
                "is_winner": approach == winner,
            }
        )
    return {
        "scenario": benchmark["scenario"],
        "winner": winner,
        "ppo_outcome": benchmark["ppo_outcome"],
        "objective_tie_across_approaches": benchmark["objective_tie_across_approaches"],
        "rows": rows,
        "device_memory": {**device_memory, **assessment},
        "llm_profile": rationale["llm_profile"],
        "rationale_artifact": rationale.get("artifacts", {}).get("rationale_path"),
    }


def _bandwidth_finding(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "hardware_memory_bandwidth_gbps": 273,
        "hardware_bandwidth_source": "known GB10 platform limit; not measured by this suite",
        "direct_dram_bandwidth_measured": False,
        "allocation_rate_caveat": (
            "allocation_rate_gbps_proxy is abs(end process RSS-start process RSS)/latency; "
            "it is not DRAM bandwidth and must not be compared numerically with 273 GB/s"
        ),
        "llm_observations": [
            {
                "scenario": item["scenario"],
                "tokens_per_second": item["llm_profile"].get("tokens_per_second"),
                "peak_process_rss_mb": item["llm_profile"].get("peak_process_rss_mb"),
            }
            for item in scenarios
        ],
        "interpretation": (
            "The shared FP8 MoE LLM is the bandwidth-sensitive component: its weights and "
            "token-generation rate dominate the tiny optimizer/PPO process footprints. "
            "This is an architectural inference correlated with measured tokens/s and memory, "
            "not a direct sustained-bandwidth measurement."
        ),
    }


def build_suite_summary(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    stress = next(item for item in scenarios if item["scenario"] == "stress-large")
    stress_memory = stress["device_memory"]
    within_envelope = (
        stress_memory["peak_used_gib"] is not None and stress_memory["headroom_gib"] >= 0
    )
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "device": {
            "name": "NVIDIA GB10",
            "nominal_memory_gb": 128,
            "usable_memory_gib": USABLE_ENVELOPE_GIB,
            "known_memory_bandwidth_gbps": 273,
        },
        "device_memory_method": DEVICE_MEMORY_METHOD,
        "envelope_flag_definition": (
            f"approaches_envelope=true at >= {ENVELOPE_FLAG_FRACTION:.0%} "
            f"of the ~{USABLE_ENVELOPE_GIB:.0f} GiB usable envelope"
        ),
        "scenarios": scenarios,
        "rows": [row for item in scenarios for row in item["rows"]],
        "bandwidth_finding": _bandwidth_finding(scenarios),
        "stress_large_decision": {
            "single_node_within_usable_envelope": within_envelope,
            "two_node_path_needed_for_prototype": not within_envelope,
            "decision": (
                "Single node retained; 2-node path is an unimplemented escalation route "
                "for workloads beyond prototype scale."
                if within_envelope
                else "Single-node usable-memory limit reached; 2-node escalation is required."
            ),
            "peak_used_gib": stress_memory["peak_used_gib"],
            "headroom_gib": stress_memory["headroom_gib"],
        },
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Phase 6 on-device benchmark suite",
        "",
        f"Generated: `{summary['generated_at_utc']}`",
        "",
        (
            "**Device memory method:** "
            f"{summary['device_memory_method']}. The flag threshold is 90% of the "
            "~121 GiB usable pool (128 GB nominal)."
        ),
        "",
        "| Scenario | Approach | Objective | Total cost | Fill rate | Days inv. | "
        "Latency (s) | API peak RSS (MB) | Device peak (GiB) | Allocation-rate proxy (GB/s) | "
        "GPU util | PPO outcome | Winner |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for row in summary["rows"]:
        gpu = (
            f"{row['gpu_utilization_percent']:.1f}%"
            if row["gpu_utilization_percent"] is not None
            else "unavailable"
        )
        lines.append(
            f"| {row['scenario']} | {row['approach']} | {row['objective']:.2f} | "
            f"{row['total_cost']:.2f} | {row['fill_rate']:.4f} | "
            f"{row['days_of_inventory']:.2f} | {row['latency_seconds']:.3f} | "
            f"{row['peak_process_rss_mb']:.2f} | "
            f"{row['device_level_peak_memory_gib']:.3f} | "
            f"{row['allocation_rate_gbps_proxy']:.6f} | {gpu} | "
            f"{row['ppo_outcome']} | {row['winner']} |"
        )
    lines.extend(
        [
            "",
            "> **Reading the memory columns:** `API peak RSS` is now the peak "
            "*current* resident-set size of the api process sampled over each "
            "stage's own window, so it is a genuine per-scenario/per-approach "
            "figure (the earlier `ru_maxrss` process-lifetime high-water mark "
            "saturated after the first scenario and has been replaced). It still "
            "reflects only the api process — not the LLM/Qdrant containers — and "
            "because Python rarely returns freed memory to the OS the per-stage "
            "floor can rise within a run. The **authoritative device-level** "
            "measure remains the `/proc/meminfo` column (`Device peak (GiB)`), "
            "which is sampled fresh during each scenario and captures the whole "
            "unified pool.",
            "",
            "## Envelope and bandwidth finding",
            "",
        ]
    )
    for item in summary["scenarios"]:
        memory = item["device_memory"]
        lines.append(
            f"- `{item['scenario']}`: device peak {memory['peak_used_gib']:.3f} GiB; "
            f"headroom {memory['headroom_gib']:.3f} GiB; "
            f"90% flag {'TRIPPED' if memory['approaches_envelope'] else 'clear'}; "
            f"LLM {item['llm_profile']['tokens_per_second']:.3f} tokens/s."
        )
    lines.extend(
        [
            "",
            summary["bandwidth_finding"]["interpretation"],
            "",
            f"**Proxy caveat:** {summary['bandwidth_finding']['allocation_rate_caveat']}",
            "",
            "GPU utilization is reported as unavailable when the in-container GB10 "
            "`nvidia-smi` query returns N/A; no value is fabricated.",
            "",
            "## Stress-large decision",
            "",
            summary["stress_large_decision"]["decision"],
            "",
        ]
    )
    return "\n".join(lines)


def run_suite(
    horizon: int = 8,
    ppo_timesteps: int = 128,
    top_k: int = 5,
    benchmark_runner: Callable[..., dict[str, Any]] = run_head_to_head,
    rationale_runner: Callable[..., dict[str, Any]] = generate_advisory_rationale,
) -> dict[str, Any]:
    scenario_summaries: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        print(f"[bench-all] running {scenario}", flush=True)
        with sample_device_memory() as device_memory:
            benchmark = benchmark_runner(
                scenario,
                horizon=horizon,
                ppo_timesteps=ppo_timesteps,
            )
            rationale = rationale_runner(benchmark_result=benchmark, top_k=top_k)
        scenario_summaries.append(summarize_scenario(benchmark, rationale, device_memory))

    summary = build_suite_summary(scenario_summaries)
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    json_path = BENCHMARK_DIR / "suite-summary.json"
    markdown_path = BENCHMARK_DIR / "suite-summary.md"
    summary["artifacts"] = {
        "json": str(json_path),
        "markdown": str(markdown_path),
    }
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--ppo-timesteps", type=int, default=128)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    result = run_suite(
        horizon=args.horizon,
        ppo_timesteps=args.ppo_timesteps,
        top_k=args.top_k,
    )
    print(json.dumps(result["artifacts"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
