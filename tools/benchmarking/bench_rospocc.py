#!/usr/bin/env python3
"""Benchmark rospocc (.rosc -> .ros)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import (
    DEFAULT_RESULTS_DIR,
    ROOT,
    add_time_per_line_metric,
    count_effective_lines,
    format_summary,
    run_benchmark,
    summarize,
    write_results,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark rospocc parser performance."
    )
    parser.add_argument(
        "--input",
        default="tools/benchmarking/programs/static_test.rosc",
        help="Input .rosc file",
    )
    parser.add_argument(
        "--output",
        default="rospos/build/bench/bench.ros",
        help="Output .ros file used for each run",
    )
    parser.add_argument("--repeat", type=int, default=20, help="Measured iterations")
    parser.add_argument("--warmup", type=int, default=3, help="Warmup iterations")
    parser.add_argument(
        "--timeout", type=int, default=0, help="Timeout per run in seconds (0 disables)"
    )
    parser.add_argument(
        "--python",
        default="rospoas/venv/bin/python",
        help="Python executable path relative to repo root",
    )
    parser.add_argument(
        "--parser",
        default="rospocc/parser.py",
        help="rospocc parser script path relative to repo root",
    )
    parser.add_argument(
        "--results-dir",
        default=str(DEFAULT_RESULTS_DIR),
        help="Directory for JSON/CSV benchmark outputs",
    )
    args = parser.parse_args()

    input_path = ROOT / args.input
    output_path = ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        str(ROOT / args.python),
        str(ROOT / args.parser),
        "--input",
        str(input_path),
        "--output",
        str(output_path),
    ]

    print("Benchmarking rospocc with command:")
    print(" ", " ".join(command))

    results = run_benchmark(
        name="rospocc",
        command=command,
        cwd=ROOT,
        repeat=args.repeat,
        warmup=args.warmup,
        timeout_s=None if args.timeout == 0 else args.timeout,
    )
    summary = summarize(results)
    rosc_effective_lines = count_effective_lines(input_path)
    add_time_per_line_metric(
        summary,
        metric_name="mean_ms_per_line_rosc",
        line_count=rosc_effective_lines,
    )
    print("Summary:", format_summary(summary))
    print(
        "Per-line metric:",
        (
            f"mean_ms_per_line_rosc={summary['mean_ms_per_line_rosc']:.6f}"
            if summary["mean_ms_per_line_rosc"] is not None
            else "mean_ms_per_line_rosc=None"
        ),
    )

    json_path, csv_path = write_results(
        benchmark_name="rospocc",
        command=command,
        metadata={
            "input": str(input_path),
            "rosc_effective_lines": rosc_effective_lines,
            "output": str(output_path),
            "repeat": args.repeat,
            "warmup": args.warmup,
            "timeout_s": args.timeout,
        },
        results=results,
        output_dir=Path(args.results_dir),
        summary=summary,
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
