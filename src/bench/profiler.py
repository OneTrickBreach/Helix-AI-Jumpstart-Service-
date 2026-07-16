"""Lightweight resource profiler for pipeline runs."""

from __future__ import annotations

import json
import subprocess
import threading
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
def profile_run(name: str, scenario: str, sample_interval_seconds: float = 0.05):
    process = psutil.Process()
    start = time.perf_counter()
    start_cpu = psutil.cpu_percent(interval=None)
    start_mem = process.memory_info().rss
    start_gpu = _gpu_snapshot()

    # Sample the process's *current* RSS throughout this stage and keep the
    # window peak. The previous implementation used `ru_maxrss`, which is a
    # process-lifetime high-water mark: because the suite runs every scenario
    # in one process, that value is monotonic and saturates after the first
    # scenario, so it could not be read as a per-scenario/per-stage figure.
    # Sampling current RSS over just this stage's window gives an honest
    # per-invocation peak (still API-process RSS, not device-level unified
    # memory or the LLM/Qdrant container footprint).
    peak_rss = start_mem
    stop = threading.Event()

    def _sample_rss() -> None:
        nonlocal peak_rss
        try:
            rss = process.memory_info().rss
            if rss > peak_rss:
                peak_rss = rss
        except Exception:  # noqa: BLE001 - sampling must never break the run
            pass

    def _worker() -> None:
        while not stop.wait(sample_interval_seconds):
            _sample_rss()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    yield_data: dict = {}
    try:
        yield yield_data
    finally:
        stop.set()
        thread.join(timeout=max(1.0, sample_interval_seconds * 4))
        end = time.perf_counter()
        end_mem = process.memory_info().rss
        _sample_rss()
        end_gpu = _gpu_snapshot()
        latency = end - start
        yield_data.update(
            {
                "name": name,
                "scenario": scenario,
                "wall_clock_seconds": round(latency, 6),
                # Per-stage sampled peak of this API process's current RSS
                # (see note above). Not device-level unified-memory use and
                # not the LLM/Qdrant container footprint.
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
