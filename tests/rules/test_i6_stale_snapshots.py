"""I6 StaleSnapshots rule tests.

Three fixture classes:
  1. Synthetic-minimum: minimal inputs that just trigger the rule
  2. Realistic: fabricated snapshot lists with mixed ages
  3. Negative-control: inputs that must NOT trigger the rule
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from mcp_trino_optimizer.parser.models import EstimatedPlan, PlanNode
from mcp_trino_optimizer.rules.evidence import EvidenceBundle
from mcp_trino_optimizer.rules.i6_stale_snapshots import I6StaleSnapshots
from mcp_trino_optimizer.rules.thresholds import RuleThresholds

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_plan() -> EstimatedPlan:
    return EstimatedPlan(
        root=PlanNode(
            id="1",
            name="TableScan",
            descriptor={"table": "iceberg:analytics.orders"},
        )
    )


def _snapshot(days_ago: float, operation: str = "append") -> dict:  # type: ignore[type-arg]
    """Build a synthetic $snapshots row committed `days_ago` days before now."""
    dt = datetime.now(UTC) - timedelta(days=days_ago)
    # Trino returns timestamps as "YYYY-MM-DD HH:MM:SS.mmm UTC"
    committed_at = dt.strftime("%Y-%m-%d %H:%M:%S.000 UTC")
    return {
        "committed_at": committed_at,
        "snapshot_id": int(dt.timestamp()),
        "parent_id": None,
        "operation": operation,
        "manifest_list": "s3://bucket/snap.avro",
        "summary": {},
    }


def _bundle(plan: EstimatedPlan, snapshots: list[dict] | None) -> EvidenceBundle:  # type: ignore[type-arg]
    return EvidenceBundle(plan=plan, iceberg_snapshots=snapshots)


# ── Synthetic-minimum: fires on snapshot count ────────────────────────────────


def test_fires_on_count_threshold() -> None:
    """60 snapshots (> 50 threshold), all recent. I6 fires on count."""
    plan = _make_plan()
    snapshots = [_snapshot(i * 0.1) for i in range(60)]  # 0..6 days ago
    bundle = _bundle(plan, snapshots)

    rule = I6StaleSnapshots()
    findings = rule.check(plan, bundle)

    assert len(findings) >= 1
    count_findings = [f for f in findings if "snapshot_count" in f.evidence]
    assert len(count_findings) >= 1
    f = count_findings[0]
    assert f.rule_id == "I6"
    assert f.severity == "medium"
    assert f.evidence["snapshot_count"] == 60


def test_fires_on_oldest_snapshot_age() -> None:
    """10 snapshots, oldest 40 days ago (> 30-day threshold). I6 fires on age."""
    plan = _make_plan()
    # 9 recent + 1 old
    snapshots = [_snapshot(i) for i in range(9)]  # 0-8 days ago
    snapshots.append(_snapshot(40))  # 40 days ago
    bundle = _bundle(plan, snapshots)

    rule = I6StaleSnapshots()
    findings = rule.check(plan, bundle)

    age_findings = [f for f in findings if f.evidence.get("oldest_snapshot_age_days", 0) > 30]
    assert len(age_findings) >= 1
    assert all(f.rule_id == "I6" for f in age_findings)


def test_both_conditions_fire_separate_findings() -> None:
    """60 snapshots AND oldest > 30 days — both findings emitted."""
    plan = _make_plan()
    snapshots = [_snapshot(i * 0.5) for i in range(59)]  # 0-29.5 days
    snapshots.append(_snapshot(45))  # 45 days ago
    bundle = _bundle(plan, snapshots)

    rule = I6StaleSnapshots()
    findings = rule.check(plan, bundle)

    assert len(findings) == 2
    assert all(f.rule_id == "I6" for f in findings)


# ── Negative-control: does NOT fire ──────────────────────────────────────────


def test_negative_few_recent_snapshots() -> None:
    """5 snapshots, oldest 10 days ago. I6 returns []."""
    plan = _make_plan()
    snapshots = [_snapshot(i * 2) for i in range(5)]  # 0, 2, 4, 6, 8 days ago
    bundle = _bundle(plan, snapshots)

    rule = I6StaleSnapshots()
    findings = rule.check(plan, bundle)

    assert findings == []


def test_negative_none_snapshots() -> None:
    """iceberg_snapshots=None. I6 returns []."""
    plan = _make_plan()
    bundle = _bundle(plan, None)

    rule = I6StaleSnapshots()
    findings = rule.check(plan, bundle)

    assert findings == []


def test_negative_empty_snapshots_list() -> None:
    """Empty snapshot list. I6 returns []."""
    plan = _make_plan()
    bundle = _bundle(plan, [])

    rule = I6StaleSnapshots()
    findings = rule.check(plan, bundle)

    assert findings == []


def test_negative_exactly_at_count_threshold() -> None:
    """Exactly 50 snapshots (= threshold, not >). I6 does not fire on count."""
    plan = _make_plan()
    snapshots = [_snapshot(i * 0.5) for i in range(50)]
    bundle = _bundle(plan, snapshots)

    rule = I6StaleSnapshots(thresholds=RuleThresholds(max_snapshot_count=50))
    findings = rule.check(plan, bundle)

    count_findings = [
        f
        for f in findings
        if f.evidence.get("snapshot_count") == 50 and f.evidence.get("oldest_snapshot_age_days", 999) <= 30
    ]
    assert len(count_findings) == 0


# ── Realistic: mixed ages ─────────────────────────────────────────────────────


def test_realistic_mixed_snapshot_ages_fires() -> None:
    """52 snapshots with varying committed_at (mix of recent and 5-day-old). I6 fires on count."""
    plan = _make_plan()
    # Alternate between 0.5-day-old and 5-day-old snapshots
    snapshots = []
    for i in range(52):
        age = 5.0 if i % 10 == 0 else 0.5
        snapshots.append(_snapshot(age))
    bundle = _bundle(plan, snapshots)

    rule = I6StaleSnapshots()
    findings = rule.check(plan, bundle)

    assert any(f.rule_id == "I6" for f in findings)
    count_findings = [f for f in findings if f.evidence.get("snapshot_count", 0) > 50]
    assert len(count_findings) >= 1


def test_evidence_fields_present() -> None:
    """Finding must contain all documented evidence fields."""
    plan = _make_plan()
    snapshots = [_snapshot(i * 0.1) for i in range(60)]
    bundle = _bundle(plan, snapshots)

    rule = I6StaleSnapshots()
    findings = rule.check(plan, bundle)

    assert len(findings) >= 1
    ev = findings[0].evidence
    assert "snapshot_count" in ev
    assert "threshold_count" in ev
    assert "oldest_snapshot_age_days" in ev
    assert "threshold_days" in ev


def test_malformed_committed_at_skipped() -> None:
    """Rows with unparseable committed_at are skipped; valid rows still counted."""
    plan = _make_plan()
    bad_snap: dict = {"committed_at": "NOT-A-TIMESTAMP", "snapshot_id": 1}  # type: ignore[type-arg]
    good_snaps = [_snapshot(i * 0.5) for i in range(60)]
    bundle = _bundle(plan, [bad_snap, *good_snaps])

    rule = I6StaleSnapshots()
    # Should not raise; bad row skipped; 60 good rows trigger count threshold
    findings = rule.check(plan, bundle)

    assert any(f.rule_id == "I6" for f in findings)
