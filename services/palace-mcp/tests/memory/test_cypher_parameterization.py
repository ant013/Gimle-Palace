import ast
import inspect

from palace_mcp.memory import cypher

_QUERY_CONSTANTS = [
    name for name, val in vars(cypher).items()
    if isinstance(val, str) and name.isupper() and "MATCH" in val
]


def test_no_python_format_interpolation() -> None:
    """Query constants must not use .format() or f-string interpolation."""
    src = inspect.getsource(cypher)
    for name in _QUERY_CONSTANTS:
        assert f"{name}.format" not in src, f"{name} uses .format()"
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id.isupper() for t in node.targets)
            and isinstance(node.value, ast.JoinedStr)
        ):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            raise AssertionError(f"Query constant(s) {names} use f-string")


def test_queries_use_dollar_params() -> None:
    """All user-value slots in query constants must use $name parameters."""
    for name in _QUERY_CONSTANTS:
        q = getattr(cypher, name)
        # Static queries with no params (e.g. ENTITY_COUNTS) are OK
        if "$" not in q and "%" in q:
            raise AssertionError(f"{name} uses %-format instead of $param")
