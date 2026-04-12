"""Hexagonal ports for the mcp-trino-optimizer adapter layer.

This package contains only Protocol definitions and domain value types. It has
ZERO imports from ``mcp_trino_optimizer.adapters`` — that coupling runs in the
opposite direction (adapters depend on ports, not the other way around).

Public API:
    PlanSource      — port for fetching Trino EXPLAIN plans
    EstimatedPlan   — typed plan from EXPLAIN (FORMAT JSON)
    ExecutedPlan    — typed plan from EXPLAIN ANALYZE with runtime metrics
    StatsSource     — port for fetching Trino table/runtime statistics
    CatalogSource   — port for fetching Iceberg catalog metadata

Phase 3: ExplainPlan placeholder removed. EstimatedPlan and ExecutedPlan are
the domain types returned by PlanSource implementations.
"""

from __future__ import annotations

from mcp_trino_optimizer.parser.models import EstimatedPlan, ExecutedPlan
from mcp_trino_optimizer.ports.catalog_source import CatalogSource
from mcp_trino_optimizer.ports.plan_source import PlanSource
from mcp_trino_optimizer.ports.stats_source import StatsSource

__all__ = [
    "CatalogSource",
    "EstimatedPlan",
    "ExecutedPlan",
    "PlanSource",
    "StatsSource",
]
