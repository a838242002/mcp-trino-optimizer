"""Syrupy snapshot tests for the multi-version Trino EXPLAIN fixture corpus.

Every fixture file in tests/fixtures/explain/{version}/ is parsed through the
parser and the result is snapshotted. These tests are the drift detection alarm:
when Trino adds or removes a field between versions, the snapshot diff shows
exactly what changed in the parsed output.

Snapshot update workflow:
    uv run pytest tests/parser/test_fixture_snapshots.py --snapshot-update

CI workflow (no update flag): snapshots must match exactly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from mcp_trino_optimizer.parser import parse_estimated_plan, parse_executed_plan

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "explain"


def _collect_fixtures() -> list[tuple[str, str, Path, str]]:
    """Collect all fixture files as (version, name, path, plan_type) tuples.

    Returned in sorted order for deterministic parametrize IDs.
    """
    fixtures: list[tuple[str, str, Path, str]] = []
    if not FIXTURE_DIR.exists():
        return fixtures

    for version_dir in sorted(FIXTURE_DIR.iterdir()):
        if not version_dir.is_dir():
            continue
        version = version_dir.name
        for f in sorted(version_dir.iterdir()):
            if f.suffix == ".json":
                fixtures.append((version, f.stem, f, "estimated"))
            elif f.name.endswith("_analyze.txt"):
                fixtures.append((version, f.stem.removesuffix("_analyze"), f, "executed"))
    return fixtures


def _fixture_id(val: object) -> str | None:
    """Generate a clean test ID from parametrize values."""
    if isinstance(val, str):
        return val
    if isinstance(val, Path):
        return val.name
    return None


_ALL_FIXTURES = _collect_fixtures()


@pytest.mark.parametrize(
    ("version", "name", "path", "plan_type"),
    _ALL_FIXTURES,
    ids=_fixture_id,
)
def test_fixture_parses_without_error(version: str, name: str, path: Path, plan_type: str) -> None:
    """Every fixture file must parse without raising any exception.

    Verifies:
    - No ParseError is raised
    - Parsed plan has a non-None root node
    - Plan tree contains at least one node
    - source_trino_version is set to the version string
    """
    text = path.read_text(encoding="utf-8")

    if plan_type == "estimated":
        plan = parse_estimated_plan(text, trino_version=version)
    else:
        plan = parse_executed_plan(text, trino_version=version)

    assert plan.root is not None, f"root is None for {version}/{name} ({plan_type})"
    nodes = list(plan.walk())
    assert len(nodes) >= 1, f"No nodes in plan tree for {version}/{name} ({plan_type})"
    assert plan.source_trino_version == version, (
        f"source_trino_version mismatch: expected {version}, got {plan.source_trino_version}"
    )


@pytest.mark.parametrize(
    ("version", "name", "path", "plan_type"),
    _ALL_FIXTURES,
    ids=_fixture_id,
)
def test_fixture_no_parse_error(version: str, name: str, path: Path, plan_type: str) -> None:
    """No fixture should raise ParseError.

    ParseError is reserved for completely unparseable input (invalid JSON,
    wrong top-level structure). Fixture files are valid EXPLAIN output.
    """
    from mcp_trino_optimizer.parser import ParseError

    text = path.read_text(encoding="utf-8")

    try:
        if plan_type == "estimated":
            parse_estimated_plan(text, trino_version=version)
        else:
            parse_executed_plan(text, trino_version=version)
    except ParseError as exc:
        pytest.fail(f"ParseError raised for {version}/{name} ({plan_type}): {exc}")


@pytest.mark.parametrize(
    ("version", "name", "path", "plan_type"),
    _ALL_FIXTURES,
    ids=_fixture_id,
)
def test_fixture_schema_drift_warnings_captured(version: str, name: str, path: Path, plan_type: str) -> None:
    """Schema drift warnings must be captured in the plan object, not raised.

    Any warnings (unexpected fields, missing fields) must be in
    plan.schema_drift_warnings — never raised as exceptions.
    """
    text = path.read_text(encoding="utf-8")

    if plan_type == "estimated":
        plan = parse_estimated_plan(text, trino_version=version)
    else:
        plan = parse_executed_plan(text, trino_version=version)

    # schema_drift_warnings must be a list (possibly empty)
    assert isinstance(plan.schema_drift_warnings, list), f"schema_drift_warnings is not a list for {version}/{name}"
    # Each warning must have the mandatory fields
    for w in plan.schema_drift_warnings:
        assert hasattr(w, "node_path"), "SchemaDriftWarning missing node_path"
        assert hasattr(w, "description"), "SchemaDriftWarning missing description"
        assert w.severity in ("info", "warning"), f"Invalid severity: {w.severity}"


@pytest.mark.parametrize(
    ("version", "name", "path", "plan_type"),
    [f for f in _ALL_FIXTURES if f[1] in ("simple_select", "aggregate")],
    ids=_fixture_id,
)
def test_estimated_fixture_has_typed_cost_estimates(version: str, name: str, path: Path, plan_type: str) -> None:
    """EXPLAIN JSON fixtures (estimated plans) should have CostEstimate entries.

    Simple select and aggregate queries produce cost estimates for all nodes.
    """
    if plan_type != "estimated":
        pytest.skip("Only applicable to estimated plans")

    text = path.read_text(encoding="utf-8")
    plan = parse_estimated_plan(text, trino_version=version)

    # At least the root node (or one of its descendants) should have estimates
    all_nodes = list(plan.walk())
    nodes_with_estimates = [n for n in all_nodes if len(n.estimates) > 0]
    assert len(nodes_with_estimates) > 0, (
        f"No nodes with CostEstimate in {version}/{name} — expected cost estimates in EXPLAIN JSON output"
    )


@pytest.mark.parametrize(
    ("version", "name", "path", "plan_type"),
    [f for f in _ALL_FIXTURES if f[1] in ("simple_select", "aggregate")],
    ids=_fixture_id,
)
def test_executed_fixture_has_runtime_metrics(version: str, name: str, path: Path, plan_type: str) -> None:
    """EXPLAIN ANALYZE fixtures (executed plans) should have runtime metrics.

    Simple select and aggregate queries should have CPU time and output rows
    populated on at least one node.
    """
    if plan_type != "executed":
        pytest.skip("Only applicable to executed plans")

    text = path.read_text(encoding="utf-8")
    plan = parse_executed_plan(text, trino_version=version)

    all_nodes = list(plan.walk())
    nodes_with_cpu = [n for n in all_nodes if n.cpu_time_ms is not None]
    nodes_with_output_rows = [n for n in all_nodes if n.output_rows is not None]

    assert len(nodes_with_cpu) > 0, (
        f"No nodes with cpu_time_ms in {version}/{name} — expected runtime metrics in EXPLAIN ANALYZE output"
    )
    assert len(nodes_with_output_rows) > 0, (
        f"No nodes with output_rows in {version}/{name} — expected runtime metrics in EXPLAIN ANALYZE output"
    )


# ── Snapshot tests ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("version", "name", "path", "plan_type"),
    _ALL_FIXTURES,
    ids=_fixture_id,
)
def test_fixture_snapshot(version: str, name: str, path: Path, plan_type: str, snapshot: SnapshotAssertion) -> None:
    """Parsed plan must match the stored syrupy snapshot.

    When Trino adds or renames a field, this test fails with a clean diff
    showing exactly what changed in the parsed output. Update snapshots with:
        uv run pytest tests/parser/test_fixture_snapshots.py --snapshot-update

    The snapshot excludes raw_text (the full EXPLAIN output) to keep diffs
    readable. It captures the typed tree structure, cost estimates, runtime
    metrics, and schema drift warnings.
    """
    text = path.read_text(encoding="utf-8")

    if plan_type == "estimated":
        plan = parse_estimated_plan(text, trino_version=version)
    else:
        plan = parse_executed_plan(text, trino_version=version)

    # Dump to dict for snapshot comparison.
    # Exclude raw_text — it's the full EXPLAIN text which is already in the fixture
    # file and would make snapshot diffs unreadable. The typed tree IS the point.
    snapshot_data = plan.model_dump(exclude={"raw_text"})

    assert snapshot_data == snapshot
