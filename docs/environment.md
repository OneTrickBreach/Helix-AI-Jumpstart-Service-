# GB10 Live Environment Reference

> **Generated from the live device on 2026-06-26 (UTC).** Every value below was read
> from a command actually run on this machine (`helix-gb10-intern`) over SSH. Nothing
> here is copied from a spec sheet — re-run the commands to refresh.

## Device environment (live values)

| Property | Value | Source command |
|---|---|---|
| GPU / device name | NVIDIA GB10 | `nvidia-smi --query-gpu=name,...` |
| Unified memory capacity | 121 GiB total RAM (unified CPU+GPU); `nvidia-smi` reports `memory.total = N/A` because the GPU shares the Grace unified memory pool rather than a dedicated VRAM region | `free -h`; `nvidia-smi --query-gpu=memory.total` |
| CPU | 20× ARM aarch64 cores — 10× Cortex-X925 + 10× Cortex-A725 (1 socket, 1 thread/core, max 3.9 GHz) | `lscpu`, `nproc` |
| Core count | 20 | `nproc` |
| OS | Ubuntu 24.04.4 LTS (Noble Numbat) | `cat /etc/os-release` |
| Kernel | `6.17.0-1021-nvidia` (`#21-Ubuntu SMP PREEMPT_DYNAMIC`, aarch64) | `uname -a` |
| NVIDIA driver version | 580.159.03 | `nvidia-smi` |
| CUDA **runtime** version (driver-reported) | 13.0 | `nvidia-smi` |
| CUDA **toolkit** version (compiler) | release 13.0, V13.0.88 (`cuda_13.0.r13.0/compiler.36424714_0`) | `nvcc --version` |
| Python | 3.12.3 | `python3 --version` |
| pip | 24.0 | `pip --version` |
| Docker | present — version 29.2.1, build a5c7197 (`/usr/bin/docker`) | `docker --version` |
| conda | not installed | `which conda` |
| Root filesystem | `/dev/nvme0n1p3` — 1.9 TB total, 1.7 TB available, 3% used | `df -h /` |

> **Note — runtime vs toolkit CUDA are different things.** The CUDA *runtime* version
> reported by `nvidia-smi` (13.0) reflects the **maximum** CUDA version the installed
> driver supports. The CUDA *toolkit* version from `nvcc` (13.0.88) is the actual
> compiler/toolchain installed on disk. They happen to align here (both 13.0), but they
> are independent and can legitimately differ.

## Known constraints

- **Single Grace+Blackwell unified-memory device.** CPU and GPU share one physical
  memory pool; there is no separate VRAM to budget against.
- **The binding constraint for memory-bound workloads is memory BANDWIDTH, not the
  128 GB capacity.** Bandwidth is the thing to benchmark. Do **not** assume the ~128 GB
  (121 GiB observed) capacity is the limiter — for large-LLM token generation and big
  RL batches, sustained memory bandwidth saturates first.
- **cuOpt is NOT preinstalled.** It must be pulled from NGC when needed, and verified to
  run on ARM64 (aarch64) early.

---

*Doc generated 2026-06-26 (UTC) from `helix-gb10-intern`. Re-run the Step 1 probe
commands to regenerate if the device changes.*
