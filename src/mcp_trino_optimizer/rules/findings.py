"""Rule finding types — discriminated union with kind literal discriminator (D-02, D-03).

RuleFinding | RuleError | RuleSkipped form the complete result type for
RuleEngine.run(). EngineResult is the Annotated union alias used in type hints.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "high", "medium", "low"]
"""Four-tier severity scale (D-03). No 'info' tier.

Maps to:
  critical — must fix (query will fail or is catastrophically slow)
  high     — should fix (significant performance impact)
  medium   — consider fixing (moderate impact)
  low      — low priority (minor or situational)
"""


class RuleFinding(BaseModel):
    """A deterministic finding emitted by a rule when it detects an issue."""

    kind: Literal["finding"] = "finding"
    rule_id: str
    """Stable rule identifier, e.g. 'R1', 'I3', 'D11'."""

    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    """Confidence score for the finding, 0.0-1.0."""

    message: str
    """Human-readable description of the issue."""

    evidence: dict[str, Any]
    """Machine-readable evidence dict; schema is rule-specific but always JSON-serializable."""

    operator_ids: list[str]
    """Plan node IDs that triggered this finding."""


class RuleError(BaseModel):
    """Emitted when a rule's check() raises an unexpected exception.

    The engine isolates the crash and continues with remaining rules.
    """

    kind: Literal["error"] = "error"
    rule_id: str
    error_type: str
    """Exception class name, e.g. 'ValueError', 'KeyError'."""

    message: str
    """str(exception) from the caught exception."""


class RuleSkipped(BaseModel):
    """Emitted when a rule is skipped due to unavailable evidence or plan type mismatch."""

    kind: Literal["skipped"] = "skipped"
    rule_id: str
    reason: str
    """Machine-readable reason code, e.g. 'offline_mode_no_stats_source'."""


EngineResult = Annotated[
    RuleFinding | RuleError | RuleSkipped,
    Field(discriminator="kind"),
]
"""Discriminated union of all possible engine output types.

Use this as the element type of list[EngineResult] in RuleEngine.run() return.
Pydantic can deserialize a list of dicts using the 'kind' discriminator field.
"""

__all__ = [
    "EngineResult",
    "RuleError",
    "RuleFinding",
    "RuleSkipped",
    "Severity",
]
