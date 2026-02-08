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


try:
    tree = parse_code(code)
except Exception as e:
    print("Error: parsing failed:", e)
    raise

ast_dict = tree_to_dict(tree)
# write a textual representation for debugging
with open("./out/ast.json", "w") as f:
    json.dump(ast_dict, f, indent=2)

# Convert parsed AST into the translation-unit for emitter (no regex fallback)
tu = frontend.code_to_translation_unit(ast_dict)

out = './out/generated.ros'
emitter.emit_translation_unit(tu, out)
print('Emitted', out)
