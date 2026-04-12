"""Registry unit tests — register, all_rules, dedup, decorator usage."""

from typing import ClassVar

from mcp_trino_optimizer.parser.models import BasePlan
from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement
from mcp_trino_optimizer.rules.findings import RuleFinding
from mcp_trino_optimizer.rules.registry import RuleRegistry


class _FakeRule(Rule):
    rule_id: ClassVar[str] = "FAKE1"
    evidence_requirement: ClassVar[EvidenceRequirement] = EvidenceRequirement.PLAN_ONLY

    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:
        return []


class _FakeRule2(Rule):
    rule_id: ClassVar[str] = "FAKE2"
    evidence_requirement: ClassVar[EvidenceRequirement] = EvidenceRequirement.PLAN_ONLY

    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:
        return []


def test_register_and_all_rules() -> None:
    """Registering a Rule subclass makes it appear in all_rules()."""
    reg = RuleRegistry()
    reg.register(_FakeRule)
    rules = reg.all_rules()
    assert _FakeRule in rules
    assert len(rules) == 1


def test_register_twice_no_duplicate() -> None:
    """Registering the same class twice results in only one entry."""
    reg = RuleRegistry()
    reg.register(_FakeRule)
    reg.register(_FakeRule)
    assert len(reg.all_rules()) == 1


def test_register_returns_class() -> None:
    """register() returns the class unchanged (usable as @decorator)."""
    reg = RuleRegistry()
    result = reg.register(_FakeRule)
    assert result is _FakeRule


def test_register_as_decorator() -> None:
    """@registry.register works as a class decorator."""
    reg = RuleRegistry()

    @reg.register
    class _DecoratedRule(Rule):
        rule_id: ClassVar[str] = "DECO1"
        evidence_requirement: ClassVar[EvidenceRequirement] = EvidenceRequirement.PLAN_ONLY

        def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:
            return []

    assert _DecoratedRule in reg.all_rules()


def test_multiple_rules_order_preserved() -> None:
    """Rules appear in all_rules() in registration order."""
    reg = RuleRegistry()
    reg.register(_FakeRule)
    reg.register(_FakeRule2)
    rules = reg.all_rules()
    assert rules[0] is _FakeRule
    assert rules[1] is _FakeRule2
