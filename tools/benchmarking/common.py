#!/usr/bin/env python3
"""Shared helpers for benchmark scripts."""

from __future__ import annotations

import csv
import json
import statistics
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_DIR = ROOT / "tools" / "benchmarking" / "results"


@dataclass
class IterationResult:
    iteration: int
    duration_ms: float


def run_command(command: list[str], cwd: Path, timeout_s: int | None = None) -> float:
    start_ns = time.perf_counter_ns()
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0

    if proc.returncode != 0:
        details = []
        if proc.stdout:
            details.append(f"stdout:\n{proc.stdout.strip()}")
        if proc.stderr:
            details.append(f"stderr:\n{proc.stderr.strip()}")
        joined = "\n\n".join(details) if details else "No output captured."
        raise RuntimeError(
            "Command failed with exit code "
            f"{proc.returncode}: {' '.join(command)}\n{joined}"
        )

    return elapsed_ms


def run_benchmark(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    repeat: int,
    warmup: int,
    timeout_s: int | None,
) -> list[IterationResult]:
    if repeat <= 0:
        raise ValueError("repeat must be > 0")
    if warmup < 0:
        raise ValueError("warmup must be >= 0")

    for i in range(1, warmup + 1):
        _ = run_command(command, cwd=cwd, timeout_s=timeout_s)
        print(f"[{name}] warmup {i}/{warmup} complete")

    results: list[IterationResult] = []
    for i in range(1, repeat + 1):
        elapsed_ms = run_command(command, cwd=cwd, timeout_s=timeout_s)
        print(f"[{name}] iteration {i}/{repeat}: {elapsed_ms:.3f} ms")
        results.append(IterationResult(iteration=i, duration_ms=elapsed_ms))

    return results


def summarize(results: list[IterationResult]) -> dict[str, Any]:
    values = [r.duration_ms for r in results]
    summary: dict[str, Any] = {
        "count": len(values),
        "min_ms": min(values),
        "max_ms": max(values),
        "mean_ms": statistics.fmean(values),
        "median_ms": statistics.median(values),
    }
    summary["stdev_ms"] = statistics.stdev(values) if len(values) > 1 else 0.0
    return summary


def write_results(
    *,
    benchmark_name: str,
    command: list[str],
    metadata: dict[str, Any],
    results: list[IterationResult],
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{benchmark_name}_{stamp}"
    json_path = output_dir / f"{base}.json"
    csv_path = output_dir / f"{base}.csv"

    payload = {
        "benchmark": benchmark_name,
        "command": command,
        "metadata": metadata,
        "summary": summarize(results),
        "iterations": [r.__dict__ for r in results],
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["iteration", "duration_ms"])
        writer.writeheader()
        for row in payload["iterations"]:
            writer.writerow(row)

    return json_path, csv_path


def format_summary(summary: dict[str, Any]) -> str:
    return (
        f"count={summary['count']} "
        f"min={summary['min_ms']:.3f}ms "
        f"max={summary['max_ms']:.3f}ms "
        f"mean={summary['mean_ms']:.3f}ms "
        f"median={summary['median_ms']:.3f}ms "
        f"stdev={summary['stdev_ms']:.3f}ms"
    )
