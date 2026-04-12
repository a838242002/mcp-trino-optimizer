"""I1 SmallFiles rule tests.

Three fixture classes:
  1. Synthetic-minimum: minimal inputs that just trigger the rule
  2. Realistic: fabricated file lists with mixed sizes
  3. Negative-control: inputs that must NOT trigger the rule
"""

from __future__ import annotations

from mcp_trino_optimizer.parser.models import BasePlan, EstimatedPlan, ExecutedPlan, PlanNode
from mcp_trino_optimizer.rules.evidence import EvidenceBundle
from mcp_trino_optimizer.rules.i1_small_files import I1SmallFiles
from mcp_trino_optimizer.rules.thresholds import RuleThresholds

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_scan_node(
    node_id: str = "1",
    iceberg_split_count: int | None = None,
    iceberg_file_count: int | None = None,
) -> PlanNode:
    return PlanNode(
        id=node_id,
        name="TableScan",
        descriptor={"table": "iceberg:analytics.orders"},
        iceberg_split_count=iceberg_split_count,
        iceberg_file_count=iceberg_file_count,
    )


def _make_estimated_plan(scan_node: PlanNode | None = None) -> EstimatedPlan:
    node = scan_node or _make_scan_node()
    return EstimatedPlan(root=node)


def _make_executed_plan(scan_node: PlanNode | None = None) -> ExecutedPlan:
    node = scan_node or _make_scan_node()
    return ExecutedPlan(root=node)


def _data_file(size_bytes: int, record_count: int = 1000) -> dict:  # type: ignore[type-arg]
    return {
        "content": 0,
        "file_path": f"s3://bucket/data_{size_bytes}.parquet",
        "file_format": "PARQUET",
        "record_count": record_count,
        "file_size_in_bytes": size_bytes,
    }


def _delete_file(size_bytes: int = 4096, content: int = 1) -> dict:  # type: ignore[type-arg]
    return {
        "content": content,
        "file_path": f"s3://bucket/delete_{size_bytes}.parquet",
        "file_format": "PARQUET",
        "record_count": 100,
        "file_size_in_bytes": size_bytes,
    }


def _bundle(plan: BasePlan, files: list[dict] | None = None) -> EvidenceBundle:  # type: ignore[type-arg]
    return EvidenceBundle(plan=plan, iceberg_files=files)


# ── Synthetic-minimum: fires via iceberg_files ────────────────────────────────


def test_fires_via_small_files_median() -> None:
    """200 data files all at 8MB (< 16MB threshold). I1 fires."""
    plan = _make_estimated_plan()
    mb8 = 8 * 1024 * 1024
    files = [_data_file(mb8) for _ in range(200)]
    bundle = _bundle(plan, files)

    rule = I1SmallFiles()
    findings = rule.check(plan, bundle)

    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "I1"
    assert f.severity == "high"
    assert f.confidence > 0.0
    assert "median_file_size_bytes" in f.evidence
    assert f.evidence["median_file_size_bytes"] < 16 * 1024 * 1024


def test_fires_via_split_count_threshold() -> None:
    """Scan node with iceberg_split_count=15_000 (> 10_000 threshold). I1 fires."""
    scan = _make_scan_node(iceberg_split_count=15_000)
    plan = _make_executed_plan(scan)
    # No iceberg_files in bundle — plan-based path only
    bundle = _bundle(plan, files=None)

    rule = I1SmallFiles()
    findings = rule.check(plan, bundle)

    assert len(findings) >= 1
    rule_ids = {f.rule_id for f in findings}
    assert "I1" in rule_ids
    split_findings = [f for f in findings if "iceberg_split_count" in f.evidence]
    assert len(split_findings) == 1
    assert split_findings[0].evidence["iceberg_split_count"] == 15_000


# ── Synthetic: fires via large split count on ExecutedPlan ────────────────────


def test_fires_at_split_count_boundary() -> None:
    """Exactly above threshold (10_001) — fires."""
    scan = _make_scan_node(iceberg_split_count=10_001)
    plan = _make_executed_plan(scan)
    bundle = _bundle(plan, files=None)

    rule = I1SmallFiles(thresholds=RuleThresholds(small_file_split_count_threshold=10_000))
    findings = rule.check(plan, bundle)

    split_findings = [f for f in findings if "iceberg_split_count" in f.evidence]
    assert len(split_findings) == 1


def test_both_paths_can_fire_simultaneously() -> None:
    """Large split count + small files in bundle: both findings emitted."""
    scan = _make_scan_node(iceberg_split_count=20_000)
    plan = _make_executed_plan(scan)
    mb4 = 4 * 1024 * 1024
    files = [_data_file(mb4) for _ in range(100)]
    bundle = _bundle(plan, files)

    rule = I1SmallFiles()
    findings = rule.check(plan, bundle)

    # Should have both a split-count finding and a file-size finding
    assert len(findings) == 2
    has_split = any("iceberg_split_count" in f.evidence for f in findings)
    has_size = any("median_file_size_bytes" in f.evidence for f in findings)
    assert has_split
    assert has_size


