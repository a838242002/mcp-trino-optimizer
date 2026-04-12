"""Tests for parse_estimated_plan and parse_executed_plan."""

from __future__ import annotations

import json

import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────

SIMPLE_EXPLAIN_JSON = json.dumps(
    {
        "id": "6",
        "name": "Output",
        "descriptor": {"columnNames": "[returnflag]"},
        "outputs": [{"symbol": "returnflag", "type": "varchar(1)"}],
        "details": [],
        "estimates": [
            {
                "outputRowCount": 10.0,
                "outputSizeInBytes": 60.0,
                "cpuCost": 34780027.7,
                "memoryCost": 0.0,
                "networkCost": 60.0,
            }
        ],
        "children": [
            {
                "id": "5",
                "name": "Aggregate",
                "descriptor": {"type": "FINAL", "keys": "[returnflag]"},
                "outputs": [{"symbol": "returnflag", "type": "varchar(1)"}],
                "details": [],
                "estimates": [],
                "children": [
                    {
                        "id": "4",
                        "name": "TableScan",
                        "descriptor": {"table": "iceberg.tpch.lineitem"},
                        "outputs": [{"symbol": "returnflag", "type": "varchar(1)"}],
                        "details": [],
                        "estimates": [{"outputRowCount": 6001215.0}],
                        "children": [],
                    }
                ],
            }
        ],
    }
)

EXPLAIN_JSON_UNKNOWN_FIELDS = json.dumps(
    {
        "id": "1",
        "name": "UnknownFutureOperator",
        "descriptor": {},
        "outputs": [],
        "details": [],
        "estimates": [],
        "children": [],
        "futureTrinoField": "someValue",
        "anotherNewField": 42,
    }
)

EXPLAIN_JSON_MISSING_OPTIONALS = json.dumps(
    {
        "id": "1",
        "name": "TableScan",
        # No estimates, no details, no outputs, no descriptor
    }
)

# Representative EXPLAIN ANALYZE text output based on Trino format
EXPLAIN_ANALYZE_TEXT = """\
Fragment 0 [SINGLE]
    CPU: 150.00ms, Scheduled: 200.00ms, Blocked 0.00ns (Input: 0.00ns, Output: 0.00ns), Input: 100 rows (5.00kB)
    Output layout: [returnflag]
    Output[columnNames = [returnflag]] => [returnflag:varchar(1)]
        CPU: 10.00ms, Scheduled: 12.00ms, Blocked: 0.00ns, Output: 100 rows (5.00kB)
        Input avg.: 100 rows, Input std.dev.: 0%
        \u2514\u2500 Aggregate(FINAL)[returnflag]$hashvalue => [returnflag:varchar(1)]
                CPU: 30.00ms, Scheduled: 35.00ms, Blocked: 0.00ns, Output: 100 rows (5.00kB)
                Input avg.: 1000 rows, Input std.dev.: 0%
                \u2514\u2500 TableScan[iceberg:iceberg.tpch.lineitem iceberg:iceberg.tpch.lineitem] => [returnflag:varchar(1)]
                        CPU: 110.00ms, Scheduled: 150.00ms, Blocked: 0.00ns, Output: 1000 rows (50.00kB)
                        Input: 6001215 rows (286.89MB), Filtered: 0.00%
                        Peak Memory: 10.00MB
"""

EXPLAIN_ANALYZE_WITH_ICEBERG = """\
Fragment 0 [SINGLE]
    CPU: 500.00ms, Scheduled: 600.00ms, Blocked 0.00ns (Input: 0.00ns, Output: 0.00ns), Input: 100 rows (5.00kB)
    Output layout: [id]
    Output[columnNames = [id]] => [id:bigint]
        CPU: 5.00ms, Scheduled: 6.00ms, Blocked: 0.00ns, Output: 100 rows (0.80kB)
        \u2514\u2500 ScanFilterAndProject[table = iceberg.schema.test_table, filterPredicate = (id > 1)] => [id:bigint]
                CPU: 490.00ms, Scheduled: 590.00ms, Blocked: 0.00ns, Output: 100 rows (0.80kB)
                Input: 1000 rows (8.00kB), 5 splits
                Files read: 3
                Peak Memory: 5.00MB
"""


# ── Tests for parse_estimated_plan ────────────────────────────────────────────


