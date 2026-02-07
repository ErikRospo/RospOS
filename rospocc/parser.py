from lark import Lark, Transformer, v_args
from preprocess import preprocess
with open('./rosc.lark', 'r') as f:
    grammar = f.read()

class ASTTransformer(Transformer):
    pass

def parse_code(code):
    parser = Lark(grammar, parser='lalr', transformer=ASTTransformer(), debug=True)
    return parser.parse(code)

with open('./first_test.rosc', 'r') as f:
    code = f.read()
code = preprocess(code)
with open("./out/preprocessed_code.rosc", 'w') as f:
    f.write(code)
ast = parse_code(code)
with open("./out/ast.txt", 'w') as f:
    f.write(ast.pretty())