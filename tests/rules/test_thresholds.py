"""Parameterized threshold data-driven tests for RuleThresholds."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from mcp_trino_optimizer.parser.models import CostEstimate, EstimatedPlan, ExecutedPlan, PlanNode
from mcp_trino_optimizer.rules.d11_cost_vs_actual import D11CostVsActual
from mcp_trino_optimizer.rules.evidence import EvidenceBundle
from mcp_trino_optimizer.rules.r5_broadcast_too_big import R5BroadcastTooBig
from mcp_trino_optimizer.rules.r7_cpu_skew import R7CpuSkew
from mcp_trino_optimizer.rules.r9_low_selectivity import R9LowSelectivity
from mcp_trino_optimizer.rules.thresholds import RuleThresholds

if TYPE_CHECKING:
    from mcp_trino_optimizer.parser.models import BasePlan
    from mcp_trino_optimizer.rules.base import Rule


def test_default_values_load_without_env() -> None:
    """RuleThresholds() loads all defaults without any env vars set."""
    t = RuleThresholds()
    assert t.skew_ratio == pytest.approx(5.0)
    assert t.broadcast_max_bytes == 100 * 1024 * 1024
    assert t.stats_divergence_factor == pytest.approx(5.0)
    assert t.scan_selectivity_threshold == pytest.approx(0.10)
    assert t.small_file_bytes == 16 * 1024 * 1024
    assert t.small_file_split_count_threshold == 10_000
    assert t.delete_file_count_threshold == 100
    assert t.delete_ratio_threshold == pytest.approx(0.10)
    assert t.max_snapshot_count == 50
    assert t.snapshot_retention_days == 30
    assert t.max_metadata_rows == 10_000


def test_env_override_skew_ratio(monkeypatch: pytest.MonkeyPatch) -> None:
    """TRINO_RULE_SKEW_RATIO env var overrides skew_ratio to 10.0."""
    monkeypatch.setenv("TRINO_RULE_SKEW_RATIO", "10.0")
    t = RuleThresholds()
    assert t.skew_ratio == pytest.approx(10.0)


def test_env_override_broadcast_max_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """TRINO_RULE_BROADCAST_MAX_BYTES env var overrides broadcast_max_bytes."""
    monkeypatch.setenv("TRINO_RULE_BROADCAST_MAX_BYTES", "52428800")  # 50MB
    t = RuleThresholds()
    assert t.broadcast_max_bytes == 52_428_800


def test_env_override_max_metadata_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """TRINO_RULE_MAX_METADATA_ROWS env var overrides max_metadata_rows."""
    monkeypatch.setenv("TRINO_RULE_MAX_METADATA_ROWS", "500")
    t = RuleThresholds()
    assert t.max_metadata_rows == 500


@pytest.mark.parametrize(
    "field_name, expected_default, citation_keyword",
    [
        # spot-check 3 thresholds against their documented citation values
        ("skew_ratio", 5.0, "empirical"),
        ("scan_selectivity_threshold", 0.10, "0.10"),
        ("delete_ratio_threshold", 0.10, "0.10"),
    ],
)
def test_threshold_defaults_match_citations(
    field_name: str, expected_default: float, citation_keyword: str
) -> None:
    """Spot-check that default values match their documented citation defaults."""
    t = RuleThresholds()
    actual = getattr(t, field_name)
    assert actual == pytest.approx(expected_default), (
        f"{field_name}: expected {expected_default}, got {actual}"
    )


# ---------------------------------------------------------------------------
# Threshold behavioral toggle tests (SC-5)
# ---------------------------------------------------------------------------

# ── Plan factory helpers ──────────────────────────────────────────────────


def _make_borderline_scan_plan() -> ExecutedPlan:
    """Scan node with selectivity ratio=0.08 (below default 0.10, above 0.05).

    input_bytes=1000, output_bytes=80 -> ratio = 80/1000 = 0.08.
    - threshold=0.05 (below_val): 0.08 >= 0.05 -> rule should NOT fire.
    - threshold=0.20 (above_val): 0.08 <  0.20 -> rule SHOULD fire.
    """
    node = PlanNode(id="0", name="TableScan", input_bytes=1000, output_bytes=80)
    return ExecutedPlan(root=node)


def _make_borderline_broadcast_plan() -> EstimatedPlan:
    """REPLICATED InnerJoin with build side estimated at 150 MB.

    - threshold=200MB (below_val): 150MB < 200MB -> rule should NOT fire.
    - threshold= 50MB (above_val): 150MB >  50MB -> rule SHOULD fire.
    """
    build_bytes = 150 * 1024 * 1024  # 150 MB
    build_node = PlanNode(
        id="1",
        name="TableScan",
        estimates=[CostEstimate(outputSizeInBytes=float(build_bytes))],
    )
    probe_node = PlanNode(id="2", name="TableScan")
    join_node = PlanNode(
        id="0",
        name="InnerJoin",
        descriptor={"distribution": "REPLICATED"},
        children=[probe_node, build_node],
    )
    return EstimatedPlan(root=join_node)


def _make_borderline_skew_plan() -> ExecutedPlan:
    """Five-node ExecutedPlan with cpu times [100, 100, 100, 100, 700] -> ratio=7.0.

    - threshold=10.0 (below_val): 7.0 < 10.0 -> rule should NOT fire.
    - threshold= 5.0 (above_val): 7.0 >= 5.0 -> rule SHOULD fire.
    """
    leaf = PlanNode(id="4", name="TableScan", cpu_time_ms=700.0)
    n3 = PlanNode(id="3", name="TableScan", cpu_time_ms=100.0, children=[leaf])
    n2 = PlanNode(id="2", name="TableScan", cpu_time_ms=100.0, children=[n3])
    n1 = PlanNode(id="1", name="TableScan", cpu_time_ms=100.0, children=[n2])
    n0 = PlanNode(id="0", name="TableScan", cpu_time_ms=100.0, children=[n1])
    return ExecutedPlan(root=n0)


@pytest.mark.parametrize(
    "threshold_name,rule_cls,below_val,above_val,make_plan",
    [
        # R9: scan selectivity — ratio 0.08 sits between 0.05 and 0.20
        (
            "scan_selectivity_threshold",
            R9LowSelectivity,
            0.05,   # below threshold: 0.08 >= 0.05  -> does NOT fire
            0.20,   # above threshold: 0.08 <  0.20  -> DOES fire
            _make_borderline_scan_plan,
        ),
        # R5: broadcast join size — build side 150 MB sits between 50 MB and 200 MB
        (
            "broadcast_max_bytes",
            R5BroadcastTooBig,
            200 * 1024 * 1024,  # below threshold: 150MB < 200MB -> does NOT fire
            50 * 1024 * 1024,   # above threshold: 150MB > 50MB  -> DOES fire
            _make_borderline_broadcast_plan,
        ),
        # R7: cpu skew — ratio 7.0 sits between 5.0 and 10.0
        (
            "skew_ratio",
            R7CpuSkew,
            10.0,   # below threshold: 7.0 < 10.0  -> does NOT fire
            5.0,    # above threshold: 7.0 >= 5.0  -> DOES fire
            _make_borderline_skew_plan,
        ),
    ],
    ids=["R9-scan-selectivity", "R5-broadcast-max-bytes", "R7-skew-ratio"],
)
def test_threshold_toggles_rule_behavior(
    threshold_name: str,
    rule_cls: type[Rule],
    below_val: float,
    above_val: float,
    make_plan: object,
) -> None:
    """Changing a single threshold toggles whether the corresponding rule fires.

    Pattern (SC-5):
      - Construct a borderline plan that sits between below_val and above_val.
      - With threshold=below_val the rule should NOT fire (plan is within limits).
      - With threshold=above_val the rule SHOULD fire (plan exceeds limits).

    This proves that RuleThresholds is actually wired into the rule logic
    and not just a dead configuration field.
    """
    assert callable(make_plan), "make_plan must be a callable that returns a BasePlan"
    plan: BasePlan = make_plan()  # type: ignore[operator]
    evidence = EvidenceBundle(plan=plan)

    # Below threshold: rule must NOT fire
    thresholds_below = RuleThresholds(**{threshold_name: below_val})
    rule_below: Rule = rule_cls(thresholds=thresholds_below)  # type: ignore[call-arg]
    assert rule_below.check(plan, evidence) == [], (
        f"{rule_cls.__name__} should NOT fire when {threshold_name}={below_val} "
        f"(plan value is between {below_val} and {above_val})"
    )

    # Above threshold: rule MUST fire
    thresholds_above = RuleThresholds(**{threshold_name: above_val})
    rule_above: Rule = rule_cls(thresholds=thresholds_above)  # type: ignore[call-arg]
    findings = rule_above.check(plan, evidence)
    assert len(findings) > 0, (
        f"{rule_cls.__name__} SHOULD fire when {threshold_name}={above_val} "
        f"(plan value is between {below_val} and {above_val})"
    )
