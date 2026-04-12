"""R8 ExchangeVolume rule tests.

Three fixture classes:
1. Synthetic-minimum: plan with Exchange node outputting more bytes than Scan input.
2. Realistic: full_scan.json (no Exchange nodes — R8 should not fire).
3. Negative-control: exchange < scan, no exchange nodes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_trino_optimizer.parser.models import CostEstimate, EstimatedPlan, PlanNode
from mcp_trino_optimizer.parser.parser import parse_estimated_plan
from mcp_trino_optimizer.rules.evidence import EvidenceBundle
from mcp_trino_optimizer.rules.r8_exchange_volume import R8ExchangeVolume

FIXTURES_480 = Path(__file__).parent.parent / "fixtures" / "explain" / "480"

_100MB = 100 * 1024 * 1024
_500MB = 500 * 1024 * 1024
_10MB = 10 * 1024 * 1024


def _make_plan(node: PlanNode) -> EstimatedPlan:
    return EstimatedPlan(root=node)


def _make_plan_with_exchange_and_scan(
    *,
    exchange_bytes: float,
    scan_bytes: float,
    exchange_name: str = "Exchange",
) -> EstimatedPlan:
    """Build a plan: Output -> Exchange -> TableScan with given byte estimates."""
    scan = PlanNode(
        id="0",
        name="TableScan",
        estimates=[CostEstimate(outputSizeInBytes=scan_bytes)],
    )
    exchange = PlanNode(
        id="1",
        name=exchange_name,
        estimates=[CostEstimate(outputSizeInBytes=exchange_bytes)],
        children=[scan],
    )
    output = PlanNode(
        id="2",
        name="Output",
        estimates=[CostEstimate(outputSizeInBytes=exchange_bytes)],
        children=[exchange],
    )
    return EstimatedPlan(root=output)


# ---------------------------------------------------------------------------
# Synthetic-minimum tests
# ---------------------------------------------------------------------------


class TestR8SyntheticMinimum:
    """R8 fires when total exchange bytes exceed total scan bytes."""

    def test_exchange_exceeds_scan_fires(self) -> None:
        """Exchange 500MB, scan 100MB -> R8 fires."""
        plan = _make_plan_with_exchange_and_scan(
            exchange_bytes=_500MB,
            scan_bytes=_100MB,
        )
        bundle = EvidenceBundle(plan=plan)

        findings = R8ExchangeVolume().check(plan, bundle)

        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "R8"
        assert f.severity == "medium"
        assert f.confidence == pytest.approx(0.75)
        assert f.evidence["total_exchange_bytes"] == pytest.approx(_500MB)
        assert f.evidence["total_scan_bytes"] == pytest.approx(_100MB)
        assert f.evidence["ratio"] == pytest.approx(_500MB / _100MB)
        assert "1" in f.operator_ids  # exchange node id

    def test_local_exchange_counts(self) -> None:
        """LocalExchange is also an exchange type — should be counted."""
        plan = _make_plan_with_exchange_and_scan(
            exchange_bytes=_500MB,
            scan_bytes=_100MB,
            exchange_name="LocalExchange",
        )
        bundle = EvidenceBundle(plan=plan)

        findings = R8ExchangeVolume().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].rule_id == "R8"

    def test_remote_source_counts(self) -> None:
        """RemoteSource is also an exchange type — should be counted."""
        plan = _make_plan_with_exchange_and_scan(
            exchange_bytes=_500MB,
            scan_bytes=_100MB,
            exchange_name="RemoteSource",
        )
        bundle = EvidenceBundle(plan=plan)

        findings = R8ExchangeVolume().check(plan, bundle)

        assert len(findings) == 1
        assert findings[0].rule_id == "R8"

    def test_multiple_exchange_nodes_summed(self) -> None:
        """Two exchange nodes summed together must exceed scan to fire."""
        scan = PlanNode(
            id="0",
            name="TableScan",
            estimates=[CostEstimate(outputSizeInBytes=_100MB)],
        )
        ex1 = PlanNode(
            id="1",
            name="Exchange",
            estimates=[CostEstimate(outputSizeInBytes=_200MB)],
            children=[scan],
        )
        ex2 = PlanNode(
            id="2",
            name="Exchange",
            estimates=[CostEstimate(outputSizeInBytes=_200MB)],
            children=[ex1],
        )
        plan = EstimatedPlan(root=ex2)
        bundle = EvidenceBundle(plan=plan)

        findings = R8ExchangeVolume().check(plan, bundle)

        # 400MB exchange vs 100MB scan -> fires
        assert len(findings) == 1
        assert findings[0].evidence["total_exchange_bytes"] == pytest.approx(
            _200MB + _200MB
        )


# ---------------------------------------------------------------------------
# Negative-control tests
# ---------------------------------------------------------------------------

_200MB = 200 * 1024 * 1024


class TestR8NegativeControl:
    """R8 should NOT fire in these scenarios."""

    def test_exchange_less_than_scan_does_not_fire(self) -> None:
        """Exchange 10MB, scan 100MB -> R8 returns []."""
        plan = _make_plan_with_exchange_and_scan(
            exchange_bytes=_10MB,
            scan_bytes=_100MB,
        )
        bundle = EvidenceBundle(plan=plan)

        findings = R8ExchangeVolume().check(plan, bundle)

        assert findings == []

    def test_no_exchange_nodes_returns_empty(self) -> None:
        """Plan with only a scan node — R8 returns []."""
        scan = PlanNode(
            id="0",
            name="TableScan",
            estimates=[CostEstimate(outputSizeInBytes=_100MB)],
        )
        plan = _make_plan(scan)
        bundle = EvidenceBundle(plan=plan)

        findings = R8ExchangeVolume().check(plan, bundle)

        assert findings == []

    def test_exchange_equals_scan_does_not_fire(self) -> None:
        """Exchange exactly equals scan (ratio=1.0) — does not fire."""
        plan = _make_plan_with_exchange_and_scan(
            exchange_bytes=_100MB,
            scan_bytes=_100MB,
        )
        bundle = EvidenceBundle(plan=plan)

        findings = R8ExchangeVolume().check(plan, bundle)

        assert findings == []

    def test_no_scan_bytes_does_not_fire(self) -> None:
        """Exchange present but no scan bytes estimates — cannot compute ratio."""
        exchange = PlanNode(
            id="1",
            name="Exchange",
            estimates=[CostEstimate(outputSizeInBytes=_500MB)],
        )
        plan = _make_plan(exchange)
        bundle = EvidenceBundle(plan=plan)

        # No scan nodes -> scan_bytes = 0 -> no finding
        findings = R8ExchangeVolume().check(plan, bundle)

        assert findings == []


# ---------------------------------------------------------------------------
# Realistic fixture tests
# ---------------------------------------------------------------------------


class TestR8Realistic:
    """R8 against real fixtures."""

    def test_full_scan_no_exchange(self) -> None:
        """full_scan.json has no Exchange nodes — R8 should not fire."""
        json_text = (FIXTURES_480 / "full_scan.json").read_text()
        plan = parse_estimated_plan(json_text)

        bundle = EvidenceBundle(plan=plan)
        findings = R8ExchangeVolume().check(plan, bundle)

        assert findings == []

    def test_join_fixture_with_local_exchange(self) -> None:
        """join.json has a LocalExchange; scan bytes are much larger than exchange bytes.

        The LocalExchange in the join fixture has outputSizeInBytes ~959 bytes,
        while the ScanFilter has ~1200 bytes. Exchange < scan -> R8 should NOT fire.
        """
        json_text = (FIXTURES_480 / "join.json").read_text()
        plan = parse_estimated_plan(json_text)

        bundle = EvidenceBundle(plan=plan)
        findings = R8ExchangeVolume().check(plan, bundle)

        # Exchange (~959) < Scan (~1200) -> no finding
        assert findings == []
