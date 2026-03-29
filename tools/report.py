#!/usr/bin/env python3
"""
Build Report Generator for RospOS

Analyzes build artifacts in rospos/build/ and generates comprehensive
statistics about compilation, optimization, and binary sizes.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class FileSize:
    """File size information"""

    name: str
    path: str
    size: int

    def size_kb(self) -> float:
        return self.size / 1024

    def size_mb(self) -> float:
        return self.size / (1024 * 1024)


class Colors:
    """ANSI color codes for terminal output"""

    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"

    @staticmethod
    def disable():
        """Disable colors (for piping to files)"""
        for attr in dir(Colors):
            if not attr.startswith("_"):
                setattr(Colors, attr, "")


def humanize_size(size: int) -> str:
    """Convert bytes to human-readable format"""
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    else:
        return f"{size / (1024 * 1024):.1f}MB"


def percentage_change(before: int, after: int) -> Tuple[float, str]:
    """Calculate percentage change and direction"""
    if before == 0:
        return 0.0, "N/A"
    change = ((after - before) / before) * 100
    if change < 0:
        return abs(change), "↓"
    else:
        return change, "↑"


class BuildAnalyzer:
    """Analyzes RospOS build artifacts"""

    def __init__(self, build_dir: Path):
        self.build_dir = build_dir
        self.files: Dict[str, FileSize] = {}
        self._index_files()

    def _index_files(self):
        """Index all build artifacts"""
        for file_path in self.build_dir.glob("*"):
            if file_path.is_file():
                size = file_path.stat().st_size
                self.files[file_path.name] = FileSize(
                    name=file_path.name, path=str(file_path), size=size
                )

    def get_file(self, name: str) -> Optional[FileSize]:
        """Get file by name"""
        return self.files.get(name)

    def read_file_lines(self, name: str) -> List[str]:
        """Read file lines safely"""
        file_info = self.get_file(name)
        if not file_info:
            return []
        try:
            with open(file_info.path, "r", encoding="utf-8", errors="ignore") as f:
                return f.readlines()
        except Exception as e:
            print(f"{Colors.RED}Error reading {name}: {e}{Colors.END}")
            return []

    def count_instructions(self, file_name: str) -> int:
        """Count instruction objects in debug file"""
        lines = self.read_file_lines(file_name)
        # Count lines that start with "Instruction("
        count = sum(1 for line in lines if re.match(r"^\s*Instruction\(", line))
        return count

    def analyze_optimization_log(self) -> Dict[str, Any]:
        """Parse optimization log and classify optimization events"""
        lines = self.read_file_lines("debug_opt_log.txt")

        optimization_stats = {
            "lines_parsed": 0,
            "unknown_events": 0,
            "event_counts": {},
            "instruction_removals": {},
            "pop_push_removals": [],
            "safe_offset_combinations": 0,
            "label_removals": 0,
            "rewrite_events": 0,
            "total_instructions_removed": 0,
        }

        def record_event(event_key: str, removed: int = 0, is_rewrite: bool = False):
            optimization_stats["event_counts"][event_key] = (
                optimization_stats["event_counts"].get(event_key, 0) + 1
            )
            if removed > 0:
                optimization_stats["instruction_removals"][event_key] = (
                    optimization_stats["instruction_removals"].get(event_key, 0)
                    + removed
                )
                optimization_stats["total_instructions_removed"] += removed
            if is_rewrite:
                optimization_stats["rewrite_events"] += 1

        for line in lines:
            line = line.strip()
            if not line:
                continue

            optimization_stats["lines_parsed"] += 1

            # Parse: "Removed POP/PUSH cancellation block at indices 395-402 (len=8)"
            match = re.search(
                r"Removed POP/PUSH cancellation block.*\(len=(\d+)\)", line
            )
            if match:
                length = int(match.group(1))
                optimization_stats["pop_push_removals"].append(length)
                record_event("pop_push_cancellation", removed=length)
                continue

            if line.startswith("Combined safe offset calc"):
                optimization_stats["safe_offset_combinations"] += 1
                # This optimization removes the preceding LLI + ADD/SUB pair.
                record_event("safe_offset_combination", removed=2, is_rewrite=True)
                continue

            if line.startswith("Removed unneeded move by combining"):
                record_event("remove_unneeded_move", removed=1, is_rewrite=True)
                continue

            if line.startswith("Removed unneeded jmp pseudo before label"):
                record_event("remove_unneeded_jump", removed=1)
                continue

            if line.startswith("Removed effective NOP instruction"):
                record_event("remove_nop", removed=1)
                continue

            if line.startswith("Threaded jump at index"):
                record_event("thread_jump_chain", is_rewrite=True)
                continue

            if line.startswith("Removed unreachable instruction"):
                record_event("remove_unreachable_after_jump", removed=1)
                continue

            if line.startswith("Removed unused label"):
                optimization_stats["label_removals"] += 1
                record_event("remove_unused_label")
                continue

            if line.startswith("Converted PUSH/POP to move"):
                # Two pseudo instructions become one ADDI move.
                record_event("push_pop_to_move", removed=1, is_rewrite=True)
                continue

            if line.startswith("Removed redundant PUSH/POP of same register"):
                record_event("remove_redundant_push_pop", removed=2)
                continue

            optimization_stats["unknown_events"] += 1

        return optimization_stats

    def analyze_ir(self) -> Dict[str, Any]:
        """Analyze intermediate representation for instruction types"""
        lines = self.read_file_lines("rospos_ir.txt")
        instruction_types = {}
        subtypes_by_type: Dict[str, Dict[str, int]] = {}
        total_instructions = 0

        for line in lines:
            if not line.lstrip().startswith("Instruction("):
                continue

            # Extract instruction type (p, r, i, l, j, b) and mnemonic subtype.
            type_match = re.search(r"type='([^']+)'", line)
            name_match = re.search(r"name='([^']+)'", line)
            if not type_match:
                continue

            instr_type = type_match.group(1)
            instruction_types[instr_type] = instruction_types.get(instr_type, 0) + 1
            total_instructions += 1

            if name_match:
                instr_name = name_match.group(1)
                if instr_type not in subtypes_by_type:
                    subtypes_by_type[instr_type] = {}
                subtypes_by_type[instr_type][instr_name] = (
                    subtypes_by_type[instr_type].get(instr_name, 0) + 1
                )

        return {
            "total": total_instructions,
            "by_type": instruction_types,
            "subtypes_by_type": subtypes_by_type,
        }

    def analyze_layout(self) -> Dict[str, Any]:
        """Parse memory layout"""
        lines = self.read_file_lines("rospos_layout.txt")
        layout = {
            "segments": {},
            "labels": {},
            "total_code_size": 0,
            "total_data_size": 0,
        }

        in_segments = False
        in_labels = False

        for line in lines:
            line = line.strip()
            if line == "Segments:":
                in_segments = True
                in_labels = False
                continue
            elif line == "Labels:":
                in_segments = False
                in_labels = True
                continue

            if in_segments and line:
                match = re.match(r"(0x[0-9A-Fa-f]+)\s+size=(\d+)", line)
                if match:
                    addr = match.group(1)
                    size = int(match.group(2))
                    layout["segments"][addr] = size

            elif in_labels and line and "->" in line:
                parts = line.split(" -> ")
                if len(parts) == 2:
                    label = parts[0].strip()
                    addr = parts[1].strip()
                    layout["labels"][label] = addr

        return layout


def print_header(title: str):
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.HEADER}{title:^70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*70}{Colors.END}\n")


def print_section(title: str):
    """Print a formatted section"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}▶ {title}{Colors.END}")
    print(f"{Colors.GRAY}{'-'*70}{Colors.END}")


