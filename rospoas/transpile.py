import ast
import os
import sys
from typing import List, Tuple


with open("./test.py","rt") as f:
    tree = ast.parse(f.read(), filename="./test.py")
    
    
functions=[]
class FunctionVisitor(ast.NodeVisitor):
    def visit_FunctionDef(self, node: ast.FunctionDef):
        functions.append(node)
        self.generic_visit(node)
FunctionVisitor().visit(tree)


for function in functions:
    print(f"Function name: {function.name}")
    args = [arg.arg for arg in function.args.args]
    print(f"Arguments: {args}")
    returns = ast.unparse(function.returns) if function.returns else "None"
    print(f"Returns: {returns}")
    print()