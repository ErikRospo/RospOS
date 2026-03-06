import argparse
import re
from pathlib import Path

from debug_emitter import RoscDebugEmitter
import emitter
from lark import Lark
from preprocess import preprocess
from transformer import transform_to_translation_unit

# Resolve all filesystem paths relative to this file
HERE = Path(__file__).resolve().parent

with open(HERE / "rosc.lark", "r") as f:
    grammar = f.read()


# Use the transformer to convert Lark parse trees into a condensed dict
# structure consumed by the frontend/emitter.


# Command-line arguments (mirror compile.py behavior)
argp = argparse.ArgumentParser(description="Parse a .rosc file and emit .ros output")
argp.add_argument(
    "--input",
    type=str,
    required=True,
    help="Input source file to parse. Should be a .rosc file",
)
argp.add_argument(
    "--output",
    type=str,
    required=False,
    help="Output .ros file. If not provided, will use the input filename with .ros extension.",
)
args = argp.parse_args()

with open(args.input, "r") as f:
    code = f.read()

code = preprocess(code)

# Ensure output directory exists and write files there

if args.output is None:
    out = Path(args.input).with_suffix(".ros")
else:
    out = Path(args.output)

out_dir = out.parent
out_dir.mkdir(exist_ok=True)

preprocessed_name = f"{out.stem}_preprocessed.rosc"
with open(out_dir / preprocessed_name, "w") as f:
    f.write(code)


def parse_code(code):
    # Use Earley parser to avoid LALR reduce/reduce conflicts
    parser = Lark(grammar, parser="earley", debug=False)
    return parser.parse(code)


try:
    tree = parse_code(code)
except Exception as e:
    print("Error: parsing failed:", e)
    raise
ast_str = tree.pretty()
with open(out_dir / "ast.txt", "w") as f:
    f.write(ast_str)
# Convert parsed AST into the translation-unit for emitter (centralized)
tu = transform_to_translation_unit(tree)
emitter.emit_translation_unit(tu, str(out))

# Emit sidecar debug mapping for RospoAS consumption.
# This is line-based and captures the source text rospocc had during emission.
# NOTE: We use the preprocessed rosc file as the source, since that's what we actually compiled from
preprocessed_path = out_dir / preprocessed_name
rosc_lines = code.splitlines()
with open(out, "r", encoding="utf-8") as f:
    ros_lines = f.read().splitlines()

dbg = RoscDebugEmitter(source_file=preprocessed_path)

# Build a comprehensive map of the rosc source structure
rosc_func_map = {}  # func_name -> (start_line, end_line)
rosc_stmt_map = []  # list of (line_num, stmt_type, content) for meaningful statements

# Parse rosc to understand structure
in_func = None
func_start = None
for idx, line in enumerate(rosc_lines, start=1):
    stripped = line.strip()
    
    # Track function boundaries
    if stripped and not stripped.startswith("//"):
        # Function start: "type name(...)" or "type* name(...)"  or "type * name(...)"
        if "(" in stripped and ")" in stripped and not stripped.startswith("if") and not stripped.startswith("while") and not stripped.startswith("for"):
            # Could be function definition
            if idx < len(rosc_lines) and rosc_lines[idx].strip() == "{":
                # This is a function definition - extract the identifier immediately before '('
                # e.g., "int foo()" -> "foo", "char *bar()" -> "bar", "void *baz (x)" -> "baz"
                paren_pos = stripped.find('(')
                if paren_pos > 0:
                    before_paren = stripped[:paren_pos].strip()
                    # Extract last word (identifier) from before the paren
                    func_match = re.search(r'(\w+)\s*$', before_paren)
                    if func_match:
                        func_name = func_match.group(1)
                        if in_func:
                            rosc_func_map[in_func] = (func_start, idx - 1)
                        in_func = func_name
                        func_start = idx
        elif stripped == "}" and in_func:
            rosc_func_map[in_func] = (func_start, idx)
            in_func = None
        
        # Track important statements
        if in_func:
            # Variable declarations/assignments
            if "=" in stripped and not stripped.startswith("if") and not stripped.startswith("while"):
                rosc_stmt_map.append((idx, "assign", stripped))
            # Function calls
            elif "(" in stripped and ")" in stripped and not stripped.startswith("if") and not stripped.startswith("while"):
                rosc_stmt_map.append((idx, "call", stripped))
            # Control flow
            elif stripped.startswith("if") or stripped.startswith("while") or stripped.startswith("for"):
                rosc_stmt_map.append((idx, "control", stripped))
            # Return statements
            elif stripped.startswith("return"):
                rosc_stmt_map.append((idx, "return", stripped))
            # Struct member access (load/store)
            elif "." in stripped and ("=" in stripped or stripped.endswith(";")):
                rosc_stmt_map.append((idx, "member", stripped))

