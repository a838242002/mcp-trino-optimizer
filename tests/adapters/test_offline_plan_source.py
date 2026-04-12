"""Tests for OfflinePlanSource adapter.

TDD RED phase: validates offline JSON plan parsing, size limits,
plan type detection, and classifier-exempt behavior.
"""
from __future__ import annotations

import json

import pytest

VALID_ESTIMATED_PLAN = json.dumps(
    {
        "id": "0",
        "name": "Output",
        "children": [{"id": "1", "name": "TableScan", "children": []}],
    }
)

VALID_EXECUTED_PLAN = json.dumps(
    {
        "id": "0",
        "name": "Output",
        "cpuTimeMillis": 1234,
        "wallTimeMillis": 5678,
        "processedRows": 1000,
        "children": [],
    }
)

VALID_DISTRIBUTED_PLAN = json.dumps(
    {
        "id": "0",
        "name": "Output",
        "stageId": "0",
        "children": [],
    }
)


class TestFetchPlan:
    """Tests for OfflinePlanSource.fetch_plan()."""

    async def test_valid_json_returns_explain_plan(self) -> None:
        """fetch_plan() with valid JSON returns an ExplainPlan."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource
        from mcp_trino_optimizer.ports import ExplainPlan

        source = OfflinePlanSource()
        result = await source.fetch_plan(VALID_ESTIMATED_PLAN)

        assert isinstance(result, ExplainPlan)

    async def test_valid_json_sets_plan_json(self) -> None:
        """fetch_plan() sets plan_json to parsed dict."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        result = await source.fetch_plan(VALID_ESTIMATED_PLAN)

        assert result.plan_json == json.loads(VALID_ESTIMATED_PLAN)

    async def test_valid_json_sets_raw_text(self) -> None:
        """fetch_plan() sets raw_text to the original JSON string."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        result = await source.fetch_plan(VALID_ESTIMATED_PLAN)

        assert result.raw_text == VALID_ESTIMATED_PLAN

    async def test_source_trino_version_is_none_for_offline(self) -> None:
        """fetch_plan() sets source_trino_version=None for offline mode."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        result = await source.fetch_plan(VALID_ESTIMATED_PLAN)

        assert result.source_trino_version is None

    async def test_estimated_plan_detected_as_estimated(self) -> None:
        """fetch_plan() detects a plan without runtime metrics as estimated."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        result = await source.fetch_plan(VALID_ESTIMATED_PLAN)

        assert result.plan_type == "estimated"

    async def test_executed_plan_detected_as_executed(self) -> None:
        """fetch_plan() detects a plan with cpuTimeMillis as executed."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        result = await source.fetch_plan(VALID_EXECUTED_PLAN)

        assert result.plan_type == "executed"

    async def test_invalid_json_raises_value_error(self) -> None:
        """fetch_plan() with invalid JSON raises ValueError."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        with pytest.raises(ValueError, match="Invalid JSON"):
            await source.fetch_plan("not valid json {{{")

    async def test_empty_string_raises_value_error(self) -> None:
        """fetch_plan() with empty string raises ValueError."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        with pytest.raises(ValueError, match="empty"):
            await source.fetch_plan("")

    async def test_plan_exceeding_1mb_raises_value_error(self) -> None:
        """fetch_plan() with JSON > 1MB raises ValueError with 'exceeds maximum'."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        # Build a JSON string > 1MB
        big_value = "x" * 1_000_001
        big_json = json.dumps({"data": big_value})

        with pytest.raises(ValueError, match="exceeds maximum"):
            await source.fetch_plan(big_json)

    async def test_plan_exactly_at_1mb_is_accepted(self) -> None:
        """fetch_plan() accepts plan JSON exactly at the 1MB boundary."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import (
            MAX_PLAN_BYTES,
            OfflinePlanSource,
        )

        source = OfflinePlanSource()
        # Build JSON that's exactly at the limit
        prefix = '{"data":"'
        suffix = '"}'
        fill = "a" * (MAX_PLAN_BYTES - len(prefix.encode()) - len(suffix.encode()))
        boundary_json = prefix + fill + suffix
        assert len(boundary_json.encode("utf-8")) <= MAX_PLAN_BYTES

        result = await source.fetch_plan(boundary_json)
        assert result is not None


class TestFetchAnalyzePlan:
    """Tests for OfflinePlanSource.fetch_analyze_plan()."""

    async def test_returns_executed_plan_type(self) -> None:
        """fetch_analyze_plan() always returns plan_type='executed'."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        result = await source.fetch_analyze_plan(VALID_ESTIMATED_PLAN)

        assert result.plan_type == "executed"

    async def test_invalid_json_raises_value_error(self) -> None:
        """fetch_analyze_plan() with invalid JSON raises ValueError."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        with pytest.raises(ValueError, match="Invalid JSON"):
            await source.fetch_analyze_plan("bad json")

    async def test_size_limit_enforced(self) -> None:
        """fetch_analyze_plan() enforces the 1MB size limit."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        big_json = json.dumps({"data": "x" * 1_000_001})

        with pytest.raises(ValueError, match="exceeds maximum"):
            await source.fetch_analyze_plan(big_json)


class TestFetchDistributedPlan:
    """Tests for OfflinePlanSource.fetch_distributed_plan()."""

    async def test_returns_distributed_plan_type(self) -> None:
        """fetch_distributed_plan() always returns plan_type='distributed'."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        result = await source.fetch_distributed_plan(VALID_DISTRIBUTED_PLAN)

        assert result.plan_type == "distributed"

    async def test_invalid_json_raises_value_error(self) -> None:
        """fetch_distributed_plan() with invalid JSON raises ValueError."""
        from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource

        source = OfflinePlanSource()
        with pytest.raises(ValueError, match="Invalid JSON"):
            await source.fetch_distributed_plan("bad json")


class TestClassifierExempt:
    """Verifies that OfflinePlanSource does not import SqlClassifier (D-15)."""

    def test_offline_plan_source_does_not_import_classifier(self) -> None:
        """OfflinePlanSource module must not contain any reference to SqlClassifier."""
        from pathlib import Path

        module_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "mcp_trino_optimizer"
            / "adapters"
            / "offline"
            / "json_plan_source.py"
        )
        source = module_path.read_text()

        # Check raw text for SqlClassifier
        assert "SqlClassifier" not in source, (
            "OfflinePlanSource must not reference SqlClassifier (D-15)"
        )
        assert "classifier" not in source.lower() or "classifier-exempt" in source.lower(), (
            "OfflinePlanSource must not import or use a classifier"
        )
