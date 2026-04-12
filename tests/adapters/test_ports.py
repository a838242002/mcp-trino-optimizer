"""Tests for hexagonal port Protocol definitions.

RED phase: these tests validate that the port Protocols exist with the right
shape and that no adapter coupling exists in the ports package.
"""

from __future__ import annotations

import ast
from pathlib import Path


def test_plan_source_is_protocol() -> None:
    """PlanSource must be a runtime_checkable Protocol."""
    from typing import Protocol

    from mcp_trino_optimizer.ports import PlanSource

    # It's a Protocol
    assert issubclass(PlanSource, Protocol)


def test_plan_source_has_required_methods() -> None:
    """PlanSource must have fetch_plan, fetch_analyze_plan, fetch_distributed_plan."""
    from mcp_trino_optimizer.ports import PlanSource

    assert hasattr(PlanSource, "fetch_plan")
    assert hasattr(PlanSource, "fetch_analyze_plan")
    assert hasattr(PlanSource, "fetch_distributed_plan")


def test_stats_source_is_protocol() -> None:
    """StatsSource must be a runtime_checkable Protocol."""
    from typing import Protocol

    from mcp_trino_optimizer.ports import StatsSource

    assert issubclass(StatsSource, Protocol)


def test_stats_source_has_required_methods() -> None:
    """StatsSource must have fetch_table_stats, fetch_system_runtime."""
    from mcp_trino_optimizer.ports import StatsSource

    assert hasattr(StatsSource, "fetch_table_stats")
    assert hasattr(StatsSource, "fetch_system_runtime")


def test_catalog_source_is_protocol() -> None:
    """CatalogSource must be a runtime_checkable Protocol."""
    from typing import Protocol

    from mcp_trino_optimizer.ports import CatalogSource

    assert issubclass(CatalogSource, Protocol)


def test_catalog_source_has_required_methods() -> None:
    """CatalogSource must have fetch_iceberg_metadata, fetch_catalogs, fetch_schemas."""
    from mcp_trino_optimizer.ports import CatalogSource

    assert hasattr(CatalogSource, "fetch_iceberg_metadata")
    assert hasattr(CatalogSource, "fetch_catalogs")
    assert hasattr(CatalogSource, "fetch_schemas")


def test_explain_plan_has_required_fields() -> None:
    """ExplainPlan must have plan_json, plan_type, source_trino_version fields."""
    import dataclasses

    from mcp_trino_optimizer.ports import ExplainPlan

    fields = {f.name for f in dataclasses.fields(ExplainPlan)}
    assert "plan_json" in fields
    assert "plan_type" in fields
    assert "source_trino_version" in fields


def test_explain_plan_plan_type_literal() -> None:
    """ExplainPlan plan_type must accept estimated, executed, distributed."""
    from mcp_trino_optimizer.ports import ExplainPlan

    for plan_type in ("estimated", "executed", "distributed"):
        ep = ExplainPlan(plan_json={"test": 1}, plan_type=plan_type)  # type: ignore[arg-type]
        assert ep.plan_type == plan_type


def test_explain_plan_source_trino_version_defaults_none() -> None:
    """ExplainPlan.source_trino_version defaults to None."""
    from mcp_trino_optimizer.ports import ExplainPlan

    ep = ExplainPlan(plan_json={}, plan_type="estimated")
    assert ep.source_trino_version is None


def test_ports_package_exports_all_symbols() -> None:
    """The ports __init__.py must re-export PlanSource, StatsSource, CatalogSource, ExplainPlan."""
    from mcp_trino_optimizer import ports

    assert hasattr(ports, "PlanSource")
    assert hasattr(ports, "StatsSource")
    assert hasattr(ports, "CatalogSource")
    assert hasattr(ports, "ExplainPlan")


def test_ports_have_no_adapter_imports() -> None:
    """Port modules must NOT import from adapters — zero coupling."""
    ports_dir = Path(__file__).parent.parent.parent / "src" / "mcp_trino_optimizer" / "ports"
    assert ports_dir.is_dir(), f"ports dir not found: {ports_dir}"

    for py_file in ports_dir.glob("*.py"):
        source = py_file.read_text()
        tree = ast.parse(source, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert "adapters" not in node.module, f"{py_file.name} imports from adapters: {node.module}"
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        assert "adapters" not in alias.name, f"{py_file.name} imports adapters: {alias.name}"
