"""Tests for normalize_plan_tree: ScanFilterAndProject decomposition."""

from __future__ import annotations


def _make_scan_filter_and_project(
    node_id: str = "1",
    with_filter: bool = True,
    children: list | None = None,
) -> "PlanNode":  # type: ignore[name-defined]
    from mcp_trino_optimizer.parser.models import CostEstimate, OutputSymbol, PlanNode

    details = []
    if with_filter:
        details = ["table = iceberg.schema.test_table", "WHERE id > 1"]
    else:
        details = ["table = iceberg.schema.test_table"]

    return PlanNode(
        id=node_id,
        name="ScanFilterAndProject",
        descriptor={"table": "iceberg.schema.test_table"},
        outputs=[OutputSymbol(symbol="id", type="bigint")],
        details=details,
        estimates=[
            CostEstimate(output_row_count=1000.0, cpu_cost=100.0),  # scan
            CostEstimate(output_row_count=100.0, cpu_cost=50.0),    # filter
            CostEstimate(output_row_count=100.0, cpu_cost=10.0),    # project
        ],
        children=children or [],
    )


class TestNormalizePlanTree:
    """Tests for normalize_plan_tree function."""

    def test_no_scan_filter_and_project_returns_unchanged(self) -> None:
        """normalize_plan_tree with no ScanFilterAndProject returns tree unchanged."""
        from mcp_trino_optimizer.parser.models import PlanNode
        from mcp_trino_optimizer.parser.normalizer import normalize_plan_tree

        root = PlanNode(
            id="0",
            name="Output",
            children=[PlanNode(id="1", name="TableScan")],
        )
        warnings: list = []
        result = normalize_plan_tree(root, warnings)

        assert result.name == "Output"
        assert result.children[0].name == "TableScan"
        assert len(warnings) == 0

    def test_scan_filter_and_project_decomposes_into_project_filter_tablescan(self) -> None:
        """ScanFilterAndProject decomposes into Project(Filter(TableScan))."""
        from mcp_trino_optimizer.parser.normalizer import normalize_plan_tree

        node = _make_scan_filter_and_project(with_filter=True)
        warnings: list = []
        result = normalize_plan_tree(node, warnings)

        # Root of decomposed subtree should be Project
        assert result.name == "Project"
        # Project wraps Filter
        assert len(result.children) == 1
        filter_node = result.children[0]
        assert filter_node.name == "Filter"
        # Filter wraps TableScan
        assert len(filter_node.children) == 1
        scan_node = filter_node.children[0]
        assert scan_node.name == "TableScan"

    def test_scan_filter_and_project_without_filter_decomposes_into_project_tablescan(self) -> None:
        """ScanFilterAndProject without filter decomposes into Project(TableScan)."""
        from mcp_trino_optimizer.parser.normalizer import normalize_plan_tree

        node = _make_scan_filter_and_project(with_filter=False)
        warnings: list = []
        result = normalize_plan_tree(node, warnings)

        assert result.name == "Project"
        assert len(result.children) == 1
        scan_node = result.children[0]
        assert scan_node.name == "TableScan"
        # No Filter in between
        assert not any(c.name == "Filter" for c in result.children)

    def test_decomposed_node_ids_use_suffixes(self) -> None:
        """Decomposed nodes have IDs: {original_id}_scan, _filter, _project."""
        from mcp_trino_optimizer.parser.normalizer import normalize_plan_tree

        node = _make_scan_filter_and_project(node_id="42", with_filter=True)
        warnings: list = []
        result = normalize_plan_tree(node, warnings)

        assert result.id == "42_project"
        assert result.children[0].id == "42_filter"
        assert result.children[0].children[0].id == "42_scan"

    def test_estimates_split_by_position(self) -> None:
        """Estimates list split correctly: index 0=scan, 1=filter, 2=project."""
        from mcp_trino_optimizer.parser.normalizer import normalize_plan_tree

        node = _make_scan_filter_and_project(with_filter=True)
        warnings: list = []
        result = normalize_plan_tree(node, warnings)

        # Project has estimates[2]
        assert len(result.estimates) == 1
        assert result.estimates[0].output_row_count == 100.0
        assert result.estimates[0].cpu_cost == 10.0

        # Filter has estimates[1]
        filter_node = result.children[0]
        assert len(filter_node.estimates) == 1
        assert filter_node.estimates[0].output_row_count == 100.0
        assert filter_node.estimates[0].cpu_cost == 50.0

        # TableScan has estimates[0]
        scan_node = filter_node.children[0]
        assert len(scan_node.estimates) == 1
        assert scan_node.estimates[0].output_row_count == 1000.0
        assert scan_node.estimates[0].cpu_cost == 100.0

    def test_iceberg_fields_transferred_to_table_scan(self) -> None:
        """Iceberg fields (iceberg_*) are transferred to TableScan node."""
        from mcp_trino_optimizer.parser.models import PlanNode
        from mcp_trino_optimizer.parser.normalizer import normalize_plan_tree

        node = PlanNode(
            id="1",
            name="ScanFilterAndProject",
            iceberg_split_count=5,
            iceberg_file_count=3,
            iceberg_partition_spec_id=0,
            details=["WHERE ts > '2025-01-01'"],
            outputs=[],
        )
        warnings: list = []
        result = normalize_plan_tree(node, warnings)

        # Walk to find TableScan
        scan = result.children[0].children[0]  # Project > Filter > TableScan
        assert scan.name == "TableScan"
        assert scan.iceberg_split_count == 5
        assert scan.iceberg_file_count == 3
        assert scan.iceberg_partition_spec_id == 0

    def test_model_extra_transferred_to_table_scan(self) -> None:
        """Unknown extra fields from model_extra go to TableScan node."""
        from mcp_trino_optimizer.parser.models import PlanNode
        from mcp_trino_optimizer.parser.normalizer import normalize_plan_tree

        node = PlanNode.model_validate(
            {
                "id": "1",
                "name": "ScanFilterAndProject",
                "details": ["WHERE id > 1"],
                "outputs": [],
                "futureVersionField": "someValue",
            }
        )
        warnings: list = []
        result = normalize_plan_tree(node, warnings)

        # Walk to find TableScan
        filter_node = result.children[0]
        scan = filter_node.children[0]
        assert scan.name == "TableScan"
        assert scan.raw.get("futureVersionField") == "someValue"

    def test_nested_scan_filter_and_project_all_normalized(self) -> None:
        """normalize_plan_tree normalizes ScanFilterAndProject inside Join children."""
        from mcp_trino_optimizer.parser.models import PlanNode
        from mcp_trino_optimizer.parser.normalizer import normalize_plan_tree

        # Build: Output > InnerJoin > [ScanFilterAndProject, ScanFilterAndProject]
        left_scan = _make_scan_filter_and_project(node_id="left", with_filter=False)
        right_scan = _make_scan_filter_and_project(node_id="right", with_filter=False)
        join = PlanNode(id="join", name="InnerJoin", children=[left_scan, right_scan])
        root = PlanNode(id="0", name="Output", children=[join])

        warnings: list = []
        result = normalize_plan_tree(root, warnings)

        join_result = result.children[0]
        assert join_result.name == "InnerJoin"
        # Both children should now be Project nodes
        assert join_result.children[0].name == "Project"
        assert join_result.children[1].name == "Project"

    def test_project_transparent_to_find_nodes_by_type(self) -> None:
        """find_nodes_by_type('TableScan') works through Project/Filter wrappers."""
        from mcp_trino_optimizer.parser.models import EstimatedPlan
        from mcp_trino_optimizer.parser.normalizer import normalize_plan_tree

        node = _make_scan_filter_and_project(with_filter=True)
        warnings: list = []
        normalized = normalize_plan_tree(node, warnings)

        plan = EstimatedPlan(root=normalized)
        table_scans = plan.find_nodes_by_type("TableScan")
        assert len(table_scans) == 1
        assert table_scans[0].name == "TableScan"

    def test_decomposition_produces_schema_drift_info_warning(self) -> None:
        """normalize_plan_tree records an info SchemaDriftWarning for each decomposed node."""
        from mcp_trino_optimizer.parser.normalizer import normalize_plan_tree

        node = _make_scan_filter_and_project(with_filter=True)
        warnings: list = []
        normalize_plan_tree(node, warnings)

        assert len(warnings) >= 1
        info_warnings = [w for w in warnings if w.severity == "info"]
        assert len(info_warnings) >= 1
