"""R5 BroadcastTooBig rule tests.

Three fixture classes:
1. Synthetic-minimum: hand-built InnerJoin node with REPLICATED distribution.
2. Realistic: loaded from tests/fixtures/explain/480/join.json.
3. Negative-control: PARTITIONED join, small build side, no join.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_trino_optimizer.parser.models import CostEstimate, EstimatedPlan, PlanNode
from mcp_trino_optimizer.parser.parser import parse_estimated_plan
from mcp_trino_optimizer.rules.evidence import EvidenceBundle
from mcp_trino_optimizer.rules.r5_broadcast_too_big import R5BroadcastTooBig
from mcp_trino_optimizer.rules.thresholds import RuleThresholds

FIXTURES_480 = Path(__file__).parent.parent / "fixtures" / "explain" / "480"

_100MB = 100 * 1024 * 1024
_200MB = 200 * 1024 * 1024
_10MB = 10 * 1024 * 1024


def _make_plan(node: PlanNode) -> EstimatedPlan:
    """Wrap a single node in a minimal EstimatedPlan."""
    return EstimatedPlan(root=node)


def _make_join_node(
    *,
    distribution: str = "REPLICATED",
    build_size_bytes: float | None = _200MB,
    join_name: str = "InnerJoin",
    join_id: str = "1",
    probe_id: str = "2",
    build_id: str = "3",
) -> PlanNode:
    """Build a join PlanNode with a probe and build child."""
    build_estimates: list[CostEstimate] = []
    if build_size_bytes is not None:
        build_estimates = [CostEstimate(outputSizeInBytes=build_size_bytes)]

    probe = PlanNode(
        id=probe_id,
        name="ScanFilter",
        estimates=[CostEstimate(outputRowCount=1000.0, outputSizeInBytes=50_000.0)],
    )
    build = PlanNode(
        id=build_id,
        name="TableScan",
        estimates=build_estimates,
    )
    return PlanNode(
        id=join_id,
        name=join_name,
        descriptor={"distribution": distribution},
        children=[probe, build],
    )


# ---------------------------------------------------------------------------
# Synthetic-minimum tests
# ---------------------------------------------------------------------------


class TestR5SyntheticMinimum:
    """R5 fires on REPLICATED join with large build side."""

    def test_replicated_large_build_fires(self) -> None:
        """REPLICATED join with 200MB build side fires R5."""
        join = _make_join_node(distribution="REPLICATED", build_size_bytes=_200MB)
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan)

        findings = R5BroadcastTooBig().check(plan, bundle)

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "R5"
        assert f.severity == "high"
        assert f.confidence == pytest.approx(0.85)
        assert "1" in f.operator_ids  # join node id
        assert f.evidence["distribution"] == "REPLICATED"
        assert f.evidence["build_side_estimated_bytes"] == pytest.approx(_200MB)
        assert f.evidence["threshold_bytes"] == _100MB

    def test_replicated_semi_join_large_build_fires(self) -> None:
        """SemiJoin with REPLICATED distribution also triggers R5."""
        join = _make_join_node(
            distribution="REPLICATED",
            build_size_bytes=_200MB,
            join_name="SemiJoin",
        )
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan)

        findings = R5BroadcastTooBig().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].rule_id == "R5"

    def test_custom_threshold_respected(self) -> None:
        """R5 respects a custom threshold from RuleThresholds."""
        thresholds = RuleThresholds(broadcast_max_bytes=_200MB + 1)
        join = _make_join_node(distribution="REPLICATED", build_size_bytes=_200MB)
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan)

        # 200MB is below the custom threshold of 200MB+1 -> no finding
        findings = R5BroadcastTooBig(thresholds=thresholds).check(plan, bundle)
        assert findings == []


# ---------------------------------------------------------------------------
# Negative-control tests
# ---------------------------------------------------------------------------


class TestR5NegativeControl:
    """R5 should NOT fire in these scenarios."""

    def test_small_build_does_not_fire(self) -> None:
        """REPLICATED join with 10MB build side (under threshold) returns []."""
        join = _make_join_node(distribution="REPLICATED", build_size_bytes=_10MB)
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan)

        findings = R5BroadcastTooBig().check(plan, bundle)

        assert findings == []

    def test_partitioned_join_does_not_fire(self) -> None:
        """PARTITIONED join never triggers R5 regardless of size."""
        join = _make_join_node(distribution="PARTITIONED", build_size_bytes=_200MB)
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan)

        findings = R5BroadcastTooBig().check(plan, bundle)

        assert findings == []

    def test_no_join_nodes_returns_empty(self) -> None:
        """Plan with only scan nodes — R5 returns []."""
        scan = PlanNode(
            id="0",
            name="TableScan",
            estimates=[CostEstimate(outputSizeInBytes=_200MB)],
        )
        plan = _make_plan(scan)
        bundle = EvidenceBundle(plan=plan)

        findings = R5BroadcastTooBig().check(plan, bundle)

        assert findings == []

    def test_no_build_side_estimates_does_not_fire(self) -> None:
        """Join with REPLICATED but build side has no estimates — cannot determine size."""
        join = _make_join_node(distribution="REPLICATED", build_size_bytes=None)
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan)

        findings = R5BroadcastTooBig().check(plan, bundle)

        assert findings == []

    def test_single_child_join_does_not_crash(self) -> None:
        """Malformed join with only one child must not raise (T-04-13 guard)."""
        join = PlanNode(
            id="1",
            name="InnerJoin",
            descriptor={"distribution": "REPLICATED"},
            children=[
                PlanNode(
                    id="2",
                    name="TableScan",
                    estimates=[CostEstimate(outputSizeInBytes=_200MB)],
                )
            ],
        )
        plan = _make_plan(join)
        bundle = EvidenceBundle(plan=plan)

        # Must not raise — T-04-13 guard
        findings = R5BroadcastTooBig().check(plan, bundle)
        assert findings == []  # Only one child — cannot access build side


# ---------------------------------------------------------------------------
# Realistic fixture tests
# ---------------------------------------------------------------------------


class TestR5Realistic:
    """R5 against the join.json fixture (REPLICATED distribution)."""

    def test_fixture_join_replicated_small_build(self) -> None:
        """join.json has InnerJoin with REPLICATED distribution.

        The fixture build side (LocalExchange -> RemoteSource) has
        outputSizeInBytes ~959 bytes, well under the 100MB threshold.
        R5 should NOT fire on this realistic fixture.
        """
        json_text = (FIXTURES_480 / "join.json").read_text()
        plan = parse_estimated_plan(json_text)

        bundle = EvidenceBundle(plan=plan)
        findings = R5BroadcastTooBig().check(plan, bundle)

        # Fixture build side is tiny (959 bytes) — below threshold
        assert findings == []

    def test_fixture_join_replicated_with_lowered_threshold(self) -> None:
        """With a threshold of 1 byte, even the tiny fixture build side triggers R5."""
        json_text = (FIXTURES_480 / "join.json").read_text()
        plan = parse_estimated_plan(json_text)

        thresholds = RuleThresholds(broadcast_max_bytes=1)
        bundle = EvidenceBundle(plan=plan)
        findings = R5BroadcastTooBig(thresholds=thresholds).check(plan, bundle)

        # With 1-byte threshold, any non-zero build side must fire
        assert len(findings) >= 1
        assert findings[0].rule_id == "R5"