def print_metric(label: str, value: str, color: Optional[str] = None):
    """Print a metric line"""
    if color is None:
        color = Colors.END
    print(f"  {label:<40} {color}{value}{Colors.END}")


def top_items(counts: Dict[str, int], limit: int = 5) -> List[Tuple[str, int]]:
    """Return top items sorted by frequency (desc), then name (asc)."""
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]


def print_comparison(label: str, before: int, after: int, reduction: bool = True):
    """Print a before/after comparison"""
    delta = after - before
    percentage, direction = percentage_change(before, after)

    is_good = (delta < 0) if reduction else (delta > 0)
    color = Colors.GREEN if is_good else Colors.RED
    delta_str = f"{direction}{humanize_size(abs(delta))}"

    print(f"  {label:<40} {humanize_size(before):>10} → {humanize_size(after):>10}")
    print(f"  {'':<40} {delta_str:>10} ({percentage:.1f}%)")


def print_file_sizes(analyzer: BuildAnalyzer):
    """Print file size analysis"""
    print_section("Build Artifacts Size Analysis")

    stages = [
        ("rospos_preprocessed.rosc", "ROSC source (preprocessed)"),
        ("rospos.ros", "Compiled ROS Assembly"),
        ("rospos_preprocessed.ros", "ROS Assembly (preprocessed)"),
        ("rospos_c.rosp", "All-compressed (ROSP)"),
        ("rospos_debc.rosp", "Debug-compressed executable (ROSP)"),
        ("rospos_binc.rosp", "Binary-compressed executable (ROSP)"),
        ("rospos.rosp", "Uncompressed Binary (ROSP)"),
    ]

    sizes = {}
    for file_name, description in stages:
        file_info = analyzer.get_file(file_name)
        if file_info:
            sizes[file_name] = file_info.size
            size_str = f"{humanize_size(file_info.size)} ({file_info.size:,} bytes)"
            print_metric(description, size_str, Colors.BLUE)

    print()
    if "rospos_c.rosp" in sizes and "rospos.rosp" in sizes:
        print_comparison(
            "Uncompressed → Compressed ROSP size",
            sizes["rospos.rosp"],
            sizes["rospos_c.rosp"],
        )
        print()

    if "rospos_c.rosp" in sizes and "rospos_binc.rosp" in sizes:
        print_metric("C ROSP size (initial)", humanize_size(sizes["rospos_c.rosp"]))
        print_metric(
            "BinC ROSP size (optimized)", humanize_size(sizes["rospos_binc.rosp"])
        )
        print_metric("Final ROSP size", humanize_size(sizes.get("rospos.rosp", 0)))


