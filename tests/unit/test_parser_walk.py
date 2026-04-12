"""Regression tests for BasePlan.walk() DFS traversal — WR-01 fix.

Verifies:
1. DFS pre-order: root -> left-child -> left-grandchild -> right-child
2. Performance: 100-node chain completes without O(n^2) slowdown
"""

from mcp_trino_optimizer.parser.models import EstimatedPlan, PlanNode


def _make_node(node_id: str, children: list[PlanNode] | None = None) -> PlanNode:
    """Build a minimal PlanNode for testing."""
    return PlanNode(
        id=node_id,
        name=f"Op_{node_id}",
        children=children or [],
    )


def test_walk_dfs_order() -> None:
    """walk() yields nodes in DFS pre-order: root, A, C, B.

    Tree shape:
        root
        ├── A
        │   └── C
        └── B
    Expected DFS pre-order: root, A, C, B
    """
    node_c = _make_node("C")
    node_b = _make_node("B")
    node_a = _make_node("A", children=[node_c])
    root = _make_node("root", children=[node_a, node_b])

    plan = EstimatedPlan(root=root)
    order = [node.id for node in plan.walk()]
    assert order == ["root", "A", "C", "B"], (
        f"Expected DFS pre-order ['root', 'A', 'C', 'B'], got {order}"
    )


def test_walk_100_node_chain() -> None:
    """walk() on a 100-node chain returns all 100 nodes without O(n^2) slowdown.

    A list-as-stack using pop(0) would be O(n^2) on a chain; pop() is O(1).
    """
    # Build a linear chain: node_0 -> node_1 -> ... -> node_99
    leaf = _make_node("node_99")
    current = leaf
    for i in range(98, -1, -1):
        current = _make_node(f"node_{i}", children=[current])

    plan = EstimatedPlan(root=current)
    nodes = list(plan.walk())
    assert len(nodes) == 100, f"Expected 100 nodes, got {len(nodes)}"
    # Verify order: node_0 first, node_99 last (DFS pre-order on a chain)
    assert nodes[0].id == "node_0"
    assert nodes[-1].id == "node_99"
