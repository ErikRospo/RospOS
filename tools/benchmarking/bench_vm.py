#!/usr/bin/env python3
"""Benchmark rospovm headless execution (.rosp runtime)."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import DEFAULT_RESULTS_DIR, ROOT, format_summary, run_benchmark, summarize, write_results


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark rospovm headless runtime performance.")
    parser.add_argument("--binary", default="rospos/build/rospos.rosp", help="Input .rosp binary")
    parser.add_argument(
        "--vm",
        default="rospovm/build/rospovm_headless",
        help="VM executable path relative to repo root",
    )
    parser.add_argument("--repeat", type=int, default=20, help="Measured iterations")
    parser.add_argument("--warmup", type=int, default=3, help="Warmup iterations")
    parser.add_argument("--timeout", type=int, default=0, help="Timeout per run in seconds (0 disables)")
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Run `make compile vm_headless` if binary or VM executable is missing",
    )
    parser.add_argument(
        "--results-dir",
        default=str(DEFAULT_RESULTS_DIR),
        help="Directory for JSON/CSV benchmark outputs",
    )
    args = parser.parse_args()

    binary_path = ROOT / args.binary
    vm_path = ROOT / args.vm

    if args.prepare and (not binary_path.exists() or not vm_path.exists()):
        print("Missing benchmark input artifacts, running `make compile vm_headless`...")
        subprocess.run(["make", "compile", "vm_headless"], cwd=str(ROOT), check=True)

    command = [str(vm_path), str(binary_path)]

    print("Benchmarking VM with command:")
    print(" ", " ".join(command))

    results = run_benchmark(
        name="rospovm_headless",
        command=command,
        cwd=ROOT,
        repeat=args.repeat,
        warmup=args.warmup,
        timeout_s=None if args.timeout == 0 else args.timeout,
    )
    summary = summarize(results)
    print("Summary:", format_summary(summary))

    json_path, csv_path = write_results(
        benchmark_name="rospovm_headless",
        command=command,
        metadata={
            "binary": str(binary_path),
            "vm": str(vm_path),
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
