"""I3 DeleteFiles rule tests.

Three fixture classes:
  1. Synthetic-minimum: minimal inputs that just trigger the rule
  2. Realistic: fabricated file lists with mixed delete/data files
  3. Negative-control: inputs that must NOT trigger the rule
"""

from __future__ import annotations

from mcp_trino_optimizer.parser.models import BasePlan, EstimatedPlan, PlanNode
from mcp_trino_optimizer.rules.evidence import EvidenceBundle
from mcp_trino_optimizer.rules.i3_delete_files import I3DeleteFiles

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_plan() -> EstimatedPlan:
    return EstimatedPlan(
        root=PlanNode(
            id="1",
            name="TableScan",
            descriptor={"table": "iceberg:analytics.orders"},
        )
    )


def _data_file(record_count: int = 100_000, size_bytes: int = 128 * 1024 * 1024) -> dict:  # type: ignore[type-arg]
    return {
        "content": 0,
        "file_path": "s3://bucket/data.parquet",
        "file_format": "PARQUET",
        "record_count": record_count,
        "file_size_in_bytes": size_bytes,
    }


def _pos_delete_file(record_count: int = 1000, size_bytes: int = 4096) -> dict:  # type: ignore[type-arg]
    return {
        "content": 1,
        "file_path": "s3://bucket/pos-delete.parquet",
        "file_format": "PARQUET",
        "record_count": record_count,
        "file_size_in_bytes": size_bytes,
    }


def _eq_delete_file(record_count: int = 1000, size_bytes: int = 4096) -> dict:  # type: ignore[type-arg]
    return {
        "content": 2,
        "file_path": "s3://bucket/eq-delete.parquet",
        "file_format": "PARQUET",
        "record_count": record_count,
        "file_size_in_bytes": size_bytes,
    }


def _bundle(plan: BasePlan, files: list[dict] | None) -> EvidenceBundle:  # type: ignore[type-arg]
    return EvidenceBundle(plan=plan, iceberg_files=files)


# ── Synthetic-minimum: fires on delete file count ────────────────────────────


def test_fires_on_count_threshold() -> None:
    """120 position delete files + 20 data files. delete_count=120 > 100. I3 fires."""
    plan = _make_plan()
    files = [_pos_delete_file() for _ in range(120)] + [_data_file() for _ in range(20)]
    bundle = _bundle(plan, files)

    rule = I3DeleteFiles()
    findings = rule.check(plan, bundle)

    assert len(findings) >= 1
    assert any(f.rule_id == "I3" for f in findings)
    count_findings = [f for f in findings if "delete_file_count" in f.evidence]
    assert len(count_findings) >= 1
    assert count_findings[0].severity == "high"


def test_fires_on_equality_delete_files() -> None:
    """Equality delete files (content=2) also trigger the rule."""
    plan = _make_plan()
    files = [_eq_delete_file() for _ in range(105)] + [_data_file() for _ in range(10)]
    bundle = _bundle(plan, files)

    rule = I3DeleteFiles()
    findings = rule.check(plan, bundle)

    assert any(f.rule_id == "I3" for f in findings)


def test_fires_on_delete_record_ratio() -> None:
    """50 delete-file rows with record_count=50_000 + 10 data rows record_count=100_000.

    delete_records=2_500_000, data_records=1_000_000 -> ratio=2.5 > 0.10 threshold.
    I3 fires (even though count < 100 threshold).
    """
    plan = _make_plan()
    # 50 delete files, each with 50_000 records
    files = [_pos_delete_file(record_count=50_000) for _ in range(50)]
    # 10 data files, each with 100_000 records
    files += [_data_file(record_count=100_000) for _ in range(10)]
    bundle = _bundle(plan, files)

    rule = I3DeleteFiles()
    findings = rule.check(plan, bundle)

    ratio_findings = [f for f in findings if f.evidence.get("delete_ratio", 0) > 0.10]
    assert len(ratio_findings) >= 1
    assert any(f.rule_id == "I3" for f in ratio_findings)


# ── Negative-control: does NOT fire ──────────────────────────────────────────


def test_negative_few_delete_files() -> None:
    """5 delete files (< 100 threshold) with low record count. I3 returns []."""
    plan = _make_plan()
    files = [_pos_delete_file(record_count=100) for _ in range(5)]
    files += [_data_file(record_count=100_000) for _ in range(50)]
    bundle = _bundle(plan, files)

    rule = I3DeleteFiles()
    findings = rule.check(plan, bundle)

    assert findings == []


