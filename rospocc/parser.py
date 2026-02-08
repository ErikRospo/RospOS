from copy import copy

from lark import Lark, Tree, Token

from preprocess import preprocess
import json

import emitter
import frontend
with open("./rosc.lark", "r") as f:
    grammar = f.read()


def tree_to_dict(node):
    """Recursively convert a Lark Tree/Token into a plain dict structure
    with 'node' and 'children' keys for easy inspection by the frontend.
    """
    if isinstance(node, Tree):
        return {'node': node.data, 'children': [tree_to_dict(c) for c in node.children]}
    if isinstance(node, Token):
        return {'token': str(node)}
    return node


with open("./first_test.rosc", "r") as f:
    code = f.read()
code = preprocess(code)
preprocessed = copy(code)
with open("./out/preprocessed_code.rosc", "w") as f:
    f.write(code)


def parse_code(code):
    # Use Earley parser to avoid LALR reduce/reduce conflicts
    parser = Lark(grammar, parser="earley", debug=False)
    return parser.parse(code)


ast_dict = None
try:
    tree = parse_code(code)
    ast_dict = tree_to_dict(tree)
    # write a textual representation for debugging
    try:
        with open("./out/ast.json", "w") as f:
            json.dump(ast_dict, f, indent=2)
    except Exception:
        pass
except Exception:
    ast_dict = None

# Convert preprocessed code or AST into the simple translation-unit for emitter
if ast_dict:
    tu = frontend.code_to_translation_unit(ast_dict)
else:
    tu = frontend.code_to_translation_unit(preprocessed)

out = './out/generated.ros'
emitter.emit_translation_unit(tu, out)
print('Emitted', out)
