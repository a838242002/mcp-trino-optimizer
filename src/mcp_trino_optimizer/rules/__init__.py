"""Public API for the rules subpackage.

Import from here rather than from individual submodules for stability.
"""

from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.engine import RuleEngine
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement, safe_float
from mcp_trino_optimizer.rules.findings import (
    EngineResult,
    RuleError,
    RuleFinding,
    RuleSkipped,
    Severity,
)
from mcp_trino_optimizer.rules.registry import registry
from mcp_trino_optimizer.rules.thresholds import RuleThresholds

__all__ = [
    "EngineResult",
    "EvidenceBundle",
    "EvidenceRequirement",
    "Rule",
    "RuleEngine",
    "RuleError",
    "RuleFinding",
    "RuleSkipped",
    "RuleThresholds",
    "Severity",
    "registry",
    "safe_float",
]
