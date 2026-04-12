"""Crashing rule isolation tests — RuleError emitted, other rules continue."""

from typing import Any, ClassVar

import pytest

from mcp_trino_optimizer.parser.models import EstimatedPlan, PlanNode
from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.engine import RuleEngine
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement
from mcp_trino_optimizer.rules.findings import RuleError, RuleFinding
from mcp_trino_optimizer.rules.registry import RuleRegistry


def _make_plan() -> EstimatedPlan:
    return EstimatedPlan(root=PlanNode(id="root", name="Output", children=[]))


class _CrashingRule(Rule):
    rule_id: ClassVar[str] = "CRASH"
    evidence_requirement: ClassVar[EvidenceRequirement] = EvidenceRequirement.PLAN_ONLY

    def check(self, plan: Any, evidence: EvidenceBundle) -> list[RuleFinding]:
        raise ValueError("intentional crash for isolation test")


class _GoodRule(Rule):
    rule_id: ClassVar[str] = "GOOD"
    evidence_requirement: ClassVar[EvidenceRequirement] = EvidenceRequirement.PLAN_ONLY

    def check(self, plan: Any, evidence: EvidenceBundle) -> list[RuleFinding]:
        return [
            RuleFinding(
                rule_id=self.rule_id,
                severity="low",
                confidence=1.0,
                message="good rule fired",
                evidence={},
                operator_ids=[],
            )
        ]


@pytest.mark.asyncio
async def test_crashing_rule_emits_rule_error() -> None:
    """When a rule's check() raises, the engine emits RuleError with correct error_type."""
    reg = RuleRegistry()
    reg.register(_CrashingRule)
    engine = RuleEngine(stats_source=None, catalog_source=None, registry=reg)

    results = await engine.run(_make_plan())
    assert len(results) == 1
    err = results[0]
    assert isinstance(err, RuleError)
    assert err.rule_id == "CRASH"
    assert err.error_type == "ValueError"


@pytest.mark.asyncio
async def test_crashing_rule_message_equals_str_exception() -> None:
    """RuleError.message equals str(the_exception)."""
    reg = RuleRegistry()
    reg.register(_CrashingRule)
    engine = RuleEngine(stats_source=None, catalog_source=None, registry=reg)

    results = await engine.run(_make_plan())
    err = results[0]
    assert isinstance(err, RuleError)
    assert err.message == "intentional crash for isolation test"


@pytest.mark.asyncio
async def test_good_rule_runs_after_crashing_rule() -> None:
    """Remaining rules continue executing after one rule crashes."""
    reg = RuleRegistry()
    reg.register(_CrashingRule)
    reg.register(_GoodRule)
    engine = RuleEngine(stats_source=None, catalog_source=None, registry=reg)

    results = await engine.run(_make_plan())
    assert len(results) == 2
    assert isinstance(results[0], RuleError)
    assert isinstance(results[1], RuleFinding)
    assert results[1].rule_id == "GOOD"


@pytest.mark.asyncio
async def test_runtime_error_also_isolated() -> None:
    """RuntimeError (not just ValueError) is also caught and becomes RuleError."""

    class _RuntimeCrash(Rule):
        rule_id: ClassVar[str] = "RTCRASH"
        evidence_requirement: ClassVar[EvidenceRequirement] = EvidenceRequirement.PLAN_ONLY

        def check(self, plan: Any, evidence: EvidenceBundle) -> list[RuleFinding]:
            raise RuntimeError("runtime crash")

    reg = RuleRegistry()
    reg.register(_RuntimeCrash)
    engine = RuleEngine(stats_source=None, catalog_source=None, registry=reg)

    results = await engine.run(_make_plan())
    assert len(results) == 1
    err = results[0]
    assert isinstance(err, RuleError)
    assert err.error_type == "RuntimeError"
    assert err.message == "runtime crash"