def test_negative_no_delete_files() -> None:
    """All content=0 (data files). I3 returns []."""
    plan = _make_plan()
    files = [_data_file() for _ in range(200)]
    bundle = _bundle(plan, files)

    rule = I3DeleteFiles()
    findings = rule.check(plan, bundle)

    assert findings == []


def test_negative_none_files() -> None:
    """iceberg_files=None. I3 returns [] (rule is defensive)."""
    plan = _make_plan()
    bundle = _bundle(plan, None)

    rule = I3DeleteFiles()
    findings = rule.check(plan, bundle)

    assert findings == []


def test_negative_empty_files_list() -> None:
    """Empty iceberg_files list. I3 returns []."""
    plan = _make_plan()
    bundle = _bundle(plan, [])

    rule = I3DeleteFiles()
    findings = rule.check(plan, bundle)

    assert findings == []


def test_negative_ratio_below_threshold() -> None:
    """5 delete files (each 1000 records) + 200 data files (each 100_000 records).

    delete_records=5_000, data_records=20_000_000 -> ratio=0.00025 << 0.10.
    Count < 100. I3 returns [].
    """
    plan = _make_plan()
    files = [_pos_delete_file(record_count=1000) for _ in range(5)]
    files += [_data_file(record_count=100_000) for _ in range(200)]
    bundle = _bundle(plan, files)

    rule = I3DeleteFiles()
    findings = rule.check(plan, bundle)

    assert findings == []


# ── Realistic: mixed file types ───────────────────────────────────────────────


def test_realistic_mixed_delete_files_fires() -> None:
    """110 position deletes + 5 equality deletes + 200 data files. I3 fires (115 > 100)."""
    plan = _make_plan()
    files = [_pos_delete_file() for _ in range(110)]
    files += [_eq_delete_file() for _ in range(5)]
    files += [_data_file() for _ in range(200)]
    bundle = _bundle(plan, files)

    rule = I3DeleteFiles()
    findings = rule.check(plan, bundle)

    assert any(f.rule_id == "I3" for f in findings)
    count_findings = [f for f in findings if "delete_file_count" in f.evidence]
    assert count_findings[0].evidence["delete_file_count"] == 115


def test_both_conditions_fire_separate_findings() -> None:
    """Both count (>100) AND ratio (>0.10) triggered — two RuleFindings emitted."""
    plan = _make_plan()
    # 120 delete files (count > 100), each with 50_000 records
    files = [_pos_delete_file(record_count=50_000) for _ in range(120)]
    # 10 data files, each with 100_000 records -> ratio = 6_000_000/1_000_000 = 6.0 > 0.10
    files += [_data_file(record_count=100_000) for _ in range(10)]
    bundle = _bundle(plan, files)

    rule = I3DeleteFiles()
    findings = rule.check(plan, bundle)

    # Should have 2 separate findings (count-based and ratio-based)
    assert len(findings) == 2
    assert all(f.rule_id == "I3" for f in findings)


def test_evidence_fields_present() -> None:
    """Finding must contain all documented evidence fields."""
    plan = _make_plan()
    files = [_pos_delete_file() for _ in range(120)] + [_data_file() for _ in range(20)]
    bundle = _bundle(plan, files)

    rule = I3DeleteFiles()
    findings = rule.check(plan, bundle)

    count_findings = [f for f in findings if "delete_file_count" in f.evidence]
    assert len(count_findings) >= 1
    ev = count_findings[0].evidence
    assert "position_delete_count" in ev
    assert "equality_delete_count" in ev
    assert "delete_file_count" in ev
    assert "data_file_count" in ev
    assert "delete_records" in ev
    assert "data_records" in ev
    assert "delete_ratio" in ev


def test_malformed_content_field_skipped() -> None:
    """Files with None or unexpected content field are skipped safely (T-04-17 guard)."""
    plan = _make_plan()
    files: list[dict] = [  # type: ignore[type-arg]
        {"content": None, "record_count": 1000, "file_size_in_bytes": 4096},
        {"content": "UNKNOWN", "record_count": 1000, "file_size_in_bytes": 4096},
    ]
    files += [_pos_delete_file() for _ in range(5)]
    bundle = _bundle(plan, files)

    rule = I3DeleteFiles()
    # Should not raise; the 5 real delete files should count
    findings = rule.check(plan, bundle)

    # 5 delete files < 100 threshold, so no findings expected
    assert findings == []
