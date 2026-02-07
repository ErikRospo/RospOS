import os
import re
def replace_quotes(code):
        """Replace single quotes with double quotes intelligently, avoiding replacements in comments or strings."""
        result = []
        i = 0
        while i < len(code):
            # Check for line comments
            if code[i:i+2] == '//':
                # Find end of line
                end = code.find('\n', i)
                if end == -1:
                    result.append(code[i:])
                    break
                result.append(code[i:end+1])
                i = end + 1
                continue
            
            # Check for block comments
            if code[i:i+2] == '/*':
                end = code.find('*/', i+2)
                if end == -1:
                    result.append(code[i:])
                    break
                result.append(code[i:end+2])
                i = end + 2
                continue
            
            # Check for double-quoted strings (keep as-is)
            if code[i] == '"':
                result.append('"')
                i += 1
                while i < len(code):
                    if code[i] == '\\' and i + 1 < len(code):
                        result.append(code[i:i+2])
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
                    if code[i] == '\\' and i + 1 < len(code):
                        result.append(code[i:i+2])
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
        
        return ''.join(result)
def include_replacer(match):
        filename = match.group(1)
        try:
            files=['./', './include/', "./lib/"]
            for f in files:
                if os.path.isfile(f + filename):
                    with open(f + filename, 'r') as f:
                        return f.read()
        except FileNotFoundError:
            print(f"Warning: Included file '{filename}' not found.")
            return ''
        print(f"Warning: Included file '{filename}' not found in any of the search paths.")
        return '' # Return empty string if file not found
def aug_replacer(match):
    var_name = match.group(1)
    operator = match.group(2)
    value = match.group(3)
    return f"{var_name} = {var_name} {operator} {value};"
def pp_replacer(match):
    var_name = match.group(1)
    operator = match.group(2)
    return f"{var_name} = {var_name} {operator} 1;"
def preprocess(code):
    include_pattern = re.compile(r'#include\s+<([^>]+)>')
    for _ in range(10):
        code = include_pattern.sub(include_replacer, code)
    if include_pattern.search(code):
        print("Warning: Maximum include depth reached. Some includes may not have been processed.")
    code = code.replace('\r\n', '\n').replace('\r', '\n')
    code = replace_quotes(code)
    aug_expr_pattern = re.compile(r'(\w+)\s*([\+\-\*/])=\s*([^;]+);')
    code = aug_expr_pattern.sub(aug_replacer, code)
    
    return code