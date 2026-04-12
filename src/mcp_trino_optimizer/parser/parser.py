"""Dual-path plan parser: EXPLAIN JSON -> EstimatedPlan, EXPLAIN ANALYZE text -> ExecutedPlan.

Two entry points:
- parse_estimated_plan: parses EXPLAIN (FORMAT JSON) output (JSON format)
- parse_executed_plan: parses EXPLAIN ANALYZE output (text format)

Security note (T-03-01, T-03-04): Size limits are enforced by the adapters before
calling these functions. The parser itself caps recursion depth at 100 levels to
prevent stack overflow from adversarially deep plans.
"""

from __future__ import annotations

import re
from typing import Any

import orjson
import structlog

from mcp_trino_optimizer.parser.models import (
    CostEstimate,
    EstimatedPlan,
    ExecutedPlan,
    OutputSymbol,
    ParseError,
    PlanNode,
    SchemaDriftWarning,
)
from mcp_trino_optimizer.parser.normalizer import normalize_plan_tree

log = structlog.get_logger(__name__)

# Maximum recursion depth for plan tree parsing (T-03-01: DoS protection)
_MAX_RECURSION_DEPTH = 100


def parse_estimated_plan(json_text: str, trino_version: str | None = None) -> EstimatedPlan:
    """Parse EXPLAIN (FORMAT JSON) output into a typed EstimatedPlan.

    Args:
        json_text: The raw JSON text from EXPLAIN (FORMAT JSON).
        trino_version: Optional Trino version string for provenance tracking.

    Returns:
        EstimatedPlan with a typed PlanNode tree. Unknown fields are in model_extra.
        SchemaDriftWarning entries indicate any unexpected structure.

    Raises:
        ParseError: If json_text is not valid JSON, or is not a JSON object (dict).
    """
    # Parse the JSON
    try:
        data = orjson.loads(json_text)
    except Exception as exc:
        raise ParseError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ParseError(f"Expected a JSON object (dict) at the top level, got {type(data).__name__}")

    warnings: list[SchemaDriftWarning] = []

    # Real Trino EXPLAIN (FORMAT JSON) wraps fragment root nodes in a top-level
    # dict keyed by fragment ID: {"0": {<root node>}, "1": {<fragment 2 root>}}.
    # Fragment "0" is the top-level output fragment.
    # Detect this format and unwrap to the root node.
    data = _unwrap_fragment_map(data, warnings)

    root = _build_node(data, "root", warnings, depth=0)

    # Normalize the tree (decompose ScanFilterAndProject etc.)
    root = normalize_plan_tree(root, warnings)

    plan = EstimatedPlan(
        root=root,
        schema_drift_warnings=warnings,
        source_trino_version=trino_version,
        raw_text=json_text,
    )

    if warnings:
        log.debug("schema_drift_warnings", count=len(warnings), plan_type="estimated")

    return plan


def parse_executed_plan(text: str, trino_version: str | None = None) -> ExecutedPlan:
    """Parse EXPLAIN ANALYZE text output into a typed ExecutedPlan.

    EXPLAIN ANALYZE does NOT support FORMAT JSON (Trino grammar limitation, issue #5786).
    This function parses the human-readable text tree format.

    Args:
        text: The raw text from EXPLAIN ANALYZE.
        trino_version: Optional Trino version string for provenance tracking.

    Returns:
        ExecutedPlan with a typed PlanNode tree and per-operator runtime metrics.
        Unknown/unparseable lines produce SchemaDriftWarning entries.
    """
    warnings: list[SchemaDriftWarning] = []

    if not text or not text.strip():
        # Return an empty plan with a synthetic root for truly empty input
        root = PlanNode(id="0", name="Unknown")
        return ExecutedPlan(
            root=root,
            schema_drift_warnings=warnings,
            source_trino_version=trino_version,
            raw_text=text,
        )

    root = _parse_explain_analyze_text(text, warnings)

    # Normalize the tree (decompose ScanFilterAndProject etc.)
    root = normalize_plan_tree(root, warnings)

    plan = ExecutedPlan(
        root=root,
        schema_drift_warnings=warnings,
        source_trino_version=trino_version,
        raw_text=text,
    )

    if warnings:
        log.debug("schema_drift_warnings", count=len(warnings), plan_type="executed")

    return plan


