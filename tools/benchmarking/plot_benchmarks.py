#!/usr/bin/env python3
"""Plot benchmark trends over time from JSON benchmark outputs."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from common import DEFAULT_RESULTS_DIR, ROOT


@dataclass
class MetricSpec:
    key: str
    label: str
    higher_is_better: bool


@dataclass
class RunPoint:
    timestamp: datetime
    source: Path
    metrics: dict[str, float]


METRICS: list[MetricSpec] = [
    MetricSpec("rospocc.mean_ms", "rospocc mean (ms)", False),
    MetricSpec("rospocc.mean_ms_per_line_rosc", "rospocc mean ms/line (.rosc)", False),
    MetricSpec("rospoas.mean_ms", "rospoas mean (ms)", False),
    MetricSpec("rospoas.mean_ms_per_line_rosc", "rospoas mean ms/line (.rosc)", False),
    MetricSpec("rospoas.mean_ms_per_line_ros", "rospoas mean ms/line (.ros)", False),
    MetricSpec("rospovm_headless.mean_ms", "rospovm headless mean (ms)", False),
    MetricSpec(
        "rospovm_headless.mean_instructions_per_second",
        "rospovm headless instr/s",
        True,
    ),
]


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return v if math.isfinite(v) else None
    return None


def _extract_timestamp(payload: dict[str, object], source: Path) -> datetime:
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        end_ts = metadata.get("end_ts_unix")
        if isinstance(end_ts, (int, float)):
            return datetime.fromtimestamp(float(end_ts))

    stem = source.stem
    parts = stem.split("_")
    if len(parts) >= 3:
        maybe_stamp = "_".join(parts[-2:])
        try:
            return datetime.strptime(maybe_stamp, "%Y%m%d_%H%M%S")
        except ValueError:
            pass

    return datetime.fromtimestamp(source.stat().st_mtime)


def _extract_metrics(payload: dict[str, object]) -> dict[str, float]:
    out: dict[str, float] = {}
    stages = payload.get("stages")
    if not isinstance(stages, dict):
        return out

    for stage_name in ("rospocc", "rospoas", "rospovm_headless"):
        stage = stages.get(stage_name)
        if not isinstance(stage, dict):
            continue
        summary = stage.get("summary")
        if not isinstance(summary, dict):
            continue

        for metric_name in (
            "mean_ms",
            "mean_ms_per_line_rosc",
            "mean_ms_per_line_ros",
            "mean_instructions_per_second",
        ):
            value = _as_float(summary.get(metric_name))
            if value is None:
                continue
            out[f"{stage_name}.{metric_name}"] = value

    return out


def collect_points(results_dir: Path, limit: int | None) -> list[RunPoint]:
    files = sorted(results_dir.glob("benchmark_all_*.json"))
    if limit is not None and limit > 0:
        files = files[-limit:]

    points: list[RunPoint] = []
    for file_path in files:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        metrics = _extract_metrics(payload)
        if not metrics:
            continue
        points.append(
            RunPoint(
                timestamp=_extract_timestamp(payload, file_path),
                source=file_path,
                metrics=metrics,
            )
        )

    points.sort(key=lambda p: p.timestamp)
    return points


def improvement_percent(first: float, latest: float, higher_is_better: bool) -> float:
    if first == 0.0:
        return float("nan")
    if higher_is_better:
        return (latest - first) / first * 100.0
    return (first - latest) / first * 100.0


def format_delta(delta_pct: float) -> str:
    if not math.isfinite(delta_pct):
        return "n/a"
    sign = "+" if delta_pct >= 0 else ""
    return f"{sign}{delta_pct:.2f}%"


def print_summary(points: list[RunPoint]) -> None:
    if len(points) < 2:
        print("Need at least 2 benchmark runs to compute improvements.")
        return

    print("Improvements from first to latest run:")
    first = points[0]
    latest = points[-1]

    for spec in METRICS:
        f = first.metrics.get(spec.key)
        l = latest.metrics.get(spec.key)
        if f is None or l is None:
            continue
        delta = improvement_percent(f, l, spec.higher_is_better)
        print(f"  {spec.label}: {f:.6g} -> {l:.6g} ({format_delta(delta)})")


def save_plot(points: list[RunPoint], output_path: Path, title: str) -> None:
    try:
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "matplotlib is required for plotting. "
            "Install it with: rospoas/venv/bin/pip install matplotlib"
        ) from exc

    available_specs: list[MetricSpec] = []
    for spec in METRICS:
        if any(spec.key in p.metrics for p in points):
            available_specs.append(spec)

    if not available_specs:
        raise RuntimeError("No supported metrics found in benchmark data.")

    ncols = 2
    nrows = math.ceil(len(available_specs) / ncols)
    fig, axes = plt.subplots(
        nrows=nrows,
        ncols=ncols,
        figsize=(14, max(4 * nrows, 5)),
        constrained_layout=True,
    )

    if hasattr(axes, "ravel"):
        flat_axes = list(axes.ravel())
    else:
        flat_axes = [axes]

    x_values = [p.timestamp for p in points]

    for idx, spec in enumerate(available_specs):
        ax = flat_axes[idx]
        y_values = [p.metrics.get(spec.key, float("nan")) for p in points]
        ax.plot(x_values, y_values, marker="o", linewidth=1.8)
        ax.set_title(spec.label)
        ax.set_xlabel("Time")
        ax.set_ylabel("Value")
        ax.grid(True, linestyle="--", alpha=0.35)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))

        finite_values = [v for v in y_values if math.isfinite(v)]
        if len(finite_values) >= 2:
            delta = improvement_percent(
                finite_values[0], finite_values[-1], spec.higher_is_better
            )
            ax.text(
                0.02,
                0.96,
                f"Delta: {format_delta(delta)}",
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=9,
                bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "alpha": 0.7},
            )

    for idx in range(len(available_specs), len(flat_axes)):
        fig.delaxes(flat_axes[idx])

    fig.suptitle(title)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plot benchmark improvements over time for multiple metrics."
    )
    parser.add_argument(
        "--results-dir",
        default=str(DEFAULT_RESULTS_DIR),
        help="Directory containing benchmark_all_*.json files",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only use the newest N runs (0 uses all)",
    )
    parser.add_argument(
        "--output",
        default="tools/benchmarking/results/benchmark_trends.png",
        help="Output image path",
    )
    parser.add_argument(
        "--title",
        default="RospOS Benchmark Trends",
        help="Plot title",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    if not results_dir.is_absolute():
        results_dir = ROOT / results_dir

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = ROOT / output_path

    points = collect_points(results_dir, None if args.limit == 0 else args.limit)
    if not points:
        print(f"No benchmark_all JSON files found in {results_dir}")
        return 1

    print(f"Loaded {len(points)} benchmark runs from {results_dir}")
    print(f"Range: {points[0].timestamp} -> {points[-1].timestamp}")
    print_summary(points)
    save_plot(points, output_path, args.title)
    print(f"Wrote plot: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
