"""Hexagonal ports for the mcp-trino-optimizer adapter layer.

This package contains only Protocol definitions and domain value types. It has
ZERO imports from ``mcp_trino_optimizer.adapters`` — that coupling runs in the
opposite direction (adapters depend on ports, not the other way around).

Public API:
    PlanSource      — port for fetching Trino EXPLAIN plans
    ExplainPlan     — domain dataclass for a fetched plan
    StatsSource     — port for fetching Trino table/runtime statistics
    CatalogSource   — port for fetching Iceberg catalog metadata
"""

from __future__ import annotations

from mcp_trino_optimizer.ports.catalog_source import CatalogSource
from mcp_trino_optimizer.ports.plan_source import ExplainPlan, PlanSource
from mcp_trino_optimizer.ports.stats_source import StatsSource

__all__ = [
    "CatalogSource",
    "ExplainPlan",
    "PlanSource",
    "StatsSource",
]
