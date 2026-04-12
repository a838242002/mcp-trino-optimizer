---
phase: 03-plan-parser-normalizer
reviewed: 2026-04-12T14:42:56Z
depth: standard
files_reviewed: 18
files_reviewed_list:
  - src/mcp_trino_optimizer/parser/__init__.py
  - src/mcp_trino_optimizer/parser/models.py
  - src/mcp_trino_optimizer/parser/parser.py
  - src/mcp_trino_optimizer/parser/normalizer.py
  - src/mcp_trino_optimizer/adapters/trino/_explain_plan.py
  - src/mcp_trino_optimizer/ports/plan_source.py
  - src/mcp_trino_optimizer/ports/__init__.py
  - src/mcp_trino_optimizer/adapters/offline/json_plan_source.py
  - src/mcp_trino_optimizer/adapters/trino/live_plan_source.py
  - src/mcp_trino_optimizer/adapters/trino/client.py
  - scripts/capture_fixtures.py
  - tests/parser/test_models.py
  - tests/parser/test_parser.py
  - tests/parser/test_normalizer.py
  - tests/parser/test_fixture_snapshots.py
  - tests/adapters/test_offline_plan_source.py
  - tests/adapters/test_port_conformance.py
  - tests/adapters/test_ports.py
findings:
  critical: 0
  warning: 4
  info: 5
  total: 9
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-04-12T14:42:56Z
**Depth:** standard
**Files Reviewed:** 18
**Status:** issues_found

## Summary

Phase 3 introduces the plan parser, normalizer, and adapter wiring for Trino EXPLAIN output. The architecture is sound: clean hexagonal ports, a typed domain model with `model_extra` for forward-compatibility, and a deterministic normalizer for `ScanFilterAndProject` decomposition. Security constraints (1MB cap, read-only guard, no SQL logging) are consistently applied.

Four warnings were found, all related to logic correctness: a quadratic `walk()` implementation that will silently produce wrong DFS order on deep trees, a resource leak in the fixture capture script, a silent data-loss path when `_execute_explain` receives text output from EXPLAIN ANALYZE, and a filter-predicate false-negative for BETWEEN/LIKE patterns without quoting. Five informational items cover dead code, a missing test assertion, a magic number, an ambiguous test signal, and a minor naming inconsistency.

No security vulnerabilities were found.

---

## Warnings

### WR-01: `BasePlan.walk()` uses `stack.pop(0)` — O(n²) list shift and incorrect DFS pre-order

**File:** `src/mcp_trino_optimizer/parser/models.py:165-168`

**Issue:** `walk()` uses a plain `list` as a stack and calls `stack.pop(0)` (dequeue from the front) combined with `stack = list(node.children) + stack` (prepend children). `pop(0)` on a Python list is O(n) — repeated N times, the full traversal is O(n²). More critically, the ordering logic is inconsistent: prepending children to the remaining stack then popping from the front does not produce correct depth-first pre-order on trees with branching factors > 1. For a root with children [A, B] where A has children [C, D], the visit order is root → A → C → D → B (correct), but this only works because `pop(0)` and `children + stack` happen to cancel out. A simpler, correct, and O(n) formulation uses `append`/`pop()` from the right:

```python
def walk(self) -> Iterator[PlanNode]:
    stack = [self.root]
    while stack:
        node = stack.pop()          # O(1)
        yield node
        stack.extend(reversed(node.children))  # preserve left-to-right child order
```

**Fix:** Replace `stack.pop(0)` with `stack.pop()` and change `stack = list(node.children) + stack` to `stack.extend(reversed(node.children))`. This is also consistent with what the existing `test_walk_yields_all_nodes_dfs` test expects (root=0, children=[1,2] → visits 0, 1, 2).

---

### WR-02: `_execute_explain` in `TrinoClient` always calls `_json.loads` even for EXPLAIN ANALYZE text

**File:** `src/mcp_trino_optimizer/adapters/trino/client.py:361-364`

