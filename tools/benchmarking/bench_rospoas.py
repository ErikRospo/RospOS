#!/usr/bin/env python3
"""Benchmark rospoas (.ros -> .rosp)."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import DEFAULT_RESULTS_DIR, ROOT, format_summary, run_benchmark, summarize, write_results


def mode_flags(mode: str) -> list[str]:
    if mode == "full":
        return ["--debug-all"]
    if mode == "debc":
        return ["--compress-debug"]
    if mode == "binc":
        return ["--compress-bin"]
    if mode == "both":
        return ["--compress-bin", "--compress-debug"]
    raise ValueError(f"Unsupported mode: {mode}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark rospoas assembler performance.")
    parser.add_argument("--input", default="rospos/build/bench/bench.ros", help="Input .ros file")
    parser.add_argument(
        "--output",
        default="rospos/build/bench/bench.rosp",
        help="Output .rosp file used for each run",
    )
    parser.add_argument("--repeat", type=int, default=20, help="Measured iterations")
    parser.add_argument("--warmup", type=int, default=3, help="Warmup iterations")
    parser.add_argument("--timeout", type=int, default=0, help="Timeout per run in seconds (0 disables)")
    parser.add_argument(
        "--python",
        default="rospoas/venv/bin/python",
        help="Python executable path relative to repo root",
    )
    parser.add_argument(
        "--assembler",
        default="rospoas/compile.py",
        help="rospoas compile script path relative to repo root",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "debc", "binc", "both"],
        default="full",
        help="Matches Makefile output variants",
    )
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Run `make parse` if input .ros is missing",
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

    if args.prepare and not input_path.exists():
        print(f"Input {input_path} missing, running `make parse`...")
        subprocess.run(["make", "parse"], cwd=str(ROOT), check=True)

    command = [
        str(ROOT / args.python),
        str(ROOT / args.assembler),
        "--optimize",
        "--bin-version",
        "2",
        "--rospocc-mapping",
        "--segment-debug",
        *mode_flags(args.mode),
        "--input",
        str(input_path),
        "--output",
        str(output_path),
    ]

    print("Benchmarking rospoas with command:")
    print(" ", " ".join(command))

    results = run_benchmark(
        name="rospoas",
        command=command,
        cwd=ROOT,
        repeat=args.repeat,
        warmup=args.warmup,
        timeout_s=None if args.timeout == 0 else args.timeout,
    )
    summary = summarize(results)
    print("Summary:", format_summary(summary))

    json_path, csv_path = write_results(
        benchmark_name=f"rospoas_{args.mode}",
        command=command,
        metadata={
            "input": str(input_path),
            "output": str(output_path),
            "mode": args.mode,
            "repeat": args.repeat,
            "warmup": args.warmup,
            "timeout_s": args.timeout,
        },
        results=results,
        output_dir=Path(args.results_dir),
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
