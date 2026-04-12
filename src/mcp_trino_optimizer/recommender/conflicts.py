"""Conflict resolution for competing rule findings (D-04, D-05).

When multiple rules fire on the same operator, only the highest-quality
finding should become a recommendation. The loser is preserved in
``considered_but_rejected`` for auditability.

Declared conflict pairs:
  R1 <-> D11 (stats vs. cost divergence)
  R2 <-> R9  (partition pruning vs. low selectivity)
  R5 <-> R8  (broadcast too big vs. exchange volume)

Resolution order: confidence (higher wins) -> severity (higher wins)
-> rule_id (alphabetically lower wins, tiebreaker).
"""

from __future__ import annotations

from typing import NamedTuple

from mcp_trino_optimizer.recommender.models import ConsideredButRejected
from mcp_trino_optimizer.recommender.scoring import SEVERITY_WEIGHTS
from mcp_trino_optimizer.rules.findings import RuleFinding


class ScoredFinding(NamedTuple):
    """A RuleFinding paired with its computed priority_score."""

    finding: RuleFinding
    priority_score: float


CONFLICT_PAIRS: dict[str, set[str]] = {
    "R1": {"D11"},
    "D11": {"R1"},
    "R2": {"R9"},
    "R9": {"R2"},
    "R5": {"R8"},
    "R8": {"R5"},
}
"""Bidirectional declared conflict pairs.

When two rules from the same pair fire on the same operator (or in the
same 'analysis group' for Iceberg rules), only the winner survives.
"""


def _operator_group_key(operator_ids: list[str]) -> str:
    """Build a hashable group key from operator_ids.

    Empty operator_ids (Iceberg table-level rules) all map to the same
    sentinel group so they are resolved together as 'same analysis'.
    """
    if not operator_ids:
        return "__iceberg_analysis__"
    return ",".join(sorted(operator_ids))


def _pick_winner(a: ScoredFinding, b: ScoredFinding) -> tuple[ScoredFinding, ScoredFinding]:
    """Return (winner, loser) between two conflicting scored findings.

    Resolution order per D-04:
      1. Higher confidence wins.
      2. On tie: higher severity wins (via SEVERITY_WEIGHTS).
      3. On tie: alphabetically lower rule_id wins (tiebreaker).
    """
    fa, fb = a.finding, b.finding

    # 1. Confidence
    if fa.confidence != fb.confidence:
        return (a, b) if fa.confidence > fb.confidence else (b, a)

    # 2. Severity weight
    wa = SEVERITY_WEIGHTS.get(fa.severity, 0)
    wb = SEVERITY_WEIGHTS.get(fb.severity, 0)
    if wa != wb:
        return (a, b) if wa > wb else (b, a)

    # 3. Alphabetical rule_id (lower wins)
    if fa.rule_id <= fb.rule_id:
        return (a, b)
    return (b, a)


def resolve_conflicts(
    scored: list[ScoredFinding],
) -> tuple[list[ScoredFinding], list[ConsideredButRejected]]:
    """Resolve declared conflicts among scored findings.

    Groups findings by overlapping operator_ids (or 'same analysis' for
    Iceberg rules with empty operator_ids). Within each group, checks all
    pairs against CONFLICT_PAIRS and removes losers.

    Args:
        scored: List of ScoredFinding objects to resolve.

    Returns:
        Tuple of (winners, rejected). Winners retain their ScoredFinding
        for downstream processing. Rejected are ConsideredButRejected
        with an explanation string.
    """
    if not scored:
        return [], []

    # Build operator -> set of scored findings index
    # For overlap detection, each finding registers all its operator groups
    op_to_indices: dict[str, set[int]] = {}
    for idx, sf in enumerate(scored):
        key = _operator_group_key(sf.finding.operator_ids)
        # For multi-operator findings, also register each individual op
        if sf.finding.operator_ids:
            for op_id in sf.finding.operator_ids:
                op_to_indices.setdefault(op_id, set()).add(idx)
        # Register the full group key too (for the iceberg sentinel)
        op_to_indices.setdefault(key, set()).add(idx)

    # Find all conflict pairs that share at least one operator
    rejected_indices: set[int] = set()
    rejected_list: list[ConsideredButRejected] = []

    for _key, indices in op_to_indices.items():
        idx_list = sorted(indices)
        for i_pos in range(len(idx_list)):
            for j_pos in range(i_pos + 1, len(idx_list)):
                i_idx, j_idx = idx_list[i_pos], idx_list[j_pos]
                if i_idx in rejected_indices or j_idx in rejected_indices:
                    continue

                sf_a, sf_b = scored[i_idx], scored[j_idx]
                rid_a, rid_b = sf_a.finding.rule_id, sf_b.finding.rule_id

                # Check if this pair is a declared conflict
                conflicts_a = CONFLICT_PAIRS.get(rid_a, set())
                if rid_b not in conflicts_a:
                    continue

                winner, loser = _pick_winner(sf_a, sf_b)
                loser_idx = i_idx if loser is sf_a else j_idx
                rejected_indices.add(loser_idx)
                rejected_list.append(
                    ConsideredButRejected(
                        rule_id=loser.finding.rule_id,
                        reason=(
                            f"Superseded by {winner.finding.rule_id} "
                            f"(confidence={winner.finding.confidence}, "
                            f"severity={winner.finding.severity}) "
                            f"on shared operator(s)"
                        ),
                        original_priority_score=loser.priority_score,
                    )
                )

    winners = [sf for idx, sf in enumerate(scored) if idx not in rejected_indices]
    return winners, rejected_list


__all__ = [
    "CONFLICT_PAIRS",
    "ScoredFinding",
    "resolve_conflicts",
]
