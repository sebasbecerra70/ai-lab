"""Tools the executor can call. All are deterministic and side-effect free."""
from __future__ import annotations

import ast
import math
import operator
import re

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg}
_FUNCS = {"ceil": math.ceil, "floor": math.floor, "min": min, "max": max, "round": round}


class ToolError(Exception):
    pass


def safe_eval(expr: str, variables: dict[str, float] | None = None) -> float:
    """Arithmetic only: numbers, + - * / **, ceil/floor/min/max/round, and named variables."""
    variables = variables or {}

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise ToolError(f"unknown variable '{node.id}'")
            return variables[node.id]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
            return _FUNCS[node.func.id](*[ev(a) for a in node.args])
        raise ToolError(f"disallowed expression: {ast.dump(node)[:40]}")

    try:
        return ev(ast.parse(expr, mode="eval"))
    except SyntaxError as e:
        raise ToolError(f"bad expression '{expr}'") from e
    except ZeroDivisionError as e:
        raise ToolError("division by zero") from e


class Toolbox:
    def __init__(self, facts: dict[str, float]):
        self.facts = facts

    def lookup(self, key: str) -> float:
        if key not in self.facts:
            raise ToolError(f"no fact named '{key}'")
        return self.facts[key]

    def calc(self, expr: str, variables: dict[str, float]) -> float:
        return safe_eval(expr, {**self.facts, **variables})

    @staticmethod
    def referenced_names(expr: str) -> set[str]:
        return set(re.findall(r"[A-Za-z_]\w*", expr)) - set(_FUNCS)
