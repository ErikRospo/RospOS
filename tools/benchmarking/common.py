#!/usr/bin/env python3
"""Shared helpers for benchmark scripts."""

from __future__ import annotations

import csv
import json
import re
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
    elapsed_ms, _, _ = run_command_with_output(command, cwd=cwd, timeout_s=timeout_s)
    return elapsed_ms


def run_command_with_output(
    command: list[str],
    cwd: Path,
    timeout_s: int | None = None,
) -> tuple[float, str, str]:
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

    return elapsed_ms, proc.stdout, proc.stderr


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


_HEADLESS_STEPS_RE = re.compile(r"Headless run completed in\s+(\d+)\s+steps")


def extract_headless_steps(stdout: str, stderr: str) -> int | None:
    text = "\n".join((stdout, stderr))
    match = _HEADLESS_STEPS_RE.search(text)
    if not match:
        return None
    return int(match.group(1))


def run_vm_benchmark(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    repeat: int,
    warmup: int,
    timeout_s: int | None,
) -> tuple[list[IterationResult], list[int | None]]:
    if repeat <= 0:
        raise ValueError("repeat must be > 0")
    if warmup < 0:
        raise ValueError("warmup must be >= 0")

    for i in range(1, warmup + 1):
        _, out, err = run_command_with_output(command, cwd=cwd, timeout_s=timeout_s)
        steps = extract_headless_steps(out, err)
        steps_str = str(steps) if steps is not None else "unknown"
        print(f"[{name}] warmup {i}/{warmup} complete (steps={steps_str})")

    results: list[IterationResult] = []
    step_counts: list[int | None] = []
    for i in range(1, repeat + 1):
        elapsed_ms, out, err = run_command_with_output(
            command, cwd=cwd, timeout_s=timeout_s
        )
        steps = extract_headless_steps(out, err)
        step_counts.append(steps)
        steps_str = str(steps) if steps is not None else "unknown"
        print(
            f"[{name}] iteration {i}/{repeat}: {elapsed_ms:.3f} ms (steps={steps_str})"
        )
        results.append(IterationResult(iteration=i, duration_ms=elapsed_ms))

    return results, step_counts


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


def _strip_comments_line(line: str, in_block_comment: bool) -> tuple[str, bool]:
    i = 0
    out: list[str] = []
    n = len(line)

    while i < n:
        if in_block_comment:
            end = line.find("*/", i)
            if end == -1:
                return "", True
            i = end + 2
            in_block_comment = False
            continue

        if line.startswith("//", i):
            break

        if line.startswith("/*", i):
            in_block_comment = True
            i += 2
            continue

        ch = line[i]
        if ch in ('"', "'"):
            quote = ch
            out.append(ch)
            i += 1
            while i < n:
                cur = line[i]
                out.append(cur)
                if cur == "\\" and i + 1 < n:
                    out.append(line[i + 1])
                    i += 2
                    continue
                i += 1
                if cur == quote:
                    break
            continue

        out.append(ch)
        i += 1

    return "".join(out), in_block_comment


def count_effective_lines(path: Path) -> int:
    """Count non-empty, non-comment lines using C/CPP-style comments."""
    in_block_comment = False
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped, in_block_comment = _strip_comments_line(line, in_block_comment)
        if stripped.strip():
            count += 1
    return count


def add_time_per_line_metric(
    summary: dict[str, Any], *, metric_name: str, line_count: int
) -> None:
    if line_count <= 0:
        summary[metric_name] = None
        return
    summary[metric_name] = summary["mean_ms"] / line_count


def add_instructions_per_second_metric(
    summary: dict[str, Any],
    *,
    metric_name: str,
    results: list[IterationResult],
    step_counts: list[int | None],
) -> None:
    if len(results) != len(step_counts):
        raise ValueError("results and step_counts must have the same length")

    values: list[float] = []
    for result, steps in zip(results, step_counts):
        if steps is None or result.duration_ms <= 0:
            continue
        values.append(steps * 1000.0 / result.duration_ms)

    summary[metric_name] = statistics.fmean(values) if values else None


def write_results(
    *,
    benchmark_name: str,
    command: list[str],
    metadata: dict[str, Any],
    results: list[IterationResult],
    output_dir: Path,
    summary: dict[str, Any] | None = None,
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
        "summary": summary if summary is not None else summarize(results),
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