# ── Negative-control: does NOT fire ──────────────────────────────────────────


def test_negative_good_file_size() -> None:
    """Files at 200MB >> 16MB threshold. I1 returns []."""
    plan = _make_estimated_plan()
    mb200 = 200 * 1024 * 1024
    files = [_data_file(mb200) for _ in range(50)]
    bundle = _bundle(plan, files)

    rule = I1SmallFiles()
    findings = rule.check(plan, bundle)

    assert findings == []


def test_negative_low_split_count() -> None:
    """split_count=500, large files. I1 returns []."""
    scan = _make_scan_node(iceberg_split_count=500)
    plan = _make_executed_plan(scan)
    mb200 = 200 * 1024 * 1024
    files = [_data_file(mb200) for _ in range(10)]
    bundle = _bundle(plan, files)

    rule = I1SmallFiles()
    findings = rule.check(plan, bundle)

    assert findings == []


def test_negative_no_files_no_split_count() -> None:
    """No iceberg_files, no split count. I1 returns []."""
    plan = _make_estimated_plan()
    bundle = _bundle(plan, files=None)

    rule = I1SmallFiles()
    findings = rule.check(plan, bundle)

    assert findings == []


def test_negative_delete_files_excluded_from_median() -> None:
    """Delete files (content=1,2) should NOT be included in median calculation.

    Mix: 5 delete files at 1KB + 100 data files at 200MB.
    Median of DATA files = 200MB >> threshold. I1 should NOT fire.
    """
    plan = _make_estimated_plan()
    mb200 = 200 * 1024 * 1024
    kb1 = 1024
    files = [_data_file(mb200) for _ in range(100)] + [_delete_file(kb1) for _ in range(5)]
    bundle = _bundle(plan, files)

    rule = I1SmallFiles()
    findings = rule.check(plan, bundle)

    # Only data files matter for median; delete files should be excluded
    size_findings = [f for f in findings if "median_file_size_bytes" in f.evidence]
    assert len(size_findings) == 0


def test_negative_split_count_at_threshold() -> None:
    """Exactly AT threshold = does not fire (threshold is >, not >=)."""
    scan = _make_scan_node(iceberg_split_count=10_000)
    plan = _make_executed_plan(scan)
    bundle = _bundle(plan, files=None)

    rule = I1SmallFiles(thresholds=RuleThresholds(small_file_split_count_threshold=10_000))
    findings = rule.check(plan, bundle)

    split_findings = [f for f in findings if "iceberg_split_count" in f.evidence]
    assert len(split_findings) == 0


# ── Realistic: mixed file sizes ───────────────────────────────────────────────


def test_realistic_mixed_sizes_fires() -> None:
    """40 files at 5MB, 10 files at 300MB. Median of 50 data files ≈ 5MB < 16MB. I1 fires."""
    plan = _make_estimated_plan()
    mb5 = 5 * 1024 * 1024
    mb300 = 300 * 1024 * 1024
    files = [_data_file(mb5) for _ in range(40)] + [_data_file(mb300) for _ in range(10)]
    bundle = _bundle(plan, files)

    rule = I1SmallFiles()
    findings = rule.check(plan, bundle)

    size_findings = [f for f in findings if "median_file_size_bytes" in f.evidence]
    assert len(size_findings) == 1
    # Verify the median is indeed small (40/50 = 80% small files so median is 5MB)
    assert size_findings[0].evidence["median_file_size_bytes"] < 16 * 1024 * 1024


def test_evidence_fields_present() -> None:
    """Metadata-path finding must contain all documented evidence fields."""
    plan = _make_estimated_plan()
    mb5 = 5 * 1024 * 1024
    files = [_data_file(mb5) for _ in range(50)]
    bundle = _bundle(plan, files)

    rule = I1SmallFiles()
    findings = rule.check(plan, bundle)

    assert len(findings) == 1
    ev = findings[0].evidence
    assert "data_file_count" in ev
    assert "median_file_size_bytes" in ev
    assert "threshold_bytes" in ev
    assert ev["threshold_bytes"] == 16 * 1024 * 1024


def test_split_count_evidence_fields_present() -> None:
    """Split-count finding must contain all documented evidence fields."""
    scan = _make_scan_node(iceberg_split_count=50_000)
    plan = _make_executed_plan(scan)
    bundle = _bundle(plan, files=None)

    rule = I1SmallFiles()
    findings = rule.check(plan, bundle)

    split_findings = [f for f in findings if "iceberg_split_count" in f.evidence]
    assert len(split_findings) == 1
    ev = split_findings[0].evidence
    assert "iceberg_split_count" in ev
    assert "threshold" in ev
    assert ev["threshold"] == 10_000
