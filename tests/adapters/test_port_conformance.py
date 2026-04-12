"""Port conformance tests.

Validates that OfflinePlanSource satisfies the PlanSource Protocol via
isinstance() checks (enabled by @runtime_checkable) and that no adapter
coupling exists in the ports package.
"""

from __future__ import annotations

import ast
from pathlib import Path


def test_offline_plan_source_satisfies_plan_source_protocol() -> None:
    """isinstance(OfflinePlanSource(), PlanSource) must be True."""
    from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource
    from mcp_trino_optimizer.ports import PlanSource

    source = OfflinePlanSource()
    assert isinstance(source, PlanSource), "OfflinePlanSource does not satisfy the PlanSource Protocol"


def test_offline_plan_source_has_all_plan_source_methods() -> None:
    """OfflinePlanSource must have fetch_plan, fetch_analyze_plan, fetch_distributed_plan."""
    from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

    source = OfflinePlanSource()
    assert callable(getattr(source, "fetch_plan", None))
    assert callable(getattr(source, "fetch_analyze_plan", None))
    assert callable(getattr(source, "fetch_distributed_plan", None))


def test_ports_package_has_no_adapter_imports() -> None:
    """All .py files under ports/ must contain zero imports from adapters."""
    ports_dir = Path(__file__).parent.parent.parent / "src" / "mcp_trino_optimizer" / "ports"
    assert ports_dir.is_dir(), f"ports/ directory not found at {ports_dir}"

    violations: list[str] = []
    for py_file in sorted(ports_dir.glob("*.py")):
        source = py_file.read_text()
        tree = ast.parse(source, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "adapters" in node.module:
                    violations.append(f"{py_file.name} line {node.lineno}: imports from '{node.module}'")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if "adapters" in alias.name:
                        violations.append(f"{py_file.name} line {node.lineno}: imports '{alias.name}'")

    assert not violations, "Ports package has forbidden adapter imports:\n" + "\n".join(violations)


def test_plan_source_protocol_methods_are_async() -> None:
    """PlanSource Protocol methods must be async (coroutine functions)."""
    import inspect

    from mcp_trino_optimizer.ports import PlanSource

    for method_name in ("fetch_plan", "fetch_analyze_plan", "fetch_distributed_plan"):
        method = getattr(PlanSource, method_name)
        assert inspect.iscoroutinefunction(method), f"PlanSource.{method_name} must be async"


def test_stats_source_protocol_methods_are_async() -> None:
    """StatsSource Protocol methods must be async (coroutine functions)."""
    import inspect

    from mcp_trino_optimizer.ports import StatsSource

    for method_name in ("fetch_table_stats", "fetch_system_runtime"):
        method = getattr(StatsSource, method_name)
        assert inspect.iscoroutinefunction(method), f"StatsSource.{method_name} must be async"


def test_catalog_source_protocol_methods_are_async() -> None:
    """CatalogSource Protocol methods must be async (coroutine functions)."""
    import inspect

    from mcp_trino_optimizer.ports import CatalogSource

    for method_name in ("fetch_iceberg_metadata", "fetch_catalogs", "fetch_schemas"):
        method = getattr(CatalogSource, method_name)
        assert inspect.iscoroutinefunction(method), f"CatalogSource.{method_name} must be async"
