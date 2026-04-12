"""Tests for parser domain models: PlanNode, EstimatedPlan, ExecutedPlan, etc."""

from __future__ import annotations


class TestCostEstimate:
    """Tests for CostEstimate model."""

    def test_cost_estimate_parses_all_fields(self) -> None:
        """CostEstimate parses outputRowCount, outputSizeInBytes, cpuCost, memoryCost, networkCost."""
        from mcp_trino_optimizer.parser.models import CostEstimate

        ce = CostEstimate.model_validate(
            {
                "outputRowCount": 100.0,
                "outputSizeInBytes": 5000.0,
                "cpuCost": 12345.0,
                "memoryCost": 0.0,
                "networkCost": 60.0,
            }
        )
        assert ce.output_row_count == 100.0
        assert ce.output_size_in_bytes == 5000.0
        assert ce.cpu_cost == 12345.0
        assert ce.memory_cost == 0.0
        assert ce.network_cost == 60.0

    def test_cost_estimate_all_fields_optional(self) -> None:
        """CostEstimate can be created with no fields (all None)."""
        from mcp_trino_optimizer.parser.models import CostEstimate

        ce = CostEstimate()
        assert ce.output_row_count is None
        assert ce.cpu_cost is None

    def test_cost_estimate_partial_fields(self) -> None:
        """CostEstimate handles partial field presence gracefully."""
        from mcp_trino_optimizer.parser.models import CostEstimate

        ce = CostEstimate.model_validate({"outputRowCount": 42.0})
        assert ce.output_row_count == 42.0
        assert ce.cpu_cost is None


class TestOutputSymbol:
    """Tests for OutputSymbol model."""

    def test_output_symbol_parses_symbol_and_type(self) -> None:
        """OutputSymbol parses symbol and type fields."""
        from mcp_trino_optimizer.parser.models import OutputSymbol

        os_ = OutputSymbol(symbol="returnflag", type="varchar(1)")
        assert os_.symbol == "returnflag"
        assert os_.type == "varchar(1)"


class TestSchemaDriftWarning:
    """Tests for SchemaDriftWarning model."""

    def test_schema_drift_warning_has_required_fields(self) -> None:
        """SchemaDriftWarning has node_path, field_name, description, severity fields."""
        from mcp_trino_optimizer.parser.models import SchemaDriftWarning

        w = SchemaDriftWarning(
            node_path="root.children[0]",
            field_name="unknown_field",
            description="Unexpected field found",
            severity="warning",
        )
        assert w.node_path == "root.children[0]"
        assert w.field_name == "unknown_field"
        assert w.description == "Unexpected field found"
        assert w.severity == "warning"

    def test_schema_drift_warning_field_name_optional(self) -> None:
        """SchemaDriftWarning field_name can be None."""
        from mcp_trino_optimizer.parser.models import SchemaDriftWarning

        w = SchemaDriftWarning(
            node_path="root",
            description="Node has unexpected structure",
        )
        assert w.field_name is None

    def test_schema_drift_warning_default_severity_is_warning(self) -> None:
        """SchemaDriftWarning default severity is 'warning'."""
        from mcp_trino_optimizer.parser.models import SchemaDriftWarning

        w = SchemaDriftWarning(node_path="root", description="test")
        assert w.severity == "warning"

    def test_schema_drift_warning_info_severity(self) -> None:
        """SchemaDriftWarning supports 'info' severity."""
        from mcp_trino_optimizer.parser.models import SchemaDriftWarning

        w = SchemaDriftWarning(node_path="root", description="info message", severity="info")
        assert w.severity == "info"


