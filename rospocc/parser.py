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
rosc_func_map = {}  # func_name -> (start_line, end_line, body_lines)
rosc_stmt_map = {}  # line_num -> (stmt_type, content, keywords)

# Parse rosc to understand structure - identify functions and meaningful statements
in_func = None
func_start = None
brace_depth = 0

for idx, line in enumerate(rosc_lines, start=1):
    stripped = line.strip()
    
    if not stripped or stripped.startswith("//"):
        continue
        
    # Track brace depth
    brace_depth += stripped.count("{") - stripped.count("}")
    
    # Function signature detection: type name(...) possibly followed by {
    if "(" in stripped and ")" in stripped and brace_depth <= 1:
        # Check if next non-empty line is { or if this line ends with {
        is_func_def = False
        if stripped.endswith("{"):
            is_func_def = True
        elif idx < len(rosc_lines):
            next_line = rosc_lines[idx].strip()
            if next_line ==  "{":
                is_func_def = True
        
        if is_func_def:
            # Extract function name
            paren_pos = stripped.find('(')
            if paren_pos > 0:
                before_paren = stripped[:paren_pos].strip()
                func_match = re.search(r'(\w+)\s*$', before_paren)
                if func_match:
                    func_name = func_match.group(1)
                    if in_func:  # Close previous function
                        body_lines = [i for i in range(func_start, idx) if i in rosc_stmt_map]
                        rosc_func_map[in_func] = (func_start, idx - 1, body_lines)
                    in_func = func_name
                    func_start = idx
    
    # Close function on brace depth return to 0
    if in_func and brace_depth == 0 and stripped == "}":
        body_lines = [i for i in range(func_start, idx + 1) if i in rosc_stmt_map]
        rosc_func_map[in_func] = (func_start, idx, body_lines)
        in_func = None
    
    # Track meaningful statements (only inside functions)
    if in_func and brace_depth > 0:
        keywords = set()
        
        # Extract variable names, function names, member names
        var_matches = re.findall(r'\b([a-z_]\w*)\b', stripped)
        keywords.update(var_matches)
        
        # Classify statement type
        stmt_type = "unknown"
        if stripped.startswith("return"):
            stmt_type = "return"
        elif stripped.startswith("if "):
            stmt_type = "if"
        elif stripped.startswith("while "):
            stmt_type = "while"
        elif stripped.startswith("for "):
            stmt_type = "for"
        elif "(" in stripped and ")" in stripped and "=" not in stripped:
            stmt_type = "call"
            # Extract function name
            call_match = re.search(r'(\w+)\s*\(', stripped)
            if call_match:
                keywords.add(call_match.group(1))
        elif "=" in stripped:
            stmt_type = "assign"
            # Extract LHS variable/member
            eq_pos = stripped.find("=")
            lhs = stripped[:eq_pos].strip()
            if "." in lhs or "->" in lhs:
                stmt_type = "member_store"
            # Extract variable being assigned
            var_match = re.search(r'(\w+)\s*(?:\.|\[|=)', lhs)
            if var_match:
                keywords.add(var_match.group(1))
        
        rosc_stmt_map[idx] = (stmt_type, stripped, keywords)

# Close last function
if in_func:
    body_lines = [i for i in range(func_start, len(rosc_lines) + 1) if i in rosc_stmt_map]
    rosc_func_map[in_func] = (func_start, len(rosc_lines), body_lines)

print(f"Parsed rosc: {len(rosc_func_map)} functions, {len(rosc_stmt_map)} statements")

# Parse ros file structure
ros_func_map = {}  # func_name -> (start_line, end_line)
ros_blocks = []  # (start_line, end_line, block_type, keywords)

current_ros_func = None
ros_func_start = None
block_start = None
block_keywords = set()

for idx, line in enumerate(ros_lines, start=1):
    stripped = line.strip()
    
    # Function definitions: .FUNC name:
    if stripped.startswith(".FUNC "):
        if current_ros_func:
            ros_func_map[current_ros_func] = (ros_func_start, idx - 1)
        func_name = stripped[6:].rstrip(":")
        current_ros_func = func_name
        ros_func_start = idx
        block_start = None
        continue
    
    # Track blocks of contiguous instructions
    if stripped and not stripped.startswith("//") and not stripped.startswith(".") and not stripped.endswith(":"):
        # This is an instruction or directive
        if block_start is None:
            block_start = idx
            block_keywords = set()
        
        # Extract keywords from comments
        comment_match = re.search(r'//\s*(.+)', line)
        if comment_match:
            comment = comment_match.group(1)
            # Extract variable names, function names from comments
            tokens = re.findall(r'\b([a-z_]\w*)\b', comment.lower())
            block_keywords.update(tokens)
        
        # Extract register usage and labels
        label_matches = re.findall(r'\b(str_\d+|[a-z_]\w+_buf\d+|WHILE\d+|IF_END\d+)\b', line)
        block_keywords.update(label_matches)
    
    elif block_start is not None:
        # End of block
        ros_blocks.append((block_start, idx - 1, "code_block", block_keywords))
        block_start = None

