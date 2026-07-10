"""Lightweight resource profiler for pipeline runs."""

from __future__ import annotations

import json
import resource
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import psutil


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = REPO_ROOT / "benchmark"


def _gpu_snapshot() -> dict:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {
                "gpu_utilization_percent": None,
                "gpu_memory_used_mb": None,
                "gpu_metrics_status": "unavailable: nvidia-smi returned no supported values",
            }
        gpu_util, mem = [part.strip() for part in result.stdout.splitlines()[0].split(",")[:2]]
        if gpu_util in {"N/A", "[N/A]"} or mem in {"N/A", "[N/A]"}:
            return {
                "gpu_utilization_percent": None,
                "gpu_memory_used_mb": None,
                "gpu_metrics_status": (
                    "unavailable: GB10 unified-memory nvidia-smi query reports N/A "
                    "inside this stack"
                ),
            }
        return {
            "gpu_utilization_percent": float(gpu_util),
            "gpu_memory_used_mb": float(mem),
            "gpu_metrics_status": "available",
        }
    except Exception as exc:
        return {
            "gpu_utilization_percent": None,
            "gpu_memory_used_mb": None,
            "gpu_metrics_status": f"unavailable: {type(exc).__name__}",
        }


@contextmanager
def profile_run(name: str, scenario: str):
    process = psutil.Process()
    start = time.perf_counter()
    start_cpu = psutil.cpu_percent(interval=None)
    start_mem = process.memory_info().rss
    start_gpu = _gpu_snapshot()
    yield_data: dict = {}
    try:
        yield yield_data
    finally:
        end = time.perf_counter()
        end_mem = process.memory_info().rss
        end_gpu = _gpu_snapshot()
        latency = end - start
        # ru_maxrss is the OS-maintained high-water mark for this process, so
        # it captures transient spikes (e.g. mid-training) that a start/end
        # RSS snapshot would miss entirely. Linux reports it in KB.
        peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        yield_data.update(
            {
                "name": name,
                "scenario": scenario,
                "wall_clock_seconds": round(latency, 6),
                # This is the API process high-water RSS, not device-level
                # unified-memory use and not the LLM/Qdrant container footprint.
                "peak_process_rss_mb": round(peak_rss / (1024 * 1024), 6),
                # A start/end RSS delta divided by time is only a coarse
                # net-allocation-rate proxy. It is not measured DRAM bandwidth.
                "allocation_rate_gbps_proxy": round(
                    (abs(end_mem - start_mem) / max(latency, 1e-9)) / 1e9, 6
                ),
                "cpu_utilization_percent": psutil.cpu_percent(interval=None) or start_cpu,
                "gpu_utilization_percent": end_gpu["gpu_utilization_percent"],
                "gpu_memory_used_mb": end_gpu["gpu_memory_used_mb"],
                "gpu_metrics_status": end_gpu["gpu_metrics_status"],
                "gpu_start": start_gpu,
            }
        )


def write_json(payload: dict, filename: str) -> Path:
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    path = BENCHMARK_DIR / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
