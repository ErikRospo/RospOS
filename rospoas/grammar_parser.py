from lark import Lark

with open("./rospoas.lark", "r") as f:
    rospoas_grammar = f.read()

parser = Lark(rospoas_grammar, start="program", parser="lalr")

def parse_source(source_code):
    return parser.parse(source_code)