# Close last block and function
if block_start is not None:
    ros_blocks.append((block_start, len(ros_lines), "code_block", block_keywords))
if current_ros_func:
    ros_func_map[current_ros_func] = (ros_func_start, len(ros_lines))

print(f"Parsed ros: {len(ros_func_map)} functions, {len(ros_blocks)} code blocks")

# Build mapping from ros lines to rosc lines
def find_best_rosc_line(ros_line_num, ros_func_name, ros_comment, prev_mapping):
    """Find best matching rosc line for a ros line"""
    
    # If we're in a known function, search within that function's rosc range
    if ros_func_name and ros_func_name in rosc_func_map:
        func_start, func_end, body_lines = rosc_func_map[ros_func_name]
        
        # Extract  keywords from comment
        keywords = set()
        if ros_comment:
            # Variable names
            var_matches = re.findall(r'(?:init|assign|load|store|zero init|deref)\s+(\w+)', ros_comment)
            keywords.update(var_matches)
            
            # Function call
            call_match = re.search(r'call\s+(\w+)', ros_comment)
            if call_match:
                keywords.add(call_match.group(1))
            
            # Struct members
            member_match = re.search(r'(?:load|store)\s+\w+\.(\w+)', ros_comment)
            if member_match:
                keywords.add(member_match.group(1))
        
        # Score each statement in the function body
        best_score = 0
        best_line = func_start
        best_text = rosc_lines[func_start - 1] if func_start <= len(rosc_lines) else ""
        
        for stmt_line in body_lines:
            stmt_type, stmt_text, stmt_keywords = rosc_stmt_map[stmt_line]
            score = 0
            
            # Keyword overlap
            overlap = keywords & stmt_keywords
            score += len(overlap) * 20
            
            # Prefer lines close to previous mapping (locality)
            if prev_mapping:
                distance = abs(stmt_line - prev_mapping)
                score -= distance * 0.5
            
            # Type-specific matching
            if ros_comment:
                if "call " in ros_comment.lower() and stmt_type == "call":
                    score += 30
                if ("init " in ros_comment.lower() or "assign " in ros_comment.lower()) and stmt_type == "assign":
                    score += 15
                if ("store " in ros_comment.lower() or "load " in ros_comment.lower()) and stmt_type == "member_store":
                    score += 25
                if "return" in ros_comment.lower() and stmt_type == "return":
                    score += 50
            
            if score > best_score:
                best_score = score
                best_line = stmt_line
                best_text = stmt_text
        
        # If we found a good match, use it; otherwise default to function signature
        if best_score > 10:
            return best_line, best_text
        else:
            return func_start, rosc_lines[func_start - 1] if func_start <= len(rosc_lines) else ""
    
    # Fallback: return line 1
    return 1, rosc_lines[0] if rosc_lines else ""

# Generate mappings
current_ros_func = None
prev_rosc_line = 1
current_src_line = None  # Track current source line from markers

for ros_idx, ros_line in enumerate(ros_lines, start=1):
    stripped = ros_line.strip()
    
    # Track current function context
    if stripped.startswith(".FUNC "):
        func_name = stripped[6:].rstrip(":")
        current_ros_func = func_name
        current_src_line = None  # Reset on function boundaries
    
    # Look for source line markers
    src_marker = re.search(r'// @SRC_LINE:(\d+)', ros_line)
    if src_marker:
        current_src_line = int(src_marker.group(1))
        # Don't create mapping for the marker line itself, it's metadata
        continue
    
    # If we have an active source line from a marker, use it
    if current_src_line is not None and current_src_line <= len(rosc_lines):
        rosc_line = current_src_line
        rosc_text = rosc_lines[rosc_line - 1]
    else:
        # Extract comment if present for heuristic matching
        comment = ""
        comment_match = re.search(r'//\s*(.+)', ros_line)
        if comment_match:
            comment = comment_match.group(1).strip()
        
        # Find best rosc line for this ros line using heuristics
        rosc_line, rosc_text = find_best_rosc_line(ros_idx, current_ros_func, comment, prev_rosc_line)
    
    # Add mapping
    dbg.add_mapping(ros_idx, preprocessed_path, rosc_line, rosc_text)
    prev_rosc_line = rosc_line

# Write sidecar
sidecar_path = out.with_suffix(".rosc.debug")
dbg.write(sidecar_path)
print(f"Emitted {out}")
print(f"Emitted {sidecar_path}")
