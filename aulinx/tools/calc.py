"""Calculator tool — safe math evaluation."""

import ast
import math
import operator

from aulinx.tools.base import Tier, Tool

# Safe operators for math evaluation
_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_SAFE_FUNCS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "int": int,
    "float": float,
    "min": min,
    "max": max,
    "sum": sum,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "pi": math.pi,
    "e": math.e,
    "ceil": math.ceil,
    "floor": math.floor,
}


def _safe_eval(node):
    """Safely evaluate an AST math expression."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value}")
    elif isinstance(node, ast.BinOp):
        op = _SAFE_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op(_safe_eval(node.left), _safe_eval(node.right))
    elif isinstance(node, ast.UnaryOp):
        op = _SAFE_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op(_safe_eval(node.operand))
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _SAFE_FUNCS:
            func = _SAFE_FUNCS[node.func.id]
            args = [_safe_eval(a) for a in node.args]
            return func(*args)
        raise ValueError(f"Unsupported function: {ast.dump(node.func)}")
    elif isinstance(node, ast.Name):
        if node.id in _SAFE_FUNCS:
            val = _SAFE_FUNCS[node.id]
            if isinstance(val, (int, float)):
                return val
        raise ValueError(f"Unknown variable: {node.id}")
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


async def calculate(expression: str) -> dict:
    """Safely evaluate a math expression.

    Supports: +, -, *, /, //, %, **, sqrt, abs, round, sin, cos, tan, log, pi, e
    Examples: "15% of 3500" → "3500 * 0.15", "sqrt(144)", "2**10"
    """
    # Clean up common patterns
    expr = expression.strip()
    expr = expr.replace("^", "**")  # caret as power
    expr = expr.replace("×", "*").replace("÷", "/")

    # Handle percentage patterns: "15% of 3500" → "3500 * 0.15"
    import re
    pct_match = re.match(r"(\d+(?:\.\d+)?)%\s*(?:of)\s*(\d+(?:\.\d+)?)", expr)
    if pct_match:
        pct, base = float(pct_match.group(1)), float(pct_match.group(2))
        result = base * (pct / 100)
        return {"expression": expr, "result": result, "formatted": f"{pct}% of {base} = {result}"}

    try:
        tree = ast.parse(expr, mode="eval")
        result = _safe_eval(tree)
        return {"expression": expr, "result": result}
    except (ValueError, SyntaxError, TypeError, ZeroDivisionError) as e:
        return {"error": f"Cannot evaluate '{expr}': {e}"}


TOOLS = [
    Tool(
        name="calculate",
        description="Evaluate a math expression safely. Supports: +,-,*,/,**,sqrt,sin,cos,log,pi. Also '15% of 3500'.",
        fn=calculate,
        parameters={"expression": "string (math expression, e.g. '2**10', 'sqrt(144)', '15% of 3500')"},
        tier=Tier.OBSERVE,
    ),
]