**Issue:** `_execute_explain` is called for all three plan types: `"estimated"`, `"executed"`, and `"distributed"`. For `"executed"` (EXPLAIN ANALYZE), Trino returns plain text — not JSON. The code unconditionally attempts `_json.loads(plan_text)` and on failure falls back to `{"raw": plan_text}`. This means the raw EXPLAIN ANALYZE text is silently packed into a synthetic `{"raw": "..."}` dict in `plan_json`, while `raw_text` correctly holds the original text. `LivePlanSource.fetch_analyze_plan` then discards `plan_json` and uses `raw_text`, which is correct — but only by accident. If `raw_text` is ever empty (e.g., Trino returns an empty first row), the fallback `analyze_text = result.raw_text or ""` passes an empty string to `parse_executed_plan`, which returns a synthetic `Unknown` root with no warning to the caller.

Additionally, stdlib `json` is imported inside the function body (`import json as _json`) rather than at module level. This is a minor style issue but also means the import cost is paid on every call.

```python
# At module level (top of client.py):
import json as _json

# In _execute_explain, replace the current block with explicit branching:
if plan_type == "executed":
    # EXPLAIN ANALYZE returns plain text — do not attempt JSON parse
    plan_text_for_json: dict[str, Any] = {}
else:
    try:
        plan_text_for_json = _json.loads(plan_text) if plan_text else {}
    except _json.JSONDecodeError:
        plan_text_for_json = {"raw": plan_text}

return ExplainPlan(
    plan_json=plan_text_for_json,
    plan_type=plan_type,
    raw_text=plan_text,
)
```

**Fix:** Add a branch on `plan_type == "executed"` to skip the JSON parse entirely and store `{}` in `plan_json`. Move the `import json` to module scope.

---

### WR-03: `_capture_explain_json` and `_capture_explain_analyze` in `capture_fixtures.py` leak cursors on exception

**File:** `scripts/capture_fixtures.py:100-104`, `141-148`, `151-158`

**Issue:** `_execute_query` creates a cursor but only calls `cursor.fetchall()` with no `finally` block to close the cursor or connection. If `cursor.execute(sql)` or `cursor.fetchall()` raises, both the cursor and connection are left open. In a long fixture capture run, this can exhaust the Trino connection pool. The same pattern affects `_detect_version`, `_setup_test_table`, `_capture_explain_json`, and `_capture_explain_analyze`, all of which call `_execute_query` and rely on connection cleanup by GC.

```python
def _execute_query(conn: trino.dbapi.Connection, sql: str) -> list[list]:
    """Execute a SQL statement and return all rows."""
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        return cursor.fetchall()
    finally:
        with contextlib.suppress(Exception):
            cursor.close()
```

**Fix:** Wrap the cursor in a `try/finally` (or `with` if the trino cursor supports context manager) to guarantee `cursor.close()` is called even on exception.

---

### WR-04: `_has_filter_predicate` false-negative for BETWEEN/LIKE predicates without SQL operators

**File:** `src/mcp_trino_optimizer/parser/normalizer.py:82-97`

**Issue:** `_has_filter_predicate` checks `_FILTER_KEYWORDS` (which includes `"BETWEEN"` and `"LIKE"`) and `_COMPARISON_OPS_RE`. However, the keyword check is done with `any(kw in detail_upper ...)`. The keyword `"BETWEEN"` and `"LIKE"` will correctly match. But the code comment says "bare `=` is too broad" and excludes plain `=` from `_COMPARISON_OPS_RE`. A detail line like `"filterPredicate = (status = 'open')"` — which contains only plain `=` signs and the `FILTERPREDICATE` keyword — will be matched by the `FILTERPREDICATE` keyword check. That part is fine.

The actual gap is: a detail line containing only `"status = 'open'"` (no keyword prefix, no `!=`/`<>`/`>`/`<`) will be misclassified as a table descriptor entry and moved to `table_details`, causing the decomposition to omit the Filter node. This is a correctness risk: equality predicates injected at the detail level without a `filterPredicate` prefix will silently disappear from the Filter node and end up in TableScan's details instead.

```python
# Add plain = with string/numeric literal patterns to _COMPARISON_OPS_RE:
_COMPARISON_OPS_RE = re.compile(
    r"(?:!=|<>|>=|<=|(?<![=<>!])[><](?![=])|(?<![=<>!])=\s*(?:'[^']*'|\d))"
)
```

