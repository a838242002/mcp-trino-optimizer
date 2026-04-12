"""I3 DeleteFiles — fires when Iceberg table has excessive delete-file accumulation.

Delete files (positional and equality) accumulate over DML operations and cause
read amplification: every data file scan must merge matching delete records.

Two detection paths:
  1. Count-based: total delete files (content IN (1,2)) > delete_file_count_threshold
  2. Ratio-based: delete record count / data record count > delete_ratio_threshold

Evidence: ICEBERG_METADATA — requires CatalogSource. Engine emits RuleSkipped
when catalog_source is None (offline mode).

Note: This rule uses the $files metadata table workaround, NOT $partitions.
$partitions does not expose delete metrics in Trino (Trino issue #28910):
  github.com/trinodb/trino/issues/28910
The $files table has the content column (0=DATA, 1=POSITION_DELETES,
2=EQUALITY_DELETES) and record_count which gives us both count and ratio signals.
"""

from __future__ import annotations

from typing import Any

from mcp_trino_optimizer.parser.models import BasePlan
from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement
from mcp_trino_optimizer.rules.findings import RuleFinding
from mcp_trino_optimizer.rules.registry import registry
from mcp_trino_optimizer.rules.thresholds import RuleThresholds

# Iceberg $files content column values (Iceberg spec §4.3):
#   0 = DATA file
#   1 = POSITION_DELETES file
#   2 = EQUALITY_DELETES file
_CONTENT_DATA = 0
_CONTENT_POSITION_DELETES = 1
_CONTENT_EQUALITY_DELETES = 2
_DELETE_CONTENT_VALUES = frozenset({_CONTENT_POSITION_DELETES, _CONTENT_EQUALITY_DELETES})


class I3DeleteFiles(Rule):
    """I3: Iceberg table has excessive delete-file accumulation.

    Uses $files cross-reference (Trino issue #28910 workaround: $partitions lacks
    delete metrics). Filters content IN (1, 2) client-side after fetching $files rows.

    Emits separate findings for:
      - Count-based trigger: delete_file_count > threshold
      - Ratio-based trigger: delete_records / data_records > threshold
    """

    rule_id = "I3"
    evidence_requirement = EvidenceRequirement.ICEBERG_METADATA

    def __init__(self, thresholds: RuleThresholds | None = None) -> None:
        self._thresholds = thresholds or RuleThresholds()

    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:
        """Detect delete-file accumulation from $files metadata."""
        if not evidence.iceberg_files:
            return []

        files = evidence.iceberg_files

        # Partition files into delete vs data — T-04-17 guard: `in` handles None/wrong type
        delete_files = [f for f in files if f.get("content") in _DELETE_CONTENT_VALUES]
        data_files = [f for f in files if f.get("content") == _CONTENT_DATA]

        pos_delete_count = sum(1 for f in delete_files if f.get("content") == _CONTENT_POSITION_DELETES)
        eq_delete_count = sum(1 for f in delete_files if f.get("content") == _CONTENT_EQUALITY_DELETES)
        delete_file_count = len(delete_files)
        data_file_count = len(data_files)

        delete_records = sum(f.get("record_count", 0) for f in delete_files)
        data_records = sum(f.get("record_count", 0) for f in data_files)
        delete_ratio = delete_records / data_records if data_records > 0 else 0.0

        # Track metadata truncation (Pitfall 7)
        metadata_truncated = len(files) >= self._thresholds.max_metadata_rows

        # Shared evidence payload for both finding types
        shared_evidence: dict[str, Any] = {
            "position_delete_count": pos_delete_count,
            "equality_delete_count": eq_delete_count,
            "delete_file_count": delete_file_count,
            "data_file_count": data_file_count,
            "delete_records": delete_records,
            "data_records": data_records,
            "delete_ratio": delete_ratio,
        }
        if metadata_truncated:
            shared_evidence["metadata_truncated"] = True

        findings: list[RuleFinding] = []

        # ── Check 1: Count-based ──────────────────────────────────────────────
        if delete_file_count > self._thresholds.delete_file_count_threshold:
            findings.append(
                RuleFinding(
                    rule_id="I3",
                    severity="high",
                    confidence=0.95,
                    message=(
                        f"Iceberg table has {delete_file_count:,} delete files "
                        f"({pos_delete_count:,} positional, {eq_delete_count:,} equality) — "
                        f"exceeds threshold of {self._thresholds.delete_file_count_threshold:,}. "
                        "Run OPTIMIZE to compact delete files and reduce read amplification."
                    ),
                    evidence=shared_evidence,
                    operator_ids=[],
                )
            )

        # ── Check 2: Ratio-based ──────────────────────────────────────────────
        if data_records > 0 and delete_ratio > self._thresholds.delete_ratio_threshold:
            findings.append(
                RuleFinding(
                    rule_id="I3",
                    severity="high",
                    confidence=0.95,
                    message=(
                        f"Iceberg delete records ({delete_records:,}) are "
                        f"{delete_ratio:.1%} of data records ({data_records:,}) — "
                        f"exceeds {self._thresholds.delete_ratio_threshold:.0%} ratio threshold. "
                        "High delete ratio causes excessive merge overhead during scans."
                    ),
                    evidence=shared_evidence,
                    operator_ids=[],
                )
            )

        return findings


registry.register(I3DeleteFiles)
