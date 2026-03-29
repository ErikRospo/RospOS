#!/usr/bin/env python3
"""Run end-to-end benchmark series for rospocc, rospoas, and rospovm."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import DEFAULT_RESULTS_DIR, ROOT, format_summary, run_benchmark, summarize, add_time_per_line_metric, count_effective_lines


def maybe_prepare(prepare: bool) -> None:
    if not prepare:
        return
    print("Preparing build artifacts with `make bm parse vm_headless`...")
    subprocess.run(["make", "bm", "parse", "vm_headless"], cwd=str(ROOT), check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full benchmark suite.")
    parser.add_argument("--input-rosc", default="tools/benchmarking/programs/static_test.rosc", help="Input .rosc program")
    parser.add_argument("--repeat", type=int, default=20, help="Measured iterations per stage")
    parser.add_argument("--warmup", type=int, default=3, help="Warmup iterations per stage")
    parser.add_argument("--timeout", type=int, default=0, help="Timeout per run in seconds (0 disables)")
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Run Makefile prep targets before benchmarking",
    )
    parser.add_argument(
        "--results-dir",
        default=str(DEFAULT_RESULTS_DIR),
        help="Directory for aggregate benchmark output",
    )
    args = parser.parse_args()

    maybe_prepare(args.prepare)

    bench_dir = ROOT / "rospos" / "build" / "bench"
    bench_dir.mkdir(parents=True, exist_ok=True)

    rosc_in = ROOT / args.input_rosc
    ros_out = bench_dir / "all_bench.ros"
    rosp_out = bench_dir / "all_bench.rosp"

    timeout = None if args.timeout == 0 else args.timeout

    rospocc_cmd = [
        str(ROOT / "rospoas/venv/bin/python"),
        str(ROOT / "rospocc/parser.py"),
        "--input",
        str(rosc_in),
        "--output",
        str(ros_out),
    ]
    rospoas_cmd = [
        str(ROOT / "rospoas/venv/bin/python"),
        str(ROOT / "rospoas/compile.py"),
        "--optimize",
        "--bin-version",
        "2",
        "--rospocc-mapping",
        "--segment-debug",
        "--debug-all",
        "--input",
        str(ros_out),
        "--output",
        str(rosp_out),
    ]
    vm_cmd = [str(ROOT / "rospovm/build/rospovm_headless"), str(rosp_out)]

    print("Running rospocc benchmark...")
    rospocc_results = run_benchmark(
        name="rospocc",
        command=rospocc_cmd,
        cwd=ROOT,
        repeat=args.repeat,
        warmup=args.warmup,
        timeout_s=timeout,
    )

    print("Running rospoas benchmark...")
    rospoas_results = run_benchmark(
        name="rospoas",
        command=rospoas_cmd,
        cwd=ROOT,
        repeat=args.repeat,
        warmup=args.warmup,
        timeout_s=timeout,
    )

    print("Running VM benchmark...")
    vm_results = run_benchmark(
        name="rospovm_headless",
        command=vm_cmd,
        cwd=ROOT,
        repeat=args.repeat,
        warmup=args.warmup,
        timeout_s=timeout,
    )

    rosc_effective_lines = count_effective_lines(rosc_in)
    ros_effective_lines = count_effective_lines(ros_out)

    rospocc_summary = summarize(rospocc_results)
    add_time_per_line_metric(
        rospocc_summary,
        metric_name="mean_ms_per_line_rosc",
        line_count=rosc_effective_lines,
    )

    rospoas_summary = summarize(rospoas_results)
    add_time_per_line_metric(
        rospoas_summary,
        metric_name="mean_ms_per_line_rosc",
        line_count=rosc_effective_lines,
    )
    add_time_per_line_metric(
        rospoas_summary,
        metric_name="mean_ms_per_line_ros",
        line_count=ros_effective_lines,
    )

    result_dir = Path(args.results_dir)
    result_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = result_dir / f"benchmark_all_{stamp}.json"

    payload = {
        "benchmark": "all",
        "metadata": {
            "input_rosc": str(rosc_in),
            "rosc_effective_lines": rosc_effective_lines,
            "generated_ros": str(ros_out),
            "ros_effective_lines": ros_effective_lines,
            "generated_rosp": str(rosp_out),
            "repeat": args.repeat,
            "warmup": args.warmup,
            "timeout_s": args.timeout,
        },
        "stages": {
            "rospocc": {
                "command": rospocc_cmd,
                "summary": rospocc_summary,
                "iterations": [r.__dict__ for r in rospocc_results],
            },
            "rospoas": {
                "command": rospoas_cmd,
                "summary": rospoas_summary,
                "iterations": [r.__dict__ for r in rospoas_results],
            },
            "rospovm_headless": {
                "command": vm_cmd,
                "summary": summarize(vm_results),
                "iterations": [r.__dict__ for r in vm_results],
            },
        },
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("Stage summaries:")
    print("  rospocc        ", format_summary(payload["stages"]["rospocc"]["summary"]))
    print(
        "                 mean_ms_per_line_rosc=",
        f"{payload['stages']['rospocc']['summary']['mean_ms_per_line_rosc']:.6f}"
        if payload["stages"]["rospocc"]["summary"]["mean_ms_per_line_rosc"] is not None
        else "None",
    )
    print("  rospoas        ", format_summary(payload["stages"]["rospoas"]["summary"]))
    print(
        "                 mean_ms_per_line_rosc=",
        f"{payload['stages']['rospoas']['summary']['mean_ms_per_line_rosc']:.6f}"
        if payload["stages"]["rospoas"]["summary"]["mean_ms_per_line_rosc"] is not None
        else "None",
    )
    print(
        "                 mean_ms_per_line_ros=",
        f"{payload['stages']['rospoas']['summary']['mean_ms_per_line_ros']:.6f}"
        if payload["stages"]["rospoas"]["summary"]["mean_ms_per_line_ros"] is not None
        else "None",
    )
    print("  rospovm_headless", format_summary(payload["stages"]["rospovm_headless"]["summary"]))
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
