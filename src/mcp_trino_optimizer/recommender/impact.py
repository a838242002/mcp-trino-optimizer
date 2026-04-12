"""Impact extractor registry with per-rule extractors for all 14 rules (D-02).

Each rule declares an impact extractor that pulls a 0-1.0 score from its
evidence dict. Rules without quantifiable evidence default to DEFAULT_IMPACT.

All extractors guard against None, NaN, zero denominators via safe_float().
Results are clamped to [0.0, 1.0] in get_impact().
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from mcp_trino_optimizer.rules.evidence import safe_float

ImpactExtractor = Callable[[dict[str, Any]], float]
"""Type alias for impact extractor functions."""

DEFAULT_IMPACT: float = 0.5
"""Default impact score for rules without quantifiable evidence."""

_IMPACT_EXTRACTORS: dict[str, ImpactExtractor] = {}


def register_impact(rule_id: str) -> Callable[[ImpactExtractor], ImpactExtractor]:
    """Decorator to register an impact extractor for a rule_id."""

    def decorator(func: ImpactExtractor) -> ImpactExtractor:
        _IMPACT_EXTRACTORS[rule_id] = func
        return func

    return decorator


def get_impact(rule_id: str, evidence: dict[str, Any]) -> float:
    """Look up and call the impact extractor for a rule_id.

    Returns DEFAULT_IMPACT if no extractor is registered or if the
    extractor raises an exception. Result is clamped to [0.0, 1.0].

    Threat mitigation T-05-01: all numeric values from evidence dicts
    are validated via safe_float() inside extractors, and the final
    result is clamped here.
    """
    extractor = _IMPACT_EXTRACTORS.get(rule_id)
    if extractor is None:
        return DEFAULT_IMPACT
    try:
        result = float(extractor(evidence))
    except (TypeError, ValueError, ZeroDivisionError):
        return DEFAULT_IMPACT
    # Guard NaN from propagating
    if math.isnan(result):
        return DEFAULT_IMPACT
    return max(0.0, min(1.0, result))


# ── Per-rule impact extractors ───────────────────────────────────────────


@register_impact("R1")
def _r1_missing_stats(evidence: dict[str, Any]) -> float:
    """R1: Stats presence is binary — no quantifiable gradient."""
    return DEFAULT_IMPACT


@register_impact("R2")
def _r2_partition_pruning(evidence: dict[str, Any]) -> float:
    """R2: Partition pruning failure is binary from plan evidence.

    The rule's evidence dict contains filter_predicate and table but no
    byte-level scan metrics, so we default to 0.5.
    """
    return DEFAULT_IMPACT


@register_impact("R3")
def _r3_predicate_pushdown(evidence: dict[str, Any]) -> float:
    """R3: Pushdown failure is binary — no quantifiable gradient."""
    return DEFAULT_IMPACT


@register_impact("R4")
def _r4_dynamic_filtering(evidence: dict[str, Any]) -> float:
    """R4: Dynamic filtering not applied is high impact.

    Fixed at 0.7 because DF failures typically cause significant extra I/O,
    but the exact waste is not measurable from plan evidence alone.
    """
    return 0.7


@register_impact("R5")
def _r5_broadcast_too_big(evidence: dict[str, Any]) -> float:
    """R5: min(1.0, build_side_estimated_bytes / threshold_bytes).

    Evidence keys from r5_broadcast_too_big.py:
      - build_side_estimated_bytes: estimated size of broadcast side
      - threshold_bytes: configured broadcast threshold
    """
    build_bytes = safe_float(evidence.get("build_side_estimated_bytes"))
    threshold = safe_float(evidence.get("threshold_bytes"))
    if build_bytes is None or threshold is None or threshold <= 0:
        return DEFAULT_IMPACT
    return min(1.0, build_bytes / threshold)


@register_impact("R6")
def _r6_join_order(evidence: dict[str, Any]) -> float:
    """R6: Join order is complex; confidence already accounts for severity."""
    return DEFAULT_IMPACT


@register_impact("R7")
def _r7_cpu_skew(evidence: dict[str, Any]) -> float:
    """R7: (skew_ratio - 5.0) / 15.0, clamped [0, 1].

    Evidence keys from r7_cpu_skew.py:
      - skew_ratio: p99/p50 CPU time ratio across workers

    Maps 5x (threshold) to 0.0 impact, 20x (extreme) to 1.0.
    """
    ratio = safe_float(evidence.get("skew_ratio"))
    if ratio is None:
        return DEFAULT_IMPACT
    return (ratio - 5.0) / 15.0


@register_impact("R8")
def _r8_exchange_volume(evidence: dict[str, Any]) -> float:
    """R8: (ratio - 1.0) / 9.0, clamped [0, 1].

    Evidence keys from r8_exchange_volume.py:
      - ratio: exchange_bytes / scan_bytes

    Maps 1.0 (no waste) to 0.0 impact, 10.0 (extreme) to 1.0.
    """
    ratio = safe_float(evidence.get("ratio"))
    if ratio is None:
        return DEFAULT_IMPACT
    return (ratio - 1.0) / 9.0


@register_impact("R9")
def _r9_low_selectivity(evidence: dict[str, Any]) -> float:
    """R9: 1.0 - selectivity_ratio.

    Evidence keys from r9_low_selectivity.py:
      - selectivity_ratio: output_bytes / input_bytes

    Lower selectivity = higher impact (more bytes wasted).
    """
    selectivity = safe_float(evidence.get("selectivity_ratio"))
    if selectivity is None:
        return DEFAULT_IMPACT
    return 1.0 - selectivity


@register_impact("I1")
def _i1_small_files(evidence: dict[str, Any]) -> float:
    """I1: 1.0 - min(1.0, median_file_size_bytes / threshold_bytes).

    Evidence keys from i1_small_files.py:
      - median_file_size_bytes: median data file size
      - threshold_bytes: configured small file threshold

    Smaller files = higher impact.
    """
    median = safe_float(evidence.get("median_file_size_bytes"))
    threshold = safe_float(evidence.get("threshold_bytes"))
    if median is None or threshold is None or threshold <= 0:
        return DEFAULT_IMPACT
    return 1.0 - min(1.0, median / threshold)


@register_impact("I3")
def _i3_delete_files(evidence: dict[str, Any]) -> float:
    """I3: min(1.0, delete_ratio / 0.5).

    Evidence keys from i3_delete_files.py:
      - delete_ratio: delete_records / data_records

    Maps 0% to 0.0 impact, 50%+ to 1.0 (extreme delete burden).
    """
    ratio = safe_float(evidence.get("delete_ratio"))
    if ratio is None:
        return DEFAULT_IMPACT
    return min(1.0, ratio / 0.5)


@register_impact("I6")
def _i6_stale_snapshots(evidence: dict[str, Any]) -> float:
    """I6: min(1.0, snapshot_count / (threshold_count * 5)).

    Evidence keys from i6_stale_snapshots.py:
      - snapshot_count: number of snapshots
      - threshold_count: configured max snapshot count

    Maps threshold to 0.2 impact, 5x threshold to 1.0.
    """
    count = safe_float(evidence.get("snapshot_count"))
    threshold = safe_float(evidence.get("threshold_count"))
    if count is None or threshold is None or threshold <= 0:
        return DEFAULT_IMPACT
    return min(1.0, count / (threshold * 5))


@register_impact("I8")
def _i8_partition_transform(evidence: dict[str, Any]) -> float:
    """I8: Binary impact — confidence already low at 0.6."""
    return DEFAULT_IMPACT


@register_impact("D11")
def _d11_cost_vs_actual(evidence: dict[str, Any]) -> float:
    """D11: (divergence_factor - 5.0) / 45.0, clamped [0, 1].

    Evidence keys from d11_cost_vs_actual.py:
      - divergence_factor: max(estimated/actual, actual/estimated), magnitude >= 1.0

    Maps 5x (threshold) to 0.0 impact, 50x (extreme) to 1.0.
    """
    factor = safe_float(evidence.get("divergence_factor"))
    if factor is None:
        return DEFAULT_IMPACT
    return (factor - 5.0) / 45.0


__all__ = [
    "DEFAULT_IMPACT",
    "get_impact",
    "register_impact",
]
