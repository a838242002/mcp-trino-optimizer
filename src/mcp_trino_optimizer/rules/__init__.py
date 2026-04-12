"""Public API for the rules subpackage.

Import from here rather than from individual submodules for stability.
"""

import mcp_trino_optimizer.rules.d11_cost_vs_actual
import mcp_trino_optimizer.rules.i1_small_files
import mcp_trino_optimizer.rules.i3_delete_files
import mcp_trino_optimizer.rules.i6_stale_snapshots
import mcp_trino_optimizer.rules.i8_partition_transform

# Import all rule modules to trigger registry.register() calls at module load time.
# Order matches rule ID sequence for readability; registration order does not affect behavior.
import mcp_trino_optimizer.rules.r1_missing_stats
import mcp_trino_optimizer.rules.r2_partition_pruning
import mcp_trino_optimizer.rules.r3_predicate_pushdown
import mcp_trino_optimizer.rules.r4_dynamic_filtering
import mcp_trino_optimizer.rules.r5_broadcast_too_big
import mcp_trino_optimizer.rules.r6_join_order
import mcp_trino_optimizer.rules.r7_cpu_skew
import mcp_trino_optimizer.rules.r8_exchange_volume
import mcp_trino_optimizer.rules.r9_low_selectivity  # noqa: F401
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
