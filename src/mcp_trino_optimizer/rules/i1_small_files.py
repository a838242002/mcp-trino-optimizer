"""I1 SmallFiles — fires when Iceberg table has too many small data files.

Small files cause excessive split planning overhead, slow metadata reads, and
underutilized CPU on workers. Two detection paths:
  1. Plan-based: iceberg_split_count on ExecutedPlan scan nodes > threshold
  2. Metadata-based: median data file size (content=0) < small_file_bytes threshold

Evidence: ICEBERG_METADATA — requires CatalogSource. Engine emits RuleSkipped
when catalog_source is None (offline mode).

References:
  - Iceberg best-practices: target 128MB-512MB files; <16MB is considered small
    (iceberg.apache.org/docs/latest/maintenance/#rewrite-data-files)
  - Trino adaptive query planner benchmarks: >10k splits causes planning overhead
"""

from __future__ import annotations

import statistics
from typing import Any

from mcp_trino_optimizer.parser.models import BasePlan
from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement
from mcp_trino_optimizer.rules.findings import RuleFinding
from mcp_trino_optimizer.rules.registry import registry
from mcp_trino_optimizer.rules.thresholds import RuleThresholds

_SCAN_TYPES = frozenset({"TableScan", "ScanFilter", "ScanFilterProject"})


def _median_file_size(files: list[dict[str, Any]]) -> float | None:
    """Compute median file_size_in_bytes for DATA files (content==0).

    Excludes delete files (content=1 or 2) from the calculation so that
    small delete files do not inflate the small-file signal.

    Returns None if there are no data files.
    """
    sizes: list[float] = [
        float(f["file_size_in_bytes"])
        for f in files
        if f.get("content") == 0 and isinstance(f.get("file_size_in_bytes"), (int, float))
    ]
    if not sizes:
        return None
    return statistics.median(sizes)


class I1SmallFiles(Rule):
    """I1: Iceberg table has too many small files.

    Fires via one or both detection paths:
      - Split count path (ExecutedPlan): iceberg_split_count > threshold on scan nodes
      - Metadata path: median data file size < small_file_bytes threshold

    Both paths can fire simultaneously; each produces a separate RuleFinding.
    """

    rule_id = "I1"
    evidence_requirement = EvidenceRequirement.ICEBERG_METADATA

    def __init__(self, thresholds: RuleThresholds | None = None) -> None:
        self._thresholds = thresholds or RuleThresholds()

    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:
        """Detect small-file conditions via split count and/or file metadata."""
        findings: list[RuleFinding] = []

        # ── Path 1: Split-count from plan (requires ExecutedPlan metrics) ─────
        for node in plan.walk():
            if node.operator_type not in _SCAN_TYPES:
                continue
            split_count = node.iceberg_split_count
            if split_count is None:
                continue
            if split_count > self._thresholds.small_file_split_count_threshold:
                findings.append(
                    RuleFinding(
                        rule_id="I1",
                        severity="high",
                        confidence=0.9,
                        message=(
                            f"Scan node '{node.operator_type}' (id={node.id}) read "
                            f"{split_count:,} Iceberg splits — exceeds threshold of "
                            f"{self._thresholds.small_file_split_count_threshold:,}. "
                            "Large split counts indicate small-file fragmentation and "
                            "cause excessive planning and scheduling overhead."
                        ),
                        evidence={
                            "iceberg_split_count": split_count,
                            "threshold": self._thresholds.small_file_split_count_threshold,
                        },
                        operator_ids=[node.id],
                    )
                )

        # ── Path 2: Median file size from $files metadata ─────────────────────
        if evidence.iceberg_files is not None:
            data_files = [f for f in evidence.iceberg_files if f.get("content") == 0]
            median = _median_file_size(evidence.iceberg_files)
            if median is not None and median < self._thresholds.small_file_bytes:
                findings.append(
                    RuleFinding(
                        rule_id="I1",
                        severity="high",
                        confidence=0.95,
                        message=(
                            f"Iceberg table has {len(data_files):,} data files with median "
                            f"size {median / (1024*1024):.1f} MB — below the "
                            f"{self._thresholds.small_file_bytes // (1024*1024)} MB threshold. "
                            "Run OPTIMIZE or Iceberg rewrite_data_files() to compact."
                        ),
                        evidence={
                            "data_file_count": len(data_files),
                            "median_file_size_bytes": median,
                            "threshold_bytes": self._thresholds.small_file_bytes,
                        },
                        operator_ids=[],
                    )
                )

        return findings


registry.register(I1SmallFiles)