def print_optimization_stats(analyzer: BuildAnalyzer):
    """Print optimization statistics"""
    print_section("Optimization Results")

    before_count = analyzer.count_instructions("debug_before_opt.txt")
    after_count = analyzer.count_instructions("debug_after_opt.txt")

    print_metric("Instructions before optimization", f"{before_count:,}")
    print_metric("Instructions after optimization", f"{after_count:,}")

    if before_count > 0:
        removed = before_count - after_count
        percentage = (removed / before_count) * 100
        print()
        print_metric(
            "Instructions removed", f"{removed:,} ({percentage:.1f}%)", Colors.GREEN
        )
        print_metric(
            "Estimated bytes saved",
            f"~{removed * 4} bytes (assuming 4B/instr)",
            Colors.GREEN,
        )

    opt_stats = analyzer.analyze_optimization_log()
    if opt_stats["lines_parsed"] > 0:
        print()
        print_metric("Optimization log entries", f"{opt_stats['lines_parsed']:,}")
        if opt_stats["unknown_events"] > 0:
            print_metric(
                "Optimization events recognized",
                f"{sum(opt_stats['event_counts'].values()):,}",
            )
            print_metric(
                "Unrecognized log entries",
                f"{opt_stats['unknown_events']:,}",
                Colors.YELLOW,
            )
    else:
        print(
            f"{Colors.YELLOW}No optimization log entries found or parsed.{Colors.END}"
        )
        return
    event_labels = {
        "pop_push_cancellation": "POP/PUSH cancellation blocks",
        "safe_offset_combination": "Safe offset calc combinations",
        "remove_unneeded_move": "Unneeded moves removed",
        "remove_unneeded_jump": "Unneeded jumps removed",
        "remove_nop": "NOP-equivalent instructions removed",
        "thread_jump_chain": "Jump chains threaded",
        "remove_unreachable_after_jump": "Unreachable instructions removed",
        "remove_unused_label": "Unused labels removed",
        "push_pop_to_move": "PUSH/POP pairs converted to moves",
        "remove_redundant_push_pop": "Redundant PUSH/POP pairs removed",
    }

    if opt_stats["event_counts"]:
        print()
        for key, count in sorted(
            opt_stats["event_counts"].items(), key=lambda kv: kv[1], reverse=True
        ):
            label = event_labels.get(key, key.replace("_", " "))
            print_metric(f"  {label}", f"{count:,}")

    if opt_stats["instruction_removals"]:
        print()
        print(
            f"{Colors.GRAY}  Top optimization impacts (estimated removed instructions):{Colors.END}"
        )
        top_impact = sorted(
            opt_stats["instruction_removals"].items(),
            key=lambda kv: kv[1],
            reverse=True,
        )[:5]
        for key, removed in top_impact:
            count = opt_stats["event_counts"].get(key, 0)
            avg = removed / count if count > 0 else 0.0
            label = event_labels.get(key, key.replace("_", " "))
            print_metric(
                f"    {label}", f"{removed:,} total (avg {avg:.1f} removed/event)"
            )

    if opt_stats["label_removals"] > 0:
        print_metric("Labels removed", f"{opt_stats['label_removals']:,}")

    if opt_stats["rewrite_events"] > 0:
        print_metric("Instruction rewrite events", f"{opt_stats['rewrite_events']:,}")