# Close last function
if in_func:
    rosc_func_map[in_func] = (func_start, len(rosc_lines))

def find_rosc_func_for_name(func_name):
    """Get rosc source line range for a function"""
    return rosc_func_map.get(func_name, None)

def find_best_stmt_in_range(start, end, comment, prev_line):
    """Find best matching statement in rosc range based on comment"""
    candidates = []
    for line_num, stmt_type, content in rosc_stmt_map:
        if start <= line_num <= end:
            score = 0
            content_lower = content.lower()
            comment_lower = comment.lower()
            
            # Extract meaningful tokens from comment
            var_match = re.search(r'(?:init|assign|zero init|load)\s+(\w+)', comment_lower)
            if var_match:
                var_name = var_match.group(1)
                if var_name in content_lower and stmt_type in ["assign", "member"]:
                    score += 50
            
            # Look for function calls
            if "call " in comment_lower:
                call_match = re.search(r'call\s+(\w+)', comment_lower)
                if call_match and call_match.group(1) in content_lower and stmt_type == "call":
                    score += 100
            
            # Struct member operations
            if "store " in comment_lower or "load " in comment_lower:
                member_match = re.search(r'(?:store|load)\s+\w+\.(\w+)', comment_lower)
                if member_match and member_match.group(1) in content_lower:
                    score += 60
            
            # Binops often stay on same line as previous
            if "binop" in comment_lower and line_num == prev_line:
                score += 30
            
            if score > 0:
                candidates.append((score, line_num, content))
    
    # Return best match or default to middle of range
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1], candidates[0][2]
    
    # Default: use statement closest to middle of range
    mid = (start + end) // 2
    for line_num, _, content in rosc_stmt_map:
        if start <= line_num <= end:
            return line_num, content
    
    return start, rosc_lines[start - 1] if start <= len(rosc_lines) else ""

# Process ros file and generate mappings
current_ros_func = None
current_rosc_range = None
last_rosc_line = 1
last_rosc_text = ""

for ros_idx, ros_line in enumerate(ros_lines, start=1):
    stripped = ros_line.strip()
    
    # Skip empty lines
    if not stripped or stripped.startswith("//"):
        continue
    
    # Handle directives
    if ros_line.startswith("."):
        if ".FUNC" in ros_line:
            # Extract function name
            parts = ros_line.split()
            if len(parts) >= 2:
                current_ros_func = parts[1].rstrip(":")
                current_rosc_range = find_rosc_func_for_name(current_ros_func)
                if current_rosc_range:
                    last_rosc_line = current_rosc_range[0]
                    last_rosc_text = rosc_lines[last_rosc_line - 1] if last_rosc_line <= len(rosc_lines) else ""
        dbg.add_mapping(ros_idx, preprocessed_path, last_rosc_line, last_rosc_text)
        continue
    
    # Handle labels
    if stripped.endswith(":"):
        dbg.add_mapping(ros_idx, preprocessed_path, last_rosc_line, last_rosc_text)
        continue
    
    # Handle actual instructions
    if current_rosc_range:
        # Try to map this instruction to a rosc statement
        if "//" in ros_line:
            comment = ros_line[ros_line.index("//"):]
            best_line, best_text = find_best_stmt_in_range(
                current_rosc_range[0], current_rosc_range[1],
                comment, last_rosc_line
            )
            if best_line:
                last_rosc_line = best_line
                last_rosc_text = best_text
    
    dbg.add_mapping(ros_idx, preprocessed_path, last_rosc_line, last_rosc_text)

sidecar_path = out.with_suffix(".rosc.debug")
dbg.write(sidecar_path)
print("Emitted", out)
print("Emitted", sidecar_path)