class TestPlanNode:
    """Tests for PlanNode model."""

    def test_plan_node_basic_fields(self) -> None:
        """PlanNode with known fields populates typed attributes."""
        from mcp_trino_optimizer.parser.models import PlanNode

        node = PlanNode(id="1", name="TableScan")
        assert node.id == "1"
        assert node.name == "TableScan"

    def test_plan_node_operator_type_property_returns_name(self) -> None:
        """PlanNode.operator_type property returns name."""
        from mcp_trino_optimizer.parser.models import PlanNode

        node = PlanNode(id="1", name="InnerJoin")
        assert node.operator_type == "InnerJoin"

    def test_plan_node_raw_property_returns_model_extra(self) -> None:
        """PlanNode.raw property returns model_extra dict."""
        from mcp_trino_optimizer.parser.models import PlanNode

        node = PlanNode.model_validate({"id": "1", "name": "TableScan", "unknownField": "value"})
        assert node.raw == {"unknownField": "value"}

    def test_plan_node_raw_empty_dict_when_no_extras(self) -> None:
        """PlanNode.raw returns empty dict when no unknown fields."""
        from mcp_trino_optimizer.parser.models import PlanNode

        node = PlanNode(id="1", name="Output")
        assert node.raw == {}

    def test_plan_node_unknown_fields_preserved_in_model_extra(self) -> None:
        """Unknown fields land in model_extra automatically."""
        from mcp_trino_optimizer.parser.models import PlanNode

        node = PlanNode.model_validate(
            {
                "id": "2",
                "name": "Aggregate",
                "futureTrinoField": "someValue",
                "anotherUnknown": 42,
            }
        )
        assert node.model_extra is not None
        assert "futureTrinoField" in node.model_extra
        assert node.model_extra["futureTrinoField"] == "someValue"
        assert node.model_extra["anotherUnknown"] == 42

    def test_plan_node_runtime_metrics_default_none(self) -> None:
        """PlanNode runtime metrics are all None by default."""
        from mcp_trino_optimizer.parser.models import PlanNode

        node = PlanNode(id="1", name="TableScan")
        assert node.cpu_time_ms is None
        assert node.wall_time_ms is None
        assert node.input_rows is None
        assert node.input_bytes is None
        assert node.output_rows is None
        assert node.output_bytes is None
        assert node.peak_memory_bytes is None
        assert node.physical_input_bytes is None
        assert node.spilled_bytes is None
        assert node.blocked_time_ms is None

    def test_plan_node_iceberg_fields_default_none(self) -> None:
        """PlanNode Iceberg fields are None by default."""
        from mcp_trino_optimizer.parser.models import PlanNode

        node = PlanNode(id="1", name="TableScan")
        assert node.iceberg_split_count is None
        assert node.iceberg_file_count is None
        assert node.iceberg_partition_spec_id is None

    def test_plan_node_children_default_empty(self) -> None:
        """PlanNode children list defaults to empty."""
        from mcp_trino_optimizer.parser.models import PlanNode

        node = PlanNode(id="1", name="Output")
        assert node.children == []

    def test_plan_node_with_estimates(self) -> None:
        """PlanNode parses estimates list of CostEstimate."""
        from mcp_trino_optimizer.parser.models import CostEstimate, PlanNode

        node = PlanNode.model_validate(
            {
                "id": "1",
                "name": "Output",
                "estimates": [{"outputRowCount": 10.0, "cpuCost": 100.0}],
            }
        )
        assert len(node.estimates) == 1
        assert isinstance(node.estimates[0], CostEstimate)
        assert node.estimates[0].output_row_count == 10.0

    def test_plan_node_with_outputs(self) -> None:
        """PlanNode parses outputs list of OutputSymbol."""
        from mcp_trino_optimizer.parser.models import OutputSymbol, PlanNode

        node = PlanNode.model_validate(
            {
                "id": "1",
                "name": "Output",
                "outputs": [{"symbol": "col1", "type": "bigint"}],
            }
        )
        assert len(node.outputs) == 1
        assert isinstance(node.outputs[0], OutputSymbol)
        assert node.outputs[0].symbol == "col1"


class TestParseError:
    """Tests for ParseError exception."""

    def test_parse_error_is_exception(self) -> None:
        """ParseError is a subclass of Exception."""
        from mcp_trino_optimizer.parser.models import ParseError

        err = ParseError("bad input")
        assert isinstance(err, Exception)

    def test_parse_error_has_message(self) -> None:
        """ParseError carries a message."""
        from mcp_trino_optimizer.parser.models import ParseError

        err = ParseError("invalid plan JSON")
        assert "invalid plan JSON" in str(err)


