"""Plan tree normalizer: decomposes fused Trino operators into canonical forms.

Phase 3 normalization scope (D-13):
- ScanFilterAndProject -> TableScan + Filter (optional) + Project
- Project wrapper walk-through is inherent (DFS walk already traverses through Project)

NOTE: The actual Trino operator name is "ScanFilterAndProject" (NOT "ScanFilterProject").
See 03-RESEARCH.md Pitfall 3.
"""

from __future__ import annotations

import re

from mcp_trino_optimizer.parser.models import (
    CostEstimate,
    PlanNode,
    SchemaDriftWarning,
)

# Exact Trino operator name for the fused scan+filter+project node.
# IMPORTANT: This is "ScanFilterAndProject" (with "And"), not "ScanFilterProject".
SCAN_FILTER_AND_PROJECT = "ScanFilterAndProject"

# Filter predicate heuristics: keywords that unambiguously indicate a SQL predicate.
# NOTE: bare "=" is too broad — it also appears in "table = schema.name" descriptor entries.
# We check for WHERE keyword, filterPredicate key, SQL predicate keywords, and
# comparison operators other than plain "=" (e.g. !=, <>, >=, <=, >, <).
_FILTER_KEYWORDS = frozenset(
    {
        "WHERE",
        "FILTERPREDICATE",  # Trino detail line key (case-insensitive match used below)
        "BETWEEN",
        "LIKE",
        "IS NULL",
        "IS NOT NULL",
        "IS DISTINCT",
        "NOT IN",
    }
)

# Comparison operators that definitively indicate a predicate (not a descriptor key=value).
# Also matches = followed by a quoted string or numeric literal to catch bare equality
# predicates like `status = 'open'` or `id = 42` without false-positives on `table = schema.name`.
_COMPARISON_OPS_RE = re.compile(
    r"(?:!=|<>|>=|<=|(?<![=<>!])[><](?![=])|(?<![=<>!])=\s*(?:'[^']*'|\d))"
)


def normalize_plan_tree(root: PlanNode, warnings: list[SchemaDriftWarning]) -> PlanNode:
    """Normalize the plan tree, decomposing fused operators.

    Performs bottom-up (children-first) transformation so that nested
    ScanFilterAndProject nodes inside joins etc. are also handled.

    Args:
        root: Root of the plan tree to normalize.
        warnings: Mutable list to append SchemaDriftWarning entries to.

    Returns:
        The normalized root node (may be the same or a new node).
    """
    return _normalize_node(root, "root", warnings)


def _normalize_node(node: PlanNode, path: str, warnings: list[SchemaDriftWarning]) -> PlanNode:
    """Recursively normalize a single node and its children.

    Children are normalized first (bottom-up) so that nested fused nodes
    inside subtrees are handled before the parent.
    """
    # First, normalize all children recursively (bottom-up)
    new_children = [_normalize_node(child, f"{path}.children[{i}]", warnings) for i, child in enumerate(node.children)]

    # Rebuild node with normalized children if any changed
    if new_children != list(node.children):
        node = node.model_copy(update={"children": new_children})

    # Then, check if this node itself needs decomposition
    if node.name == SCAN_FILTER_AND_PROJECT:
        return _decompose_scan_filter_and_project(node, path, warnings)

    return node


def _has_filter_predicate(details: list[str]) -> bool:
    """Heuristically determine if a details list contains a SQL filter predicate.

    Avoids false positives from "table = schema.name" descriptor entries by
    requiring either explicit SQL keywords (WHERE, BETWEEN, etc.) or
    comparison operators other than plain "=" (!=, <>, >, <, >=, <=).
    """
    for detail in details:
        detail_upper = detail.upper()
        # Check for unambiguous SQL predicate keywords
        if any(kw in detail_upper for kw in _FILTER_KEYWORDS):
            return True
        # Check for comparison operators (!=, <>, >, <, >=, <=)
        if _COMPARISON_OPS_RE.search(detail):
            return True
    return False


def _get_estimate(estimates: list[CostEstimate], index: int) -> list[CostEstimate]:
    """Safely get a single estimate by index, or return empty list."""
    if index < len(estimates):
        return [estimates[index]]
    return []


def _decompose_scan_filter_and_project(node: PlanNode, path: str, warnings: list[SchemaDriftWarning]) -> PlanNode:
    """Decompose a ScanFilterAndProject node into TableScan + Filter + Project.

    Per 03-RESEARCH.md Pattern 5:
    - estimates[0] goes to TableScan
    - estimates[1] goes to Filter (if present)
    - estimates[2] goes to Project

    The original node's children become children of TableScan.
    Iceberg fields (iceberg_*) are transferred to TableScan.
    Unknown extra fields (model_extra) go to TableScan.
    """
    has_filter = _has_filter_predicate(node.details)

    # Split details: predicate lines vs table/descriptor lines
    filter_details = [d for d in node.details if _has_filter_predicate([d])]
    table_details = [d for d in node.details if not _has_filter_predicate([d])]

    # Build TableScan node
    scan_node_data = {
        "id": f"{node.id}_scan",
        "name": "TableScan",
        "descriptor": node.descriptor,
        "outputs": [],  # TableScan outputs are raw columns; handled by Project
        "details": table_details,
        "estimates": _get_estimate(node.estimates, 0),
        "children": list(node.children),  # original children of the fused node
        # Transfer Iceberg fields
        "iceberg_split_count": node.iceberg_split_count,
        "iceberg_file_count": node.iceberg_file_count,
        "iceberg_partition_spec_id": node.iceberg_partition_spec_id,
        # Transfer runtime metrics (populated for executed plans)
        "cpu_time_ms": node.cpu_time_ms,
        "wall_time_ms": node.wall_time_ms,
        "input_rows": node.input_rows,
        "input_bytes": node.input_bytes,
        "peak_memory_bytes": node.peak_memory_bytes,
        "physical_input_bytes": node.physical_input_bytes,
        "spilled_bytes": node.spilled_bytes,
        "blocked_time_ms": node.blocked_time_ms,
        # Transfer unknown extra fields from model_extra (version-specific fields)
        **node.raw,
    }
    scan_node = PlanNode.model_validate(scan_node_data)

    if has_filter:
        # Build Filter node wrapping TableScan
        filter_node = PlanNode(
            id=f"{node.id}_filter",
            name="Filter",
            descriptor={},
            outputs=[],
            details=filter_details,
            estimates=_get_estimate(node.estimates, 1),
            children=[scan_node],
        )
        inner_node: PlanNode = filter_node
    else:
        inner_node = scan_node

    # Build Project node wrapping Filter (or TableScan if no filter)
    project_node = PlanNode(
        id=f"{node.id}_project",
        name="Project",
        descriptor={},
        outputs=node.outputs,
        details=[],
        estimates=_get_estimate(node.estimates, 2),
        children=[inner_node],
        # Transfer output metrics to Project (the outermost node)
        output_rows=node.output_rows,
        output_bytes=node.output_bytes,
    )

    warnings.append(
        SchemaDriftWarning(
            node_path=path,
            description=(
                f"ScanFilterAndProject node (id={node.id}) decomposed into "
                + ("Project(Filter(TableScan))" if has_filter else "Project(TableScan)")
            ),
            severity="info",
        )
    )

    return project_node
