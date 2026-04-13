"""Shared fixtures for recommender tests."""

from __future__ import annotations

from typing import Any

import pytest

from mcp_trino_optimizer.rules.findings import RuleFinding, Severity


@pytest.fixture
def sample_finding_factory() -> type[_SampleFindingFactory]:
    """Factory fixture that builds RuleFinding instances with sensible defaults."""
    return _SampleFindingFactory


class _SampleFindingFactory:
    """Callable factory for RuleFinding test instances."""

    @staticmethod
    def create(
        rule_id: str = "R1",
        severity: Severity = "medium",
        confidence: float = 0.8,
        evidence: dict[str, Any] | None = None,
        operator_ids: list[str] | None = None,
    ) -> RuleFinding:
        return RuleFinding(
            rule_id=rule_id,
            severity=severity,
            confidence=confidence,
            message=f"Test finding for {rule_id}",
            evidence=evidence or {},
            operator_ids=operator_ids or ["node-1"],
        )


ALL_RULE_IDS = [
    "R1",
    "R2",
    "R3",
    "R4",
    "R5",
    "R6",
    "R7",
    "R8",
    "R9",
    "I1",
    "I3",
    "I6",
    "I8",
    "D11",
]


@pytest.fixture
def sample_findings_all_rules() -> list[RuleFinding]:
    """One finding per rule_id for full coverage."""
    return [_SampleFindingFactory.create(rule_id=rid) for rid in ALL_RULE_IDS]


@pytest.fixture
def sample_findings_r1_d11() -> list[RuleFinding]:
    """R1 and D11 findings on the same operator (for conflict tests in Plan 02)."""
    return [
        _SampleFindingFactory.create(
            rule_id="R1",
            severity="medium",
            confidence=0.7,
            operator_ids=["node-5"],
        ),
        _SampleFindingFactory.create(
            rule_id="D11",
            severity="high",
            confidence=0.95,
            operator_ids=["node-5"],
        ),
    ]
