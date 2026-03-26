import os
import re
from functools import partial

def replace_quotes(code):
    """Replace single quotes with double quotes intelligently, avoiding replacements in comments or strings."""
    result = []
    i = 0
    while i < len(code):
        # Check for line comments
        if code[i : i + 2] == "//":
            # Find end of line
            end = code.find("\n", i)
            if end == -1:
                result.append(code[i:])
                break
            result.append(code[i : end + 1])
            i = end + 1
            continue

        # Check for block comments
        if code[i : i + 2] == "/*":
            end = code.find("*/", i + 2)
            if end == -1:
                result.append(code[i:])
                break
            result.append(code[i : end + 2])
            i = end + 2
            continue

        # Check for double-quoted strings (keep as-is)
        if code[i] == '"':
            result.append('"')
            i += 1
            while i < len(code):
                if code[i] == "\\" and i + 1 < len(code):
                    result.append(code[i : i + 2])
                    i += 2
                elif code[i] == '"':
                    result.append('"')
                    i += 1
                    break
                else:
                    result.append(code[i])
                    i += 1
            continue

        # Check for single-quoted strings (convert to double quotes)
        if code[i] == "'":
            result.append('"')
            i += 1
            while i < len(code):
                if code[i] == "\\" and i + 1 < len(code):
                    result.append(code[i : i + 2])
                    i += 2
                elif code[i] == "'":
                    result.append('"')
                    i += 1
                    break
                else:
                    result.append(code[i])
                    i += 1
            continue

        result.append(code[i])
        i += 1

    return "".join(result)

included_files = set()

def include_replacer(match, current_file=None):
    filename = match.group(1)
    was_found=False
    try:
        pragma_many_pattern = re.compile(r"#pragma\s+many")
        current_dir = (
            os.path.dirname(os.path.abspath(current_file))
            if current_file
            else os.getcwd()
        )
        files = [
            current_dir,
            os.path.join(current_dir, "include"),
            os.path.join(current_dir, "lib"),
        ]
        for path in files:
            filepath = os.path.join(path, filename)
            if os.path.isfile(filepath):
                norm_path = os.path.normpath(filepath)
                if norm_path in included_files:
                    print(f"Skipping already included file: {norm_path}")
                    was_found=True
                    continue # This file has already been included, skip it.
                    # Note: this means that if a file is included multiple times, and a file with the same name exists
                    # in multiple search paths, the one in the root directory will be found first, then the next time it 
                    # is included, the one in `include` will be found, then the one in `lib`, and then any further
                    # includes will be skipped. This is a bit weird but it should work for now, especially as we should
                    # not have multiple files with the same name in different search paths.
                with open(filepath, "r") as f:
                    r=f.read()
                if not pragma_many_pattern.search(r):
                    # This file is not marked with #pragma many, so we should only include it once
                    # This is flipping the script compared to most C compilers, which include files multiple times by 
                    # default and require #pragma once or include guards to prevent multiple inclusions, but it really
                    # feels like the more intuitive behavior is to only include files once by default and require a
                    # special marker to allow multiple inclusions, so that's what we'll do.
                    included_files.add(norm_path)
                else:
                    r=pragma_many_pattern.sub("", r) 
                    # Remove the #pragma many directive from the included file, as it has already served its purpose of 
                    # allowing multiple inclusions of this file. The next time this file is included, this will be done
                    # again, which is fine. But as the rest of the pipeline isn't really set up to handle #pragma 
                    # directives in any way, we should remove it to avoid a compiler error about an unknown directive.
                return r
    except FileNotFoundError:
        print(f"Warning: Included file '{filename}' not found.")
        return ""
    if not was_found: # If we went through all search paths and didn't find the file, print a warning
        print(f"Warning: Included file '{filename}' not found in any of the search paths.")
    # If we did find the file but we got to this point, it was already included and a warning was printed, so we don't
    # need to print another warning here.
    return ""

def aug_replacer(match):
    var_name = match.group(1)
    operator = match.group(2)
    value = match.group(3)
    return f"{var_name} = {var_name} {operator} {value};"


def pp_replacer(match):
    var_name = match.group(1)
    operator = match.group(2)
    return f"{var_name} = {var_name} {operator[0]} 1;"

def void_return_replacer(match):
    return "return 0;"

def preprocess(code, current_file=None):
    include_pattern = re.compile(r"#include\s+<([^>]+)>")
    
    inc_replacer = partial(include_replacer, current_file=current_file)
    
    for _ in range(10):
        code = include_pattern.sub(inc_replacer, code)
    if include_pattern.search(code):
        print(
            "Warning: Maximum include depth reached. Some includes may not have been processed."
        )
    code = code.replace("\r\n", "\n").replace("\r", "\n")
    code = replace_quotes(code)
    aug_expr_pattern = re.compile(r"(\w+)\s*([\+\-\*/])=\s*([^;]+);")
    code = aug_expr_pattern.sub(aug_replacer, code)
    pp_pattern = re.compile(r"(\w+)\s*(\+\+|--);")
    code = pp_pattern.sub(pp_replacer, code)
    void_return_pattern = re.compile(r"\breturn\s*;") # Match 'return;' with optional whitespace
    # Replace 'return;' with 'return 0;' to ensure all functions return a value, as RospOS does not support void returns.
    
    code = void_return_pattern.sub(void_return_replacer, code)

    return code