**Fix:** Extend `_COMPARISON_OPS_RE` to also match `= 'literal'` and `= number` patterns (i.e., `=` followed by whitespace and a quoted string or digit), which unambiguously indicates a predicate rather than a descriptor key assignment.

---

## Info

### IN-01: `_unwrap_fragment_map` fallback path returns `data` unchanged when no integer-keyed fragment and no `id`/`name`

**File:** `src/mcp_trino_optimizer/parser/parser.py:186-193`

**Issue:** When the fragment map has all-digit keys but lacks key `"0"` AND `isinstance(data[first_key], dict)` is False (e.g., the first value is a list or scalar), the function falls through to `return data` — returning the original unmodified dict to `_build_node`. This will cause `_build_node` to produce a node with `id=""` and `name="Unknown"` with a warning, which is acceptable degradation. However the code path is silently reached without an additional warning explaining that the fragment-map unwrapping itself failed. Consider appending a second `SchemaDriftWarning` in the else branch before `return data`.

**Fix:** Add a `warnings.append(SchemaDriftWarning(..., severity="warning"))` before `return data` in the inner else branch (line 191) to make the failure path observable.

---

### IN-02: `capture_fixtures.py` `_execute_query` return type annotation is `list[list]` but callers expect `list[list[Any]]`

**File:** `scripts/capture_fixtures.py:100`

**Issue:** The return type is annotated `list[list]` (unparameterized inner `list`), which is technically `list[list[Unknown]]`. This is inconsistent with the codebase's use of `list[dict[str, Any]]` elsewhere. While this is a script (not production code), the inconsistency will cause mypy strict mode warnings.

**Fix:** Change the annotation to `list[list[Any]]` and add `from typing import Any` at the top of the script.

---

### IN-03: `test_schema_drift_warning_for_missing_id` has no assertion on the warning

**File:** `tests/parser/test_parser.py:198-218`

**Issue:** The test documents the intent ("a child node without 'id' should produce a warning") but the assertion is `assert plan is not None` — which tests nothing meaningful since `parse_estimated_plan` would have to raise for this to fail. The actual requirement — that a `SchemaDriftWarning` is emitted — is not verified.

**Fix:** Add `assert any(w.field_name == "id" for w in plan.schema_drift_warnings)` to make the test actually verify the documented behavior.

---

### IN-04: `_parse_size_to_bytes` does not handle case-insensitive `"kB"` unit variants correctly

**File:** `src/mcp_trino_optimizer/parser/parser.py:393-407`

**Issue:** `_parse_size_to_bytes` lowercases the unit before comparison and checks for `"kb"`, `"mb"`, `"gb"`, `"tb"`. The regex `_OUTPUT_LINE_RE` captures `[kKmMgGtT]?B` which means the unit group could be `"B"`, `"kB"`, `"KB"`, `"MB"`, `"mB"`, `"GB"`, `"gB"`, `"TB"`, `"tB"`. After `unit.lower()`, `"kB"` → `"kb"` which matches the check. This is correct. However `"B"` alone (bare bytes) hits `unit_lower in ("b", "")` — but the regex requires `B` (capital) as the last character. `unit.lower()` of `"B"` is `"b"` which correctly matches. No actual bug, but the check `unit_lower in ("b", "")` for empty string is dead code: the regex always captures at least `"B"`, so the unit group can never be empty.

**Fix:** Remove the `""` from the bytes check: `if unit_lower == "b":`. Low priority — dead code only.

---

### IN-05: `BasePlan.walk()` docstring says "depth-first, pre-order" but implementation traverses breadth-first

**File:** `src/mcp_trino_optimizer/parser/models.py:159-168`

**Issue:** As noted in WR-01, the current implementation (`pop(0)` + prepend children) produces correct DFS pre-order for simple linear chains but the docstring claim would be violated for any tree with branching. After the WR-01 fix the docstring will be accurate. This item is a documentation inconsistency that is resolved as a side-effect of fixing WR-01 — tracking it separately for completeness.

**Fix:** Resolved when WR-01 is applied.

---

_Reviewed: 2026-04-12T14:42:56Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
