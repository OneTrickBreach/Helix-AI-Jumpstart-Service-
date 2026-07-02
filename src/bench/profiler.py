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
            return {"gpu_utilization_percent": None, "gpu_memory_used_mb": None}
        gpu_util, mem = [part.strip() for part in result.stdout.splitlines()[0].split(",")[:2]]
        return {"gpu_utilization_percent": float(gpu_util), "gpu_memory_used_mb": float(mem)}
    except Exception:
        return {"gpu_utilization_percent": None, "gpu_memory_used_mb": None}


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
                "peak_unified_memory_mb": round(peak_rss / (1024 * 1024), 6),
                "effective_memory_bandwidth_gbps": round((abs(end_mem - start_mem) / max(latency, 1e-9)) / 1e9, 6),
                "cpu_utilization_percent": psutil.cpu_percent(interval=None) or start_cpu,
                "gpu_utilization_percent": end_gpu["gpu_utilization_percent"],
                "gpu_memory_used_mb": end_gpu["gpu_memory_used_mb"],
                "gpu_start": start_gpu,
            }
        )


def write_json(payload: dict, filename: str) -> Path:
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    path = BENCHMARK_DIR / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