class TestEstimatedAndExecutedPlan:
    """Tests for EstimatedPlan and ExecutedPlan."""

    def test_estimated_plan_has_root_and_warnings(self) -> None:
        """EstimatedPlan has root PlanNode and schema_drift_warnings list."""
        from mcp_trino_optimizer.parser.models import EstimatedPlan, PlanNode

        root = PlanNode(id="0", name="Output")
        plan = EstimatedPlan(root=root)
        assert plan.root is root
        assert plan.schema_drift_warnings == []

    def test_estimated_plan_has_plan_type_estimated(self) -> None:
        """EstimatedPlan.plan_type is 'estimated'."""
        from mcp_trino_optimizer.parser.models import EstimatedPlan, PlanNode

        plan = EstimatedPlan(root=PlanNode(id="0", name="Output"))
        assert plan.plan_type == "estimated"

    def test_executed_plan_has_root_and_warnings(self) -> None:
        """ExecutedPlan has root PlanNode and schema_drift_warnings list."""
        from mcp_trino_optimizer.parser.models import ExecutedPlan, PlanNode

        root = PlanNode(id="0", name="Output")
        plan = ExecutedPlan(root=root)
        assert plan.root is root
        assert plan.schema_drift_warnings == []

    def test_executed_plan_has_plan_type_executed(self) -> None:
        """ExecutedPlan.plan_type is 'executed'."""
        from mcp_trino_optimizer.parser.models import ExecutedPlan, PlanNode

        plan = ExecutedPlan(root=PlanNode(id="0", name="Output"))
        assert plan.plan_type == "executed"

    def test_source_trino_version_default_none(self) -> None:
        """EstimatedPlan and ExecutedPlan source_trino_version defaults to None."""
        from mcp_trino_optimizer.parser.models import EstimatedPlan, PlanNode

        plan = EstimatedPlan(root=PlanNode(id="0", name="Output"))
        assert plan.source_trino_version is None

    def test_walk_yields_all_nodes_dfs(self) -> None:
        """EstimatedPlan.walk() yields all nodes in DFS order."""
        from mcp_trino_optimizer.parser.models import EstimatedPlan, PlanNode

        child1 = PlanNode(id="1", name="TableScan")
        child2 = PlanNode(id="2", name="Filter")
        root = PlanNode(id="0", name="Output", children=[child1, child2])
        plan = EstimatedPlan(root=root)

        nodes = list(plan.walk())
        assert len(nodes) == 3
        assert nodes[0].id == "0"  # root first in DFS
        assert nodes[1].id == "1"
        assert nodes[2].id == "2"

    def test_walk_nested_tree(self) -> None:
        """EstimatedPlan.walk() traverses deeply nested trees."""
        from mcp_trino_optimizer.parser.models import EstimatedPlan, PlanNode

        grandchild = PlanNode(id="2", name="TableScan")
        child = PlanNode(id="1", name="Filter", children=[grandchild])
        root = PlanNode(id="0", name="Output", children=[child])
        plan = EstimatedPlan(root=root)

        nodes = list(plan.walk())
        assert len(nodes) == 3

    def test_find_nodes_by_type_returns_matching(self) -> None:
        """EstimatedPlan.find_nodes_by_type() returns only matching nodes."""
        from mcp_trino_optimizer.parser.models import EstimatedPlan, PlanNode

        scan1 = PlanNode(id="1", name="TableScan")
        scan2 = PlanNode(id="3", name="TableScan")
        child = PlanNode(id="2", name="Filter", children=[scan2])
        root = PlanNode(id="0", name="Output", children=[scan1, child])
        plan = EstimatedPlan(root=root)

        scans = plan.find_nodes_by_type("TableScan")
        assert len(scans) == 2
        assert all(n.name == "TableScan" for n in scans)

    def test_find_nodes_by_type_returns_empty_when_none_match(self) -> None:
        """find_nodes_by_type returns empty list if no nodes match."""
        from mcp_trino_optimizer.parser.models import EstimatedPlan, PlanNode

        root = PlanNode(id="0", name="Output")
        plan = EstimatedPlan(root=root)
        assert plan.find_nodes_by_type("NonExistentType") == []
