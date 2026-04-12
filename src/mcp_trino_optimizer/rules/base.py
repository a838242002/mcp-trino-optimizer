"""Rule ABC — base class for all deterministic rule implementations (D-06).

Every rule is a concrete subclass of Rule with:
  rule_id: ClassVar[str]                    — unique stable identifier
  evidence_requirement: ClassVar[EvidenceRequirement]
  check(plan, evidence) -> list[RuleFinding]  — pure, sync, no I/O

Rules must NOT import from mcp_trino_optimizer.adapters (enforced by mypy + pre-commit).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement
from mcp_trino_optimizer.rules.findings import RuleFinding

if TYPE_CHECKING:
    from mcp_trino_optimizer.parser.models import BasePlan


class Rule(ABC):
    """Abstract base class for all deterministic rules.

    Subclasses declare their rule_id and evidence_requirement as ClassVars,
    then implement check() as a pure, deterministic, sync function.

    The engine instantiates each rule class (zero-arg constructor) and calls check().
    Rules must not cache state between calls — each analysis is independent.
    """

    rule_id: ClassVar[str]
    """Stable rule identifier, e.g. 'R1', 'I3', 'D11'. Must be unique across all rules."""

    evidence_requirement: ClassVar[EvidenceRequirement]
    """Declares what evidence this rule needs; engine skips the rule if unavailable."""

    @abstractmethod
    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:
        """Run the rule against the plan and evidence bundle.

        Args:
            plan: The plan tree to analyze.
            evidence: Pre-fetched evidence bundle (table stats, Iceberg metadata).

        Returns:
            List of RuleFinding objects if the rule triggers, empty list otherwise.

        Contract:
            - Pure and deterministic: same inputs must produce same outputs.
            - Sync: no async/await, no I/O, no external calls.
            - Safe: must not raise; all exceptions are caught by the engine.
        """
        ...


__all__ = ["Rule"]