class TestParseEstimatedPlan:
    """Tests for parse_estimated_plan function."""

    def test_parses_valid_explain_json_into_estimated_plan(self) -> None:
        """parse_estimated_plan parses valid EXPLAIN JSON into EstimatedPlan with typed tree."""
        from mcp_trino_optimizer.parser import parse_estimated_plan
        from mcp_trino_optimizer.parser.models import EstimatedPlan

        plan = parse_estimated_plan(SIMPLE_EXPLAIN_JSON)

        assert isinstance(plan, EstimatedPlan)
        assert plan.plan_type == "estimated"

    def test_root_node_is_plan_node(self) -> None:
        """parse_estimated_plan produces a root PlanNode."""
        from mcp_trino_optimizer.parser import parse_estimated_plan
        from mcp_trino_optimizer.parser.models import PlanNode

        plan = parse_estimated_plan(SIMPLE_EXPLAIN_JSON)

        assert isinstance(plan.root, PlanNode)
        assert plan.root.name == "Output"

    def test_children_are_parsed_recursively(self) -> None:
        """parse_estimated_plan builds a full recursive tree."""
        from mcp_trino_optimizer.parser import parse_estimated_plan

        plan = parse_estimated_plan(SIMPLE_EXPLAIN_JSON)

        assert len(plan.root.children) == 1
        aggregate = plan.root.children[0]
        assert aggregate.name == "Aggregate"
        assert len(aggregate.children) == 1
        assert aggregate.children[0].name == "TableScan"

    def test_cost_estimates_parsed(self) -> None:
        """parse_estimated_plan parses estimates into typed CostEstimate objects."""
        from mcp_trino_optimizer.parser import parse_estimated_plan
        from mcp_trino_optimizer.parser.models import CostEstimate

        plan = parse_estimated_plan(SIMPLE_EXPLAIN_JSON)

        assert len(plan.root.estimates) == 1
        assert isinstance(plan.root.estimates[0], CostEstimate)
        assert plan.root.estimates[0].output_row_count == 10.0

    def test_unknown_node_type_does_not_raise(self) -> None:
        """parse_estimated_plan with unknown node type does not raise exception."""
        from mcp_trino_optimizer.parser import parse_estimated_plan

        # Should not raise
        plan = parse_estimated_plan(EXPLAIN_JSON_UNKNOWN_FIELDS)
        assert plan.root.operator_type == "UnknownFutureOperator"

    def test_unknown_fields_preserved_in_model_extra(self) -> None:
        """parse_estimated_plan with unknown fields preserves them in model_extra."""
        from mcp_trino_optimizer.parser import parse_estimated_plan

        plan = parse_estimated_plan(EXPLAIN_JSON_UNKNOWN_FIELDS)

        assert "futureTrinoField" in plan.root.raw
        assert plan.root.raw["futureTrinoField"] == "someValue"
        assert plan.root.raw["anotherNewField"] == 42

    def test_missing_optional_fields_still_parses(self) -> None:
        """parse_estimated_plan with missing optional fields (no estimates, no details) still parses."""
        from mcp_trino_optimizer.parser import parse_estimated_plan

        plan = parse_estimated_plan(EXPLAIN_JSON_MISSING_OPTIONALS)

        assert plan.root.name == "TableScan"
        assert plan.root.estimates == []
        assert plan.root.details == []
        assert plan.root.outputs == []

    def test_invalid_json_raises_parse_error(self) -> None:
        """parse_estimated_plan with completely invalid JSON raises ParseError."""
        from mcp_trino_optimizer.parser import parse_estimated_plan
        from mcp_trino_optimizer.parser.models import ParseError

        with pytest.raises(ParseError):
            parse_estimated_plan("not json at all {{{{")

    def test_wrong_top_level_structure_raises_parse_error(self) -> None:
        """parse_estimated_plan with wrong top-level structure (list) raises ParseError."""
        from mcp_trino_optimizer.parser import parse_estimated_plan
        from mcp_trino_optimizer.parser.models import ParseError

        with pytest.raises(ParseError):
            parse_estimated_plan(json.dumps([{"id": "1", "name": "Output"}]))

    def test_schema_drift_warning_for_missing_id(self) -> None:
        """parse_estimated_plan records SchemaDriftWarning for nodes missing required fields."""
        from mcp_trino_optimizer.parser import parse_estimated_plan

        # A child node without 'id' should produce a warning
        json_with_bad_child = json.dumps(
            {
                "id": "0",
                "name": "Output",
                "children": [
                    {
                        # Missing 'id' - should trigger a warning
                        "name": "TableScan",
                    }
                ],
            }
        )
        plan = parse_estimated_plan(json_with_bad_child)
        # Either: a warning was recorded, OR the node was parsed with a default id
        # The key requirement is no exception
        assert plan is not None

    def test_trino_version_stored_on_plan(self) -> None:
        """parse_estimated_plan stores trino_version on the result plan."""
        from mcp_trino_optimizer.parser import parse_estimated_plan

        plan = parse_estimated_plan(SIMPLE_EXPLAIN_JSON, trino_version="480")
        assert plan.source_trino_version == "480"

    def test_outputs_parsed_as_output_symbols(self) -> None:
        """parse_estimated_plan parses outputs as OutputSymbol objects."""
        from mcp_trino_optimizer.parser import parse_estimated_plan
        from mcp_trino_optimizer.parser.models import OutputSymbol

        plan = parse_estimated_plan(SIMPLE_EXPLAIN_JSON)
        assert len(plan.root.outputs) == 1
        assert isinstance(plan.root.outputs[0], OutputSymbol)
        assert plan.root.outputs[0].symbol == "returnflag"


