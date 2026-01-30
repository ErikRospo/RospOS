import lark
with open("./rospoas.lark", "r") as f:
    rospoas_grammar=f.read()
    
parser = lark.Lark(rospoas_grammar, start='program', parser='lalr')

with open("./test.ros","r") as f:
    source_code=f.read()
parse_tree = parser.parse(source_code)
print(parse_tree.pretty())