from lark import Lark
from pathlib import Path

grammar_file = Path(__file__).parent / "rospoas.lark"
with open(grammar_file, "r") as f:
    rospoas_grammar = f.read()

parser = Lark(rospoas_grammar, start="program", parser="lalr")

def parse_source(source_code):
    return parser.parse(source_code)