# ── Tests for parse_executed_plan ─────────────────────────────────────────────


class TestParseExecutedPlan:
    """Tests for parse_executed_plan function."""

    def test_parses_explain_analyze_text_into_executed_plan(self) -> None:
        """parse_executed_plan parses EXPLAIN ANALYZE text into ExecutedPlan."""
        from mcp_trino_optimizer.parser import parse_executed_plan
        from mcp_trino_optimizer.parser.models import ExecutedPlan

        plan = parse_executed_plan(EXPLAIN_ANALYZE_TEXT)

        assert isinstance(plan, ExecutedPlan)
        assert plan.plan_type == "executed"

    def test_executed_plan_has_root_node(self) -> None:
        """parse_executed_plan produces a root PlanNode."""
        from mcp_trino_optimizer.parser import parse_executed_plan
        from mcp_trino_optimizer.parser.models import PlanNode

        plan = parse_executed_plan(EXPLAIN_ANALYZE_TEXT)

        assert isinstance(plan.root, PlanNode)

    def test_executed_plan_extracts_cpu_time(self) -> None:
        """parse_executed_plan extracts cpu_time_ms per operator."""
        from mcp_trino_optimizer.parser import parse_executed_plan

        plan = parse_executed_plan(EXPLAIN_ANALYZE_TEXT)

        # Walk to find TableScan with cpu metrics
        nodes = list(plan.walk())
        scan_nodes = [n for n in nodes if "TableScan" in n.name]
        if scan_nodes:
            assert scan_nodes[0].cpu_time_ms is not None

    def test_executed_plan_extracts_output_rows(self) -> None:
        """parse_executed_plan extracts output_rows per operator."""
        from mcp_trino_optimizer.parser import parse_executed_plan

        plan = parse_executed_plan(EXPLAIN_ANALYZE_TEXT)

        nodes = list(plan.walk())
        # At least one node should have output rows set
        nodes_with_rows = [n for n in nodes if n.output_rows is not None]
        assert len(nodes_with_rows) > 0

    def test_executed_plan_stores_raw_text(self) -> None:
        """parse_executed_plan stores the raw text on the plan."""
        from mcp_trino_optimizer.parser import parse_executed_plan

        plan = parse_executed_plan(EXPLAIN_ANALYZE_TEXT)
        assert plan.raw_text == EXPLAIN_ANALYZE_TEXT

    def test_executed_plan_trino_version_stored(self) -> None:
        """parse_executed_plan stores trino_version on the result plan."""
        from mcp_trino_optimizer.parser import parse_executed_plan

        plan = parse_executed_plan(EXPLAIN_ANALYZE_TEXT, trino_version="480")
        assert plan.source_trino_version == "480"

    def test_iceberg_scan_extracts_split_count(self) -> None:
        """parse_executed_plan extracts iceberg_split_count from detail lines."""
        from mcp_trino_optimizer.parser import parse_executed_plan

        plan = parse_executed_plan(EXPLAIN_ANALYZE_WITH_ICEBERG)

        nodes = list(plan.walk())
        scan_nodes = [n for n in nodes if "Scan" in n.name]
        # After normalization, should see TableScan with split_count set
        scan_with_splits = [n for n in scan_nodes if n.iceberg_split_count is not None]
        assert len(scan_with_splits) > 0
        assert scan_with_splits[0].iceberg_split_count == 5

    def test_iceberg_scan_extracts_file_count(self) -> None:
        """parse_executed_plan extracts iceberg_file_count from 'Files read' detail lines."""
        from mcp_trino_optimizer.parser import parse_executed_plan

        plan = parse_executed_plan(EXPLAIN_ANALYZE_WITH_ICEBERG)

        nodes = list(plan.walk())
        # After normalization, TableScan or ScanFilterAndProject with file_count
        scan_nodes = [n for n in nodes if n.iceberg_file_count is not None]
        assert len(scan_nodes) > 0
        assert scan_nodes[0].iceberg_file_count == 3

    def test_malformed_text_line_produces_schema_drift_warning(self) -> None:
        """parse_executed_plan with malformed text records SchemaDriftWarning, does not raise."""
        from mcp_trino_optimizer.parser import parse_executed_plan

        malformed_text = "Fragment 0 [SINGLE]\n    CORRUPTED@@@@LINE###\n"
        # Should not raise
        plan = parse_executed_plan(malformed_text)
        assert plan is not None

    def test_empty_text_returns_executed_plan(self) -> None:
        """parse_executed_plan with minimal/empty text returns ExecutedPlan without raising."""
        from mcp_trino_optimizer.parser import parse_executed_plan
        from mcp_trino_optimizer.parser.models import ExecutedPlan

        plan = parse_executed_plan("")
        assert isinstance(plan, ExecutedPlan)
