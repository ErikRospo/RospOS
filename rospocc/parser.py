import re
from lark import Lark, Transformer, v_args
with open('./rosc.lark', 'r') as f:
    grammar = f.read()

class ASTTransformer(Transformer):
    pass

def parse_code(code):
    parser = Lark(grammar, parser='lalr', transformer=ASTTransformer())
    return parser.parse(code)

def preprocess(code):
    code = code.replace('\r\n', '\n').replace('\r', '\n')
    
    include_pattern = re.compile(r'#include\s+"([^"]+)"')
    def include_replacer(match):
        filename = match.group(1)
        try:
            with open(filename, 'r') as f:
                return f.read()
        except FileNotFoundError:
            print(f"Warning: Included file '{filename}' not found.")
            return ''
    for _ in range(10):
        code = include_pattern.sub(include_replacer, code)
    if include_pattern.search(code):
        print("Warning: Maximum include depth reached. Some includes may not have been processed.")
    return code
with open('./first_test.rosc', 'r') as f:
    code = f.read()
code = preprocess(code)
ast = parse_code(code)
with open("./out/ast.txt", 'w') as f:
    f.write(ast.pretty())