def parse_distributed_plan(text: str, trino_version: str | None = None) -> EstimatedPlan:
    """Parse EXPLAIN (TYPE DISTRIBUTED) text output into a typed EstimatedPlan.

    EXPLAIN (TYPE DISTRIBUTED) returns text (same format as EXPLAIN ANALYZE)
    showing fragment/stage layout without runtime metrics. Parsed with the same
    text parser as EXPLAIN ANALYZE, but wrapped in EstimatedPlan since it
    contains no runtime data.

    Args:
        text: The raw text from EXPLAIN (TYPE DISTRIBUTED).
        trino_version: Optional Trino version string for provenance tracking.

    Returns:
        EstimatedPlan with a typed PlanNode tree. No runtime metrics are populated.
    """
    warnings: list[SchemaDriftWarning] = []

    if not text or not text.strip():
        root = PlanNode(id="0", name="Unknown")
        return EstimatedPlan(
            root=root,
            schema_drift_warnings=warnings,
            source_trino_version=trino_version,
            raw_text=text,
        )

    root = _parse_explain_analyze_text(text, warnings)
    root = normalize_plan_tree(root, warnings)

    plan = EstimatedPlan(
        root=root,
        schema_drift_warnings=warnings,
        source_trino_version=trino_version,
        raw_text=text,
    )

    if warnings:
        log.debug("schema_drift_warnings", count=len(warnings), plan_type="distributed")

    return plan


# ── Private: EXPLAIN JSON parsing ─────────────────────────────────────────────


def _unwrap_fragment_map(
    data: dict[str, Any],
    warnings: list[SchemaDriftWarning],
) -> dict[str, Any]:
    """Unwrap the real Trino EXPLAIN (FORMAT JSON) fragment-keyed format.

    Real Trino EXPLAIN JSON output wraps fragment root nodes in a top-level dict
    keyed by fragment ID (string integers): {"0": {<root node>}, "1": {<fragment>}}.
    Fragment "0" is always the top-level output fragment.

    A direct node dict has "id" and "name" keys. A fragment map has integer string
    keys ("0", "1", etc.) mapping to node dicts.

    Args:
        data: The top-level dict from orjson.loads.
        warnings: Mutable list to append SchemaDriftWarning entries to.

    Returns:
        The root node dict (fragment "0") if fragment map, otherwise data unchanged.
    """
    # Direct node format: has "id" or "name" keys (used in tests)
    if "id" in data or "name" in data:
        return data

    # Check if all keys are string integers — fragment map format
    if all(k.isdigit() for k in data):
        # Fragment "0" is the top-level output fragment (the query root)
        if "0" in data and isinstance(data["0"], dict):
            if len(data) > 1:
                # Multi-fragment plan: document the extra fragments as drift info
                # (Phase 4 distributed plan parsing may want them, but Phase 3 ignores them)
                warnings.append(
                    SchemaDriftWarning(
                        node_path="root",
                        description=(
                            f"EXPLAIN JSON has {len(data)} fragments "
                            f"(keys: {sorted(data.keys())}). "
                            "Parsing fragment '0' (output fragment) as the plan root. "
                            "Other fragments are available in the raw fixture for distributed plan analysis."
                        ),
                        severity="info",
                    )
                )
            return data["0"]
        else:
            warnings.append(
                SchemaDriftWarning(
                    node_path="root",
                    description=(
                        f"Fragment map lacks key '0'; keys are {sorted(data.keys())}. "
                        "Using first available fragment as root."
                    ),
                    severity="warning",
                )
            )
            # Use lexicographically first key as fallback
            first_key = sorted(data.keys())[0]
            if isinstance(data[first_key], dict):
                return data[first_key]  # type: ignore[no-any-return]

    return data


def _build_node(
    node_dict: dict[str, Any],
    path: str,
    warnings: list[SchemaDriftWarning],
    depth: int,
) -> PlanNode:
    """Recursively build a PlanNode from an EXPLAIN JSON node dict.

    Args:
        node_dict: A single node's JSON dict.
        path: Current path in the tree for warning messages.
        warnings: Mutable list to append SchemaDriftWarning entries to.
        depth: Current recursion depth (capped at _MAX_RECURSION_DEPTH).

    Returns:
        A PlanNode with typed fields populated and model_extra for unknowns.
    """
    if depth > _MAX_RECURSION_DEPTH:
        warnings.append(
            SchemaDriftWarning(
                node_path=path,
                description=f"Plan tree exceeds maximum depth of {_MAX_RECURSION_DEPTH}; truncating.",
                severity="warning",
            )
        )
        return PlanNode(id=f"truncated_{depth}", name="TruncatedDepth")

    # Extract known fields, leaving unknown ones to be captured by model_extra
    node_id = node_dict.get("id", "")
    if not node_id:
        warnings.append(
            SchemaDriftWarning(
                node_path=path,
                field_name="id",
                description="Node missing 'id' field; using empty string default.",
                severity="warning",
            )
        )

    name = node_dict.get("name", "Unknown")
    if name == "Unknown" and "name" not in node_dict:
        warnings.append(
            SchemaDriftWarning(
                node_path=path,
                field_name="name",
                description="Node missing 'name' field; using 'Unknown' default.",
                severity="warning",
            )
        )

    # Parse children recursively
    raw_children = node_dict.get("children", [])
    children: list[PlanNode] = []
    if isinstance(raw_children, list):
        for i, child_dict in enumerate(raw_children):
            if isinstance(child_dict, dict):
                child = _build_node(child_dict, f"{path}.children[{i}]", warnings, depth + 1)
                children.append(child)
            else:
                warnings.append(
                    SchemaDriftWarning(
                        node_path=f"{path}.children[{i}]",
                        description=f"Child at index {i} is not a dict; skipping.",
                        severity="warning",
                    )
                )

    # Parse estimates
    raw_estimates = node_dict.get("estimates", [])
    estimates: list[CostEstimate] = []
    if isinstance(raw_estimates, list):
        for est in raw_estimates:
            if isinstance(est, dict):
                try:
                    estimates.append(CostEstimate.model_validate(est))
                except Exception:
                    warnings.append(
                        SchemaDriftWarning(
                            node_path=path,
                            field_name="estimates",
                            description=f"Could not parse estimate entry: {est}",
                            severity="warning",
                        )
                    )

    # Parse outputs
    raw_outputs = node_dict.get("outputs", [])
    outputs: list[OutputSymbol] = []
    if isinstance(raw_outputs, list):
        for out in raw_outputs:
            if isinstance(out, dict) and "symbol" in out and "type" in out:
                outputs.append(OutputSymbol(symbol=out["symbol"], type=out["type"]))

    # Parse details
    raw_details = node_dict.get("details", [])
    details: list[str] = []
    if isinstance(raw_details, list):
        details = [str(d) for d in raw_details]

    # Parse descriptor
    raw_descriptor = node_dict.get("descriptor", {})
    descriptor: dict[str, str] = {}
    if isinstance(raw_descriptor, dict):
        descriptor = {k: str(v) for k, v in raw_descriptor.items()}

    # Build the known-field subset to pass to PlanNode.
    # Unknown fields in node_dict will be captured by model_extra (extra='allow').
    known_keys = {"id", "name", "descriptor", "outputs", "details", "estimates", "children"}
    extra_fields = {k: v for k, v in node_dict.items() if k not in known_keys}

    node_data: dict[str, Any] = {
        "id": node_id,
        "name": name,
        "descriptor": descriptor,
        "outputs": outputs,
        "details": details,
        "estimates": estimates,
        "children": children,
        **extra_fields,
    }

    return PlanNode.model_validate(node_data)


# ── Private: EXPLAIN ANALYZE text parsing ─────────────────────────────────────

# Regex patterns for EXPLAIN ANALYZE text output
# Based on Trino's PlanPrinter output format

# Matches operator lines like:
#   "Output[columnNames = [returnflag]] => [returnflag:varchar(1)]"
#   "└─ Aggregate(FINAL)[returnflag]..."
#   "   - ScanFilterAndProject[table = ...]..."
_OPERATOR_LINE_RE = re.compile(
    r"^(?P<indent>\s*)(?:└─\s*|├─\s*|-\s*)?(?P<name>[A-Za-z][A-Za-z0-9]*)"
    r"(?:\[(?P<bracket_detail>[^\]]*)\])?(?:\((?P<paren_detail>[^)]*)\))?"
    r"(?:\[(?P<bracket_detail2>[^\]]*)\])?"
    r"(?:\s*=>\s*.*)?$"
)

# Matches CPU/timing lines like:
#   "CPU: 150.00ms, Scheduled: 200.00ms, Blocked: 0.00ns, Output: 100 rows (5.00kB)"
_CPU_LINE_RE = re.compile(
    r"CPU:\s*(?P<cpu_val>[\d.]+)(?P<cpu_unit>ms|s|ns|us)",
    re.IGNORECASE,
)

_SCHEDULED_LINE_RE = re.compile(
    r"Scheduled:\s*(?P<sched_val>[\d.]+)(?P<sched_unit>ms|s|ns|us)",
    re.IGNORECASE,
)

_BLOCKED_LINE_RE = re.compile(
    r"Blocked:\s*(?P<blocked_val>[\d.]+)(?P<blocked_unit>ms|s|ns|us)",
    re.IGNORECASE,
)

_OUTPUT_LINE_RE = re.compile(
    r"Output:\s*(?P<rows>[\d,]+)\s*rows\s*\((?P<size>[\d.]+)(?P<size_unit>[kKmMgGtT]?B)\)",
    re.IGNORECASE,
)

_INPUT_LINE_RE = re.compile(
    r"Input:\s*(?P<rows>[\d,]+)\s*rows\s*\((?P<size>[\d.]+)(?P<size_unit>[kKmMgGtT]?B)\)"
    r"(?:,\s*(?P<splits>\d+)\s*splits)?",
    re.IGNORECASE,
)

# Trino 480+ emits "Splits: N" (not "N splits") on the Input summary line.
# Example: "Input: 10 rows (533B), Physical input: 996B, ..., Splits: 1, ..."
_SPLITS_RE = re.compile(r"Splits:\s*(?P<splits>\d+)", re.IGNORECASE)

_PEAK_MEMORY_RE = re.compile(
    r"Peak\s*[Mm]emory(?:\s+[Uu]sage)?:\s*(?P<size>[\d.]+)(?P<unit>[kKmMgGtT]?B)",
    re.IGNORECASE,
)

_FILES_READ_RE = re.compile(
    r"Files\s+read:\s*(?P<count>\d+)",
    re.IGNORECASE,
)

# Fragment header line: "Fragment N [TYPE]"
_FRAGMENT_LINE_RE = re.compile(r"^Fragment\s+(\d+)\s*\[", re.IGNORECASE)


def _parse_duration_to_ms(value: str, unit: str) -> float:
    """Convert a duration string+unit to milliseconds."""
    v = float(value)
    unit_lower = unit.lower()
    if unit_lower == "s":
        return v * 1000.0
    elif unit_lower == "ms":
        return v
    elif unit_lower == "us":
        return v / 1000.0
    elif unit_lower == "ns":
        return v / 1_000_000.0
    return v


def _parse_size_to_bytes(value: str, unit: str) -> int:
    """Convert a size string+unit to bytes."""
    v = float(value.replace(",", ""))
    unit_lower = unit.lower()
    if unit_lower in ("b", ""):
        return int(v)
    elif unit_lower == "kb":
        return int(v * 1024)
    elif unit_lower == "mb":
        return int(v * 1024 * 1024)
    elif unit_lower == "gb":
        return int(v * 1024 * 1024 * 1024)
    elif unit_lower == "tb":
        return int(v * 1024 * 1024 * 1024 * 1024)
    return int(v)


def _parse_int_with_commas(value: str) -> int:
    """Parse an integer that may have comma separators."""
    return int(value.replace(",", ""))


def _extract_operator_name(line: str) -> str | None:
    """Extract the operator name from a plan line.

    Handles various line formats:
    - "Output[columnNames = [col]]"
    - "└─ Aggregate(FINAL)"
    - "   - ScanFilterAndProject[table = ...]"
    - "    TableScan[catalog.schema.table]"
    """
    # Strip leading whitespace and tree-drawing chars
    stripped = line.lstrip()
    stripped = re.sub(r"^[└├─\s\-]+", "", stripped).strip()

    if not stripped:
        return None

    # Extract the operator name (first CamelCase word)
    m = re.match(r"^([A-Za-z][A-Za-z0-9]*)", stripped)
    if m:
        return m.group(1)
    return None


def _get_indent_depth(line: str) -> int:
    """Get the indentation depth (number of leading spaces)."""
    return len(line) - len(line.lstrip())


def _parse_explain_analyze_text(text: str, warnings: list[SchemaDriftWarning]) -> PlanNode:
    """Parse EXPLAIN ANALYZE text into a PlanNode tree.

    Strategy: Identify operator lines by their CamelCase names at various
    indentation levels. Use indentation to reconstruct the tree hierarchy.
    Metric lines (CPU, Output, Input, etc.) following an operator line are
    attributed to that operator.
    """
    lines = text.splitlines()

    # Find the operator lines and build a flat list of (indent, name, metrics)
    # then reconstruct the tree from indentation structure.

    # First pass: identify operator lines
    operators: list[dict[str, Any]] = []
    current_op: dict[str, Any] | None = None
    node_counter = [0]  # mutable counter for node IDs

    for line_no, line in enumerate(lines):
        if not line.strip():
            continue

        # Skip Fragment header lines (they're metadata, not operators)
        if _FRAGMENT_LINE_RE.match(line.strip()):
            continue

        # Check if this looks like an operator line (CamelCase name)
        op_name = _extract_operator_name(line)
        indent = _get_indent_depth(line)

        # An operator line has a CamelCase name and typically follows tree structure
        # It should NOT start with metric keywords
        metric_keywords = {
            "CPU:",
            "Scheduled:",
            "Blocked:",
            "Output:",
            "Input:",
            "Peak",
            "Input",
            "Layout:",
            "Estimates:",
            "Distribution:",
            "Physical",
        }
        stripped_for_keyword = line.lstrip()
        is_metric_line = any(
            stripped_for_keyword.startswith(kw) or stripped_for_keyword.startswith(kw.lower()) for kw in metric_keywords
        )
        # Also catch lines like "Files read: N"
        is_metric_line = is_metric_line or bool(_FILES_READ_RE.search(line))
        is_metric_line = is_metric_line or bool(_CPU_LINE_RE.search(line) and "CPU:" in line)
        # Column assignment lines like "status := 5:status:varchar" are detail lines, not operators
        is_metric_line = is_metric_line or ":=" in stripped_for_keyword

        if op_name and not is_metric_line:
            # Looks like an operator line
            node_counter[0] += 1
            current_op = {
                "id": str(node_counter[0]),
                "name": op_name,
                "indent": indent,
                "line_no": line_no,
                "line": line,
                "cpu_time_ms": None,
                "wall_time_ms": None,
                "input_rows": None,
                "input_bytes": None,
                "output_rows": None,
                "output_bytes": None,
                "peak_memory_bytes": None,
                "physical_input_bytes": None,
                "spilled_bytes": None,
                "blocked_time_ms": None,
                "iceberg_split_count": None,
                "iceberg_file_count": None,
                "details": [],
            }
            operators.append(current_op)
        elif current_op is not None:
            # This is a metric or detail line for the current operator
            _extract_metrics_from_line(line, current_op, warnings)

    if not operators:
        # Could not parse any operators — return a minimal node with a warning
        warnings.append(
            SchemaDriftWarning(
                node_path="root",
                description="Could not parse any operator nodes from EXPLAIN ANALYZE text.",
                severity="warning",
            )
        )
        return PlanNode(id="0", name="Unknown")

    # Second pass: reconstruct tree from indentation levels
    return _build_tree_from_operators(operators, warnings)


def _extract_metrics_from_line(line: str, op: dict[str, Any], warnings: list[SchemaDriftWarning]) -> None:
    """Extract runtime metrics from a metric line and update the operator dict."""
    # CPU time
    cpu_m = _CPU_LINE_RE.search(line)
    if cpu_m and "CPU:" in line:
        op["cpu_time_ms"] = _parse_duration_to_ms(cpu_m.group("cpu_val"), cpu_m.group("cpu_unit"))

    # Wall/scheduled time
    sched_m = _SCHEDULED_LINE_RE.search(line)
    if sched_m:
        op["wall_time_ms"] = _parse_duration_to_ms(sched_m.group("sched_val"), sched_m.group("sched_unit"))

    # Blocked time
    blocked_m = _BLOCKED_LINE_RE.search(line)
    if blocked_m:
        op["blocked_time_ms"] = _parse_duration_to_ms(blocked_m.group("blocked_val"), blocked_m.group("blocked_unit"))

    # Output rows/bytes
    output_m = _OUTPUT_LINE_RE.search(line)
    if output_m and "Output:" in line:
        op["output_rows"] = _parse_int_with_commas(output_m.group("rows"))
        op["output_bytes"] = _parse_size_to_bytes(output_m.group("size"), output_m.group("size_unit"))

    # Input rows/bytes/splits
    input_m = _INPUT_LINE_RE.search(line)
    if input_m and "Input:" in line:
        op["input_rows"] = _parse_int_with_commas(input_m.group("rows"))
        op["input_bytes"] = _parse_size_to_bytes(input_m.group("size"), input_m.group("size_unit"))
        # Legacy format: "Input: N rows (XB), M splits"
        if input_m.group("splits"):
            op["iceberg_split_count"] = int(input_m.group("splits"))
        # Trino 480+ format: "Input: N rows (XB), ..., Splits: M, ..."
        elif op["iceberg_split_count"] is None:
            splits_m = _SPLITS_RE.search(line)
            if splits_m:
                op["iceberg_split_count"] = int(splits_m.group("splits"))

    # Peak memory
    peak_m = _PEAK_MEMORY_RE.search(line)
    if peak_m:
        op["peak_memory_bytes"] = _parse_size_to_bytes(peak_m.group("size"), peak_m.group("unit"))

    # Files read (Iceberg)
    files_m = _FILES_READ_RE.search(line)
    if files_m:
        op["iceberg_file_count"] = int(files_m.group("count"))


def _build_tree_from_operators(operators: list[dict[str, Any]], warnings: list[SchemaDriftWarning]) -> PlanNode:
    """Reconstruct a PlanNode tree from a flat list of operators with indent levels.

    Uses a stack to track the current parent chain. An operator at indent level N
    is a child of the last operator at indent level < N.
    """
    if not operators:
        return PlanNode(id="0", name="Unknown")

    # Convert operator dicts to PlanNode objects first
    nodes: list[tuple[int, PlanNode]] = []
    for op in operators:
        node = PlanNode(
            id=op["id"],
            name=op["name"],
            cpu_time_ms=op.get("cpu_time_ms"),
            wall_time_ms=op.get("wall_time_ms"),
            input_rows=op.get("input_rows"),
            input_bytes=op.get("input_bytes"),
            output_rows=op.get("output_rows"),
            output_bytes=op.get("output_bytes"),
            peak_memory_bytes=op.get("peak_memory_bytes"),
            physical_input_bytes=op.get("physical_input_bytes"),
            spilled_bytes=op.get("spilled_bytes"),
            blocked_time_ms=op.get("blocked_time_ms"),
            iceberg_split_count=op.get("iceberg_split_count"),
            iceberg_file_count=op.get("iceberg_file_count"),
            details=op.get("details", []),
        )
        nodes.append((op["indent"], node))

    # Build tree using a stack of (indent, node) pairs
    # The root is the first operator
    root_indent, root_node = nodes[0]

    # Stack tracks (indent_level, node) for potential parents
    stack: list[tuple[int, PlanNode]] = [(root_indent, root_node)]
    # We need mutable children — keep a mapping from node id to mutable children list
    children_map: dict[str, list[PlanNode]] = {root_node.id: []}

    for indent, node in nodes[1:]:
        # Initialize children list for this node
        children_map[node.id] = []

        # Pop stack until we find a parent with smaller indent
        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()

        # Current top of stack is the parent
        _parent_indent, parent_node = stack[-1]
        children_map[parent_node.id].append(node)

        # Push this node onto the stack
        stack.append((indent, node))

    # Now rebuild nodes with their children (PlanNode is immutable, need model_copy)
    return _attach_children(root_node, children_map)


def _attach_children(node: PlanNode, children_map: dict[str, list[PlanNode]]) -> PlanNode:
    """Recursively attach children from children_map to nodes."""
    child_nodes = children_map.get(node.id, [])
    rebuilt_children = [_attach_children(child, children_map) for child in child_nodes]

    if not rebuilt_children and not child_nodes:
        return node

    return node.model_copy(update={"children": rebuilt_children})
