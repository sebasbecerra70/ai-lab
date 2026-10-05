"""Tool definitions: JSON-schema inputs, argument validation and safe implementations."""
from __future__ import annotations

import ast
import json
import operator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

_TYPES = {"string": str, "number": (int, float), "integer": int, "boolean": bool, "object": dict}


class ToolError(Exception):
    """Raised for bad arguments or tool failures; reported back to the model, not crashed on."""


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    fn: Callable[..., Any]

    def spec(self) -> dict:
        """The shape the Anthropic Messages API expects in `tools`."""
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}

    def validate(self, args: dict) -> None:
        props = self.input_schema.get("properties", {})
        for key in self.input_schema.get("required", []):
            if key not in args:
                raise ToolError(f"{self.name}: missing required argument '{key}'")
        for key, value in args.items():
            if key not in props:
                raise ToolError(f"{self.name}: unknown argument '{key}'")
            expected = _TYPES[props[key]["type"]]
            if isinstance(value, bool) and props[key]["type"] != "boolean":
                raise ToolError(f"{self.name}: '{key}' must be {props[key]['type']}")
            if not isinstance(value, expected):
                raise ToolError(f"{self.name}: '{key}' must be {props[key]['type']}")
            if "enum" in props[key] and value not in props[key]["enum"]:
                raise ToolError(f"{self.name}: '{key}' must be one of {props[key]['enum']}")

    def __call__(self, args: dict) -> Any:
        self.validate(args)
        return self.fn(**args)


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self.tools = {t.name: t for t in tools}

    def specs(self) -> list[dict]:
        return [t.spec() for t in self.tools.values()]

    def dispatch(self, name: str, args: dict) -> tuple[str, bool]:
        """Run a tool and return (content, is_error). Errors become text the model can react to."""
        tool = self.tools.get(name)
        if tool is None:
            return f"unknown tool '{name}'", True
        try:
            return json.dumps(tool(args)), False
        except ToolError as exc:
            return str(exc), True
        except Exception as exc:  # a tool bug should not kill the agent loop
            return f"{name} failed: {type(exc).__name__}: {exc}", True


# --- calculator: arithmetic only, via a whitelisted AST walk (never eval) ---
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        if isinstance(node.op, ast.Pow) and abs(_eval(node.right)) > 10:
            raise ToolError("calculator: exponent too large")
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ToolError(f"calculator: unsupported expression element {type(node).__name__}")


def calculate(expression: str) -> float:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolError(f"calculator: cannot parse '{expression}'") from exc
    try:
        return round(_eval(tree), 6)
    except ZeroDivisionError as exc:
        raise ToolError("calculator: division by zero") from exc


# --- unit conversion: everything goes through an SI base per dimension ---
_UNITS = {
    "power": {"W": 1.0, "kW": 1e3, "MW": 1e6, "BTU/h": 0.29307107, "ton": 3516.8528},
    "energy": {"kWh": 1.0, "MWh": 1e3, "J": 1 / 3.6e6},
    "volume": {"L": 1.0, "gal": 3.785411784, "m3": 1000.0},
    "temperature": {"C": None, "F": None, "K": None},
}


def convert_units(value: float, from_unit: str, to_unit: str) -> float:
    for dim, table in _UNITS.items():
        if from_unit in table and to_unit in table:
            if dim == "temperature":
                c = {"C": value, "F": (value - 32) * 5 / 9, "K": value - 273.15}[from_unit]
                out = {"C": c, "F": c * 9 / 5 + 32, "K": c + 273.15}[to_unit]
            else:
                out = value * table[from_unit] / table[to_unit]
            return round(out, 4)
    raise ToolError(f"convert_units: cannot convert {from_unit} to {to_unit}")


def make_lookup(facts: dict[str, float]) -> Callable[[str], Any]:
    def lookup(key: str) -> Any:
        if key in facts:
            return {"key": key, "value": facts[key]}
        close = sorted(k for k in facts if key.split(".")[0] in k)[:5]
        raise ToolError(f"lookup: no fact '{key}'. Similar keys: {close or sorted(facts)[:5]}")
    return lookup


def default_registry(facts_path: str | Path) -> ToolRegistry:
    facts = json.loads(Path(facts_path).read_text())
    return ToolRegistry([
        Tool("calculator", "Evaluate an arithmetic expression (+ - * / ** % and parentheses).",
             {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
             calculate),
        Tool("lookup", "Look up a site metric by key, e.g. 'hall_a.it_load_kw'. Keys: " + ", ".join(sorted(facts)),
             {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
             make_lookup(facts)),
        Tool("convert_units", "Convert a value between units of power, energy, volume or temperature.",
             {"type": "object",
              "properties": {"value": {"type": "number"}, "from_unit": {"type": "string"}, "to_unit": {"type": "string"}},
              "required": ["value", "from_unit", "to_unit"]},
             convert_units),
    ])
