"""What a learner's brain code may contain, and the small set of built-ins it runs with.

Used by Fight Lab (fight_brain.py, brain_worker.py): the same rules as Robot Lab. Uses only the
standard library, so the brain worker process can load it without the game engine.

These checks catch honest mistakes and block the obvious ways to reach files or the internet. On the class
server, brains also run in their own process with memory and time limits (brain_worker.py), because no list
of rules can stop every way a brain could hog the computer.
"""
import ast
import math
import random

MAX_LINES_PER_TICK = 5000  # a brain that runs longer than this is stuck in a loop
MAX_MS_PER_TICK = 20
MAX_SOURCE = 20000         # characters

BANNED_NAMES = {"eval", "exec", "open", "compile", "__import__", "globals", "locals", "vars", "getattr",
                "setattr", "delattr", "input", "breakpoint", "exit", "quit", "help", "memoryview",
                "type", "object", "super", "classmethod", "staticmethod", "property", "dir", "id"}
ALLOWED_MODULES = {"math", "random"}


class RuleError(Exception):
    pass


def _capped_range(*a):
    r = range(*a)
    if len(r) > 10000:
        raise ValueError("range() is too big for a fighter brain (max 10,000)")
    return r


SAFE_BUILTINS = {
    "abs": abs, "min": min, "max": max, "round": round, "len": len, "range": _capped_range, "sum": sum,
    "sorted": sorted, "enumerate": enumerate, "zip": zip, "int": int, "float": float, "bool": bool,
    "str": str, "list": list, "dict": dict, "tuple": tuple, "isinstance": isinstance, "any": any,
    "all": all, "pow": pow, "divmod": divmod, "reversed": reversed, "map": map, "filter": filter,
    "Exception": Exception, "ValueError": ValueError, "ZeroDivisionError": ZeroDivisionError,
}


def safe_import(name, *a, **k):
    if name not in ALLOWED_MODULES:
        raise ImportError(f"only math and random can be imported, not {name}")
    return {"math": math, "random": random}[name]


def check_code(tree):
    """Raises RuleError (with a line number) if the file has anything a fighter brain never needs."""
    for node in tree.body:  # what is allowed at the top of the file
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # a docstring or comment string
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
            if any(n not in ALLOWED_MODULES for n in names):
                raise RuleError(f"line {node.lineno}: only 'import math' and 'import random' are allowed")
            continue
        if isinstance(node, ast.FunctionDef):
            continue
        if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] == ["FIGHTER"]:
            continue
        raise RuleError(f"line {node.lineno}: only functions and 'import math' "
                        "may be at the top of the file")
    for node in ast.walk(tree):  # things a brain never needs
        if isinstance(node, ast.Name) and (node.id in BANNED_NAMES or node.id.startswith("__")):
            raise RuleError(f"line {node.lineno}: '{node.id}' isn't allowed in a fighter brain")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise RuleError(f"line {node.lineno}: names starting with _ aren't allowed")
        if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef, ast.Await, ast.Yield, ast.YieldFrom)):
            raise RuleError(f"line {node.lineno}: classes, async and yield aren't needed here")


def describe(e, fname):
    """An error as a learner can act on it: the line in their file and what went wrong."""
    tb, line = e.__traceback__, None
    while tb:
        if tb.tb_frame.f_code.co_filename == fname:
            line = tb.tb_lineno
        tb = tb.tb_next
    where = f"line {line}: " if line else ""
    return f"{where}{type(e).__name__}: {e}"
