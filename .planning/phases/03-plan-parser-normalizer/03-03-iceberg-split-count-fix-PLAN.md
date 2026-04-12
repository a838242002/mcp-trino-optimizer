---
phase: 03-plan-parser-normalizer
plan: 03
type: execute
wave: 1
gap_closure: true
uat_test: 5
depends_on: []
files_modified:
  - src/mcp_trino_optimizer/parser/parser.py
  - tests/parser/test_parser.py
  - tests/parser/__snapshots__/test_fixture_snapshots.ambr
---

# Plan 03-03: Fix iceberg_split_count Regex Mismatch (Gap Closure)

## Objective

Fix the regex mismatch that causes `iceberg_split_count` to always be `None`.

EXPLAIN ANALYZE emits `Splits: N` on the Input summary line, but `_INPUT_LINE_RE`
looks for `N splits` (number-then-word). The regex never matches, so `iceberg_split_count`
is always `None`. This violates PLN-04.

**Root cause:** `parser.py` line 360
- Current: `r"(?:,\s*(?P<splits>\d+)\s*splits)?"`
- Actual fixture format: `Input: 10 rows (533B), Physical input: 996B, ..., Splits: 1, ...`

## Tasks

### Task 1: Fix iceberg_split_count regex in parser.py

In `src/mcp_trino_optimizer/parser/parser.py`:

1. Remove the broken `(?:,\s*(?P<splits>\d+)\s*splits)?` optional group from `_INPUT_LINE_RE` (line 360)
2. Add a new standalone regex after `_INPUT_LINE_RE`:
   ```python
   _SPLITS_RE = re.compile(r"Splits:\s*(?P<splits>\d+)", re.IGNORECASE)
   ```
3. In `_extract_operator_metrics()` (around line 562–568), after the existing `input_m` block, apply `_SPLITS_RE` to the same line:
   ```python
   splits_m = _SPLITS_RE.search(line)
   if splits_m and "Input:" in line:
       op["iceberg_split_count"] = int(splits_m.group("splits"))
   ```
   The `"Input:" in line` guard ensures splits are only captured from the operator Input summary line.

### Task 2: Add test coverage

In `tests/parser/test_parser.py`, add:

```python
def test_iceberg_split_count_extracted_from_executed_plan():
    """iceberg_split_count must be parsed from 'Splits: N' in the Input line (PLN-04)."""
    raw = (Path(__file__).parent.parent / "fixtures/explain/480/iceberg_partition_filter_analyze.txt").read_text()
    plan = parse_executed_plan(raw)

    def find_scan(node):
        if "scan" in node.name.lower():
            return node
        for child in node.children:
            result = find_scan(child)
            if result:
                return result
        return None

    scan = find_scan(plan.root)
    assert scan is not None, "No scan node found"
    assert scan.iceberg_split_count == 1, f"Expected 1, got {scan.iceberg_split_count}"


def test_iceberg_split_count_none_for_estimated_plan():
    """iceberg_split_count must be None for EstimatedPlan — not a runtime metric (PLN-04)."""
    raw = (Path(__file__).parent.parent / "fixtures/explain/480/iceberg_partition_filter.json").read_text()
    plan = parse_estimated_plan(raw)

    def find_scan(node):
        if "scan" in node.name.lower():
            return node
        for child in node.children:
            result = find_scan(child)
            if result:
                return result
        return None

    scan = find_scan(plan.root)
    assert scan is not None, "No scan node found"
    assert scan.iceberg_split_count is None
```

### Task 3: Update syrupy snapshots

The snapshot for `iceberg_partition_filter_analyze` will now include `iceberg_split_count: 1`.
Update snapshots:

```bash
uv run pytest tests/parser/test_fixture_snapshots.py --snapshot-update
```

Verify all other snapshots are unchanged (only the iceberg fixture snapshots should differ).

Commit: `fix(03): correct iceberg_split_count regex — Splits: N format (PLN-04)`

## Success Criteria

- [ ] `iceberg_split_count` returns `1` for `iceberg_partition_filter_analyze.txt`
- [ ] `iceberg_split_count` is `None` for `iceberg_partition_filter.json` (EstimatedPlan — by design)
- [ ] All pre-existing tests still pass (357+)
- [ ] New tests for `iceberg_split_count` pass
- [ ] Snapshots updated and committed
