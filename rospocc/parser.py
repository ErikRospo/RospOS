from copy import copy
from lark import Lark, Transformer, v_args
from preprocess import preprocess
with open('./rosc.lark', 'r') as f:
    grammar = f.read()

class ASTTransformer(Transformer):
    pass

with open('./first_test.rosc', 'r') as f:
    code = f.read()
code = preprocess(code)
preprocessed = copy(code)
with open("./out/preprocessed_code.rosc", 'w') as f:
    f.write(code)

def parse_code(code):
    # Use Earley parser to avoid LALR reduce/reduce conflicts
    parser = Lark(grammar, parser='earley', debug=True)
    return parser.parse(code)
ast = parse_code(code)
with open("./out/ast.txt", 'w') as f:
    f.write(ast.pretty())