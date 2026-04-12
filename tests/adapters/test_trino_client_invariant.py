"""TRN-05 architectural invariant test: every public TrinoClient method that
takes a ``sql: str`` parameter must call ``self._classifier.assert_read_only(sql)``
as its first executable statement.

This test introspects ``client.py`` via the ``ast`` module so it acts as a
compile-time regression guard — any refactor that accidentally removes or
relocates the classifier call will break CI.

Note: ``fetch_stats`` and ``fetch_iceberg_metadata`` take catalog/schema/table
params and build SQL internally — they still call assert_read_only on the
constructed SQL but are not in the "sql: str param" category tested here.
``cancel_query`` and ``probe_capabilities`` are fully classifier-exempt.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CLIENT_SRC = (
    Path(__file__).parent.parent.parent
    / "src/mcp_trino_optimizer/adapters/trino/client.py"
)

_AnyFuncDef = ast.FunctionDef | ast.AsyncFunctionDef


def _parse_client() -> ast.Module:
    """Parse client.py and return its AST Module node."""
    return ast.parse(CLIENT_SRC.read_text())


def _get_public_methods(tree: ast.Module) -> list[_AnyFuncDef]:
    """Return all public (non-underscore) methods of TrinoClient (sync + async)."""
    methods: list[_AnyFuncDef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "TrinoClient":
            for item in node.body:
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not item.name.startswith("_")
                ):
                    methods.append(item)
    return methods


def _has_sql_str_param(method: _AnyFuncDef) -> bool:
    """Return True if the method has a parameter named ``sql`` annotated as ``str``."""
    for arg in method.args.args:
        if arg.arg == "sql":
            ann = arg.annotation
            if isinstance(ann, ast.Name) and ann.id == "str":
                return True
    return False


def _first_executable_stmt(method: _AnyFuncDef) -> ast.stmt | None:
    """Return the first non-docstring statement in the method body."""
    body = method.body
    if not body:
        return None
    # Skip a leading docstring constant
    if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        return body[1] if len(body) > 1 else None
    return body[0]


def _is_assert_read_only_call(stmt: ast.stmt | None) -> bool:
    """Return True if *stmt* is ``self._classifier.assert_read_only(sql)``."""
    if stmt is None:
        return False
    if not isinstance(stmt, ast.Expr):
        return False
    call = stmt.value
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    # func must be an attribute access: self._classifier.assert_read_only
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr != "assert_read_only":
        return False
    # The object must itself be an attribute: self._classifier
    obj = func.value
    if not isinstance(obj, ast.Attribute):
        return False
    if obj.attr != "_classifier":
        return False
    if not isinstance(obj.value, ast.Name) or obj.value.id != "self":
        return False
    # The sole positional arg must be ``sql``
    if len(call.args) != 1:
        return False
    arg = call.args[0]
    if not isinstance(arg, ast.Name) or arg.id != "sql":
        return False
    return True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_client_py_exists() -> None:
    """client.py must exist before this invariant test can run."""
    assert CLIENT_SRC.exists(), f"client.py not found at {CLIENT_SRC}"


def test_trino_client_class_exists() -> None:
    """TrinoClient class must be defined in client.py."""
    tree = _parse_client()
    class_names = [
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    ]
    assert "TrinoClient" in class_names, "TrinoClient class not found in client.py"


@pytest.mark.parametrize(
    "method_name",
    [
        # Methods that take sql: str directly — must call assert_read_only(sql) first
        "fetch_plan",
        "fetch_analyze_plan",
        "fetch_distributed_plan",
        "fetch_system_runtime",
    ],
)
def test_sql_taking_method_calls_classifier_first(method_name: str) -> None:
    """Every public method with a sql: str param has assert_read_only(sql) as first line."""
    tree = _parse_client()
    methods = {m.name: m for m in _get_public_methods(tree)}

    assert method_name in methods, (
        f"Method '{method_name}' not found in TrinoClient. "
        f"Available public methods: {list(methods)}"
    )

    method = methods[method_name]
    assert _has_sql_str_param(method), (
        f"Method '{method_name}' does not have a 'sql: str' parameter."
    )

    first_stmt = _first_executable_stmt(method)
    assert _is_assert_read_only_call(first_stmt), (
        f"Method '{method_name}' does not call self._classifier.assert_read_only(sql) "
        f"as its first executable statement. "
        f"Got: {ast.dump(first_stmt) if first_stmt else 'None'}"
    )


def test_cancel_query_has_no_sql_param() -> None:
    """cancel_query must NOT have a ``sql`` parameter — it is classifier-exempt."""
    tree = _parse_client()
    methods = {m.name: m for m in _get_public_methods(tree)}

    assert "cancel_query" in methods, "cancel_query not found in TrinoClient"
    assert not _has_sql_str_param(methods["cancel_query"]), (
        "cancel_query should not have a sql parameter"
    )


def test_probe_capabilities_has_no_sql_param() -> None:
    """probe_capabilities must NOT have a ``sql`` parameter — it is classifier-exempt."""
    tree = _parse_client()
    methods = {m.name: m for m in _get_public_methods(tree)}

    assert "probe_capabilities" in methods, "probe_capabilities not found in TrinoClient"
    assert not _has_sql_str_param(methods["probe_capabilities"]), (
        "probe_capabilities should not have a sql parameter"
    )


def test_all_required_methods_present() -> None:
    """All 8 required public methods are present in TrinoClient."""
    tree = _parse_client()
    methods = {m.name for m in _get_public_methods(tree)}

    required = {
        "fetch_plan",
        "fetch_analyze_plan",
        "fetch_distributed_plan",
        "fetch_stats",
        "fetch_iceberg_metadata",
        "fetch_system_runtime",
        "cancel_query",
        "probe_capabilities",
    }
    missing = required - methods
    assert not missing, f"Missing required public methods: {missing}"


def test_sql_str_param_methods_enumerated() -> None:
    """Exactly the expected set of methods have a sql: str parameter."""
    tree = _parse_client()
    methods = _get_public_methods(tree)

    expected_sql_methods = {
        "fetch_plan",
        "fetch_analyze_plan",
        "fetch_distributed_plan",
        "fetch_system_runtime",
    }

    actual_sql_methods = {m.name for m in methods if _has_sql_str_param(m)}
    assert expected_sql_methods == actual_sql_methods, (
        f"Unexpected public sql: str-taking methods. "
        f"Expected: {expected_sql_methods}, Got: {actual_sql_methods}"
    )
