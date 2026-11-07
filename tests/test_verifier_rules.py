"""The sandbox's static rules for verifier/, re-checked here: pure standard-library imports, no forbidden calls."""

from __future__ import annotations

import ast
from pathlib import Path

ALLOWED = {
    "__future__", "collections", "dataclasses", "decimal", "difflib", "enum", "fractions", "functools",
    "hashlib", "itertools", "json", "math", "operator", "pathlib", "re", "statistics", "string", "textwrap",
    "typing", "unicodedata", "contract",
}
FORBIDDEN_NAMES = {
    "__import__", "breakpoint", "compile", "delattr", "eval", "exec", "getattr", "globals", "input", "locals",
    "open", "setattr", "vars",
}
FORBIDDEN_ATTRIBUTES = {
    "builtins", "chmod", "hardlink_to", "mkdir", "os", "rename", "rmdir", "shutil", "socket", "subprocess",
    "symlink_to", "sys", "touch", "unlink", "write_bytes", "write_text",
}
VERIFIER = Path(__file__).resolve().parent.parent / "verifier"


def test_verifier_holds_only_python_files() -> None:
    assert {path.suffix for path in VERIFIER.iterdir() if path.is_file()} == {".py"}


def test_verifier_obeys_the_sandbox_rules() -> None:
    problems = []
    for module in VERIFIER.rglob("*.py"):
        for node in ast.walk(ast.parse(module.read_text())):
            if isinstance(node, ast.Import):
                problems += [a.name for a in node.names if a.name.split(".")[0] not in ALLOWED]
            if isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").split(".")[0] not in ALLOWED:
                problems.append(node.module)
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
                problems.append(f"{module.name}: {node.id}")
            if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr in FORBIDDEN_ATTRIBUTES):
                problems.append(f"{module.name}: .{node.attr}")
    assert problems == []