def print_memory_layout(analyzer: BuildAnalyzer):
    """Print memory layout analysis"""
    print_section("Memory Layout & Segments")

    layout = analyzer.analyze_layout()

    if layout["segments"]:
        print_metric("Segments found", f"{len(layout['segments'])}")
        for addr, size in sorted(layout["segments"].items()):
            print_metric(f"  Segment: {addr}", humanize_size(size))

    total_labeled = len(layout["labels"])
    print_metric("Labels defined", f"{total_labeled}")


def print_instruction_types(analyzer: BuildAnalyzer):
    """Print instruction type breakdown"""
    print_section("Instruction Type Analysis")

    ir_stats = analyzer.analyze_ir()

    if ir_stats["total"] > 0:
        print_metric("Total IR instructions", f"{ir_stats['total']:,}")
        print()

        type_names = {
            "p": "Pseudo instructions",
            "r": "Register-type (R-type)",
            "i": "Immediate-type (I-type)",
            "l": "Load/Store-type (L-type)",
            "j": "Jump-type (J-type)",
            "b": "Branch-type (B-type)",
        }

        for instr_type in ["p", "r", "i", "l", "j", "b"]:
            if instr_type in ir_stats["by_type"]:
                count = ir_stats["by_type"][instr_type]
                percentage = (count / ir_stats["total"]) * 100
                name = type_names.get(instr_type, f"Type {instr_type}")
                print_metric(f"  {name}", f"{count:,} ({percentage:.1f}%)")

                subtype_counts = ir_stats.get("subtypes_by_type", {}).get(
                    instr_type, {}
                )
                if subtype_counts:
                    for subtype, subtype_count in top_items(subtype_counts, limit=5):
                        subtype_pct = (subtype_count / count) * 100 if count > 0 else 0
                        print_metric(
                            f"    {subtype}",
                            f"{subtype_count:,} ({subtype_pct:.1f}% of {instr_type}-type)",
                            Colors.GRAY,
                        )
                    print()


def print_summary(analyzer: BuildAnalyzer):
    """Print build summary"""
    print_section("Summary Statistics")

    before_count = analyzer.count_instructions("debug_before_opt.txt")
    after_count = analyzer.count_instructions("debug_after_opt.txt")
    final_rosp = analyzer.get_file("rospos.rosp")
    source_ros = analyzer.get_file("rospos.ros")

    print_metric("Total instructions (before opt)", f"{before_count:,}")
    print_metric("Total instructions (after opt)", f"{after_count:,}")
    if before_count > after_count:
        opt_improvement = ((before_count - after_count) / before_count) * 100
        print_metric(
            "Optimization improvement",
            f"{opt_improvement:.1f}% ({before_count - after_count:,} saved)",
            Colors.GREEN,
        )

    print()

    if source_ros and final_rosp:
        ratio = final_rosp.size / source_ros.size if source_ros.size > 0 else 0
        print_metric("Source → Binary expansion ratio", f"{ratio:.2f}x")
        print_metric("Source size", humanize_size(source_ros.size))
        print_metric("Binary size", humanize_size(final_rosp.size))

    print()

    layout = analyzer.analyze_layout()
    print_metric("Memory segments allocated", f"{len(layout['segments'])}")
    print_metric("Functions/labels defined", f"{len(layout['labels'])}")

    if final_rosp:
        print_metric("Final binary size", humanize_size(final_rosp.size), Colors.BLUE)


def main():
    """Main entry point"""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    build_dir = project_root / "rospos" / "build"

    if not build_dir.exists():
        print(
            f"{Colors.RED}Error: Build directory not found at {build_dir}{Colors.END}"
        )
        return 1

    analyzer = BuildAnalyzer(build_dir)

    print_header("RospOS Build Report")

    print_file_sizes(analyzer)
    print_optimization_stats(analyzer)
    print_memory_layout(analyzer)
    print_instruction_types(analyzer)
    print_summary(analyzer)

    print(f"\n{Colors.GRAY}Report generated from: {build_dir.name}/{Colors.END}\n")

    return 0


if __name__ == "__main__":
    exit(main())
