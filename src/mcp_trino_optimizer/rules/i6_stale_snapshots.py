"""I6 StaleSnapshots — fires when Iceberg table has stale snapshot accumulation.

Stale snapshots cause:
  - Metadata scan overhead on every query (Iceberg table-scan reads all manifests)
  - Slow metadata list operations (manifest file count grows linearly with snapshots)
  - Potential OOM in the metadata layer for very wide tables

Two detection paths:
  1. Count-based: snapshot_count > max_snapshot_count threshold (default 50)
  2. Age-based: oldest snapshot age > snapshot_retention_days (default 30)

Evidence: ICEBERG_METADATA — requires CatalogSource. Engine emits RuleSkipped
when catalog_source is None (offline mode).

References:
  - Iceberg table spec §4: snapshot accumulation without expiry causes metadata overhead
  - Iceberg write.metadata.delete-after-commit.enabled default (30 days)
    (iceberg.apache.org/docs/latest/configuration/#write-properties)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mcp_trino_optimizer.parser.models import BasePlan
from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement
from mcp_trino_optimizer.rules.findings import RuleFinding
from mcp_trino_optimizer.rules.registry import registry
from mcp_trino_optimizer.rules.thresholds import RuleThresholds


def _parse_committed_at(raw: str) -> datetime | None:
    """Parse a Trino $snapshots committed_at string to a UTC datetime.

    Trino returns timestamps as "YYYY-MM-DD HH:MM:SS.mmm UTC" or
    "YYYY-MM-DD HH:MM:SS UTC". Handles both formats by replacing " UTC"
    with "+00:00" for fromisoformat().

    Returns None if parsing fails (T-04-14: don't crash on unexpected formats).
    """
    try:
        normalized = raw.strip().replace(" UTC", "+00:00")
        return datetime.fromisoformat(normalized)
    except (ValueError, AttributeError):
        return None


class I6StaleSnapshots(Rule):
    """I6: Iceberg table has stale snapshot accumulation.

    Fires via one or both detection paths:
      - Count path: snapshot_count > max_snapshot_count
      - Age path: oldest snapshot > snapshot_retention_days

    Each triggered path produces a separate RuleFinding so callers can act on
    the specific signal (expire-all vs expire-old).
    """

    rule_id = "I6"
    evidence_requirement = EvidenceRequirement.ICEBERG_METADATA

    def __init__(self, thresholds: RuleThresholds | None = None) -> None:
        self._thresholds = thresholds or RuleThresholds()

    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:
        """Detect stale snapshot accumulation from $snapshots metadata."""
        if not evidence.iceberg_snapshots:
            return []

        snapshots = evidence.iceberg_snapshots
        snapshot_count = len(snapshots)

        # Parse committed_at for each row; skip rows with unparseable timestamps
        parsed_times: list[datetime] = []
        for snap in snapshots:
            raw_ts = snap.get("committed_at", "")
            if raw_ts:
                dt = _parse_committed_at(str(raw_ts))
                if dt is not None:
                    parsed_times.append(dt)

        now = datetime.now(UTC)
        oldest_age_days = 0
        if parsed_times:
            oldest_dt = min(parsed_times)
            oldest_age_days = (now - oldest_dt).days

        # Shared evidence payload
        shared_evidence: dict[str, Any] = {
            "snapshot_count": snapshot_count,
            "threshold_count": self._thresholds.max_snapshot_count,
            "oldest_snapshot_age_days": oldest_age_days,
            "threshold_days": self._thresholds.snapshot_retention_days,
        }

        findings: list[RuleFinding] = []

        # ── Check 1: Snapshot count ───────────────────────────────────────────
        if snapshot_count > self._thresholds.max_snapshot_count:
            findings.append(
                RuleFinding(
                    rule_id="I6",
                    severity="medium",
                    confidence=0.9,
                    message=(
                        f"Iceberg table has {snapshot_count:,} snapshots — exceeds threshold "
                        f"of {self._thresholds.max_snapshot_count:,}. "
                        "Run CALL system.expire_snapshots() to reduce metadata overhead."
                    ),
                    evidence=shared_evidence,
                    operator_ids=[],
                )
            )

        # ── Check 2: Oldest snapshot age ─────────────────────────────────────
        if oldest_age_days > self._thresholds.snapshot_retention_days:
            findings.append(
                RuleFinding(
                    rule_id="I6",
                    severity="low",
                    confidence=0.9,
                    message=(
                        f"Iceberg table's oldest snapshot is {oldest_age_days} days old — "
                        f"exceeds retention threshold of {self._thresholds.snapshot_retention_days} days. "
                        "Run CALL system.expire_snapshots(retention_threshold => INTERVAL '30' DAY) "
                        "to remove expired snapshots."
                    ),
                    evidence=shared_evidence,
                    operator_ids=[],
                )
            )

        return findings


registry.register(I6StaleSnapshots)
