---
phase: 03-plan-parser-normalizer
plan: 02
type: execute
wave: 2
depends_on:
  - 03-01
files_modified:
  - scripts/capture_fixtures.py
  - tests/fixtures/explain/480/simple_select.json
  - tests/fixtures/explain/480/simple_select_analyze.txt
  - tests/fixtures/explain/480/full_scan.json
  - tests/fixtures/explain/480/full_scan_analyze.txt
  - tests/fixtures/explain/480/aggregate.json
  - tests/fixtures/explain/480/aggregate_analyze.txt
  - tests/fixtures/explain/480/join.json
  - tests/fixtures/explain/480/join_analyze.txt
  - tests/fixtures/explain/480/iceberg_partition_filter.json
  - tests/fixtures/explain/480/iceberg_partition_filter_analyze.txt
  - tests/fixtures/explain/455/simple_select.json
  - tests/fixtures/explain/455/simple_select_analyze.txt
  - tests/fixtures/explain/455/aggregate.json
  - tests/fixtures/explain/455/aggregate_analyze.txt
  - tests/fixtures/explain/429/simple_select.json
  - tests/fixtures/explain/429/simple_select_analyze.txt
  - tests/fixtures/explain/429/aggregate.json
  - tests/fixtures/explain/429/aggregate_analyze.txt
  - tests/parser/test_fixture_snapshots.py
  - pyproject.toml
autonomous: true
requirements:
  - PLN-06

must_haves:
  truths:
    - "At least 3 Trino versions (429, ~455, 480) have captured EXPLAIN JSON and EXPLAIN ANALYZE text fixtures"
    - "Every fixture file parses without error through the parser from Plan 01"
    - "Syrupy snapshot tests gate the parsed output of every fixture in CI"
    - "When a Trino version adds a new field, the snapshot diff shows the change cleanly"
  artifacts:
    - path: "tests/fixtures/explain/480/simple_select.json"
      provides: "EXPLAIN (FORMAT JSON) fixture from Trino 480"
      min_lines: 10
    - path: "tests/fixtures/explain/480/simple_select_analyze.txt"
      provides: "EXPLAIN ANALYZE text fixture from Trino 480"
      min_lines: 5
    - path: "tests/fixtures/explain/429/simple_select.json"
      provides: "EXPLAIN (FORMAT JSON) fixture from Trino 429"
      min_lines: 10
    - path: "tests/parser/test_fixture_snapshots.py"
      provides: "Syrupy snapshot tests for all fixtures"
      contains: "snapshot"
    - path: "scripts/capture_fixtures.py"
      provides: "Automated fixture capture script"
      contains: "EXPLAIN"
  key_links:
    - from: "tests/parser/test_fixture_snapshots.py"
      to: "tests/fixtures/explain/"
      via: "loads fixture files and parses through parser"
      pattern: "parse_estimated_plan|parse_executed_plan"
    - from: "tests/parser/test_fixture_snapshots.py"
      to: "syrupy snapshot assertions"
      via: "assert result == snapshot"
      pattern: "snapshot"
    - from: "scripts/capture_fixtures.py"
      to: ".testing/docker-compose.yml"
      via: "connects to Trino via docker-compose stack"
      pattern: "docker-compose|trino"
---

<objective>
Capture the multi-version Trino fixture corpus and create syrupy snapshot tests that gate parsed
output in CI. This is the drift detection alarm for the entire rule engine.

Purpose: Every rule in Phase 4 depends on the parser producing stable, correct output from real
Trino EXPLAIN data. The fixture corpus provides regression coverage across Trino versions, and
snapshot tests surface field changes as clean diffs rather than crashes.

Output: Fixture files for 3 Trino versions, a capture script for re-running when versions change,
and snapshot tests that parse every fixture and assert stable output.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/03-plan-parser-normalizer/03-CONTEXT.md
@.planning/phases/03-plan-parser-normalizer/03-RESEARCH.md
@.planning/phases/03-plan-parser-normalizer/03-01-SUMMARY.md

<interfaces>
<!-- From Plan 01 output -->
From src/mcp_trino_optimizer/parser/__init__.py:
```python
from mcp_trino_optimizer.parser.parser import parse_estimated_plan, parse_executed_plan
from mcp_trino_optimizer.parser.models import EstimatedPlan, ExecutedPlan, PlanNode
```

From src/mcp_trino_optimizer/parser/models.py:
```python
class BasePlan(BaseModel):
    root: PlanNode
    schema_drift_warnings: list[SchemaDriftWarning] = []
    source_trino_version: str | None = None
    def walk(self) -> Iterator[PlanNode]: ...
    def find_nodes_by_type(self, operator_type: str) -> list[PlanNode]: ...
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Fixture capture script and multi-version corpus</name>
  <files>
    scripts/capture_fixtures.py
    tests/fixtures/explain/480/simple_select.json
    tests/fixtures/explain/480/simple_select_analyze.txt
    tests/fixtures/explain/480/full_scan.json
    tests/fixtures/explain/480/full_scan_analyze.txt
    tests/fixtures/explain/480/aggregate.json
    tests/fixtures/explain/480/aggregate_analyze.txt
    tests/fixtures/explain/480/join.json
    tests/fixtures/explain/480/join_analyze.txt
    tests/fixtures/explain/480/iceberg_partition_filter.json
    tests/fixtures/explain/480/iceberg_partition_filter_analyze.txt
    tests/fixtures/explain/455/simple_select.json
    tests/fixtures/explain/455/simple_select_analyze.txt
    tests/fixtures/explain/455/aggregate.json
    tests/fixtures/explain/455/aggregate_analyze.txt
    tests/fixtures/explain/429/simple_select.json
    tests/fixtures/explain/429/simple_select_analyze.txt
    tests/fixtures/explain/429/aggregate.json
    tests/fixtures/explain/429/aggregate_analyze.txt
  </files>
  <read_first>
    .testing/docker-compose.yml
    tests/integration/conftest.py
    .planning/phases/03-plan-parser-normalizer/03-RESEARCH.md
  </read_first>
  <action>
**Create `scripts/capture_fixtures.py`:**

A standalone Python script that:
1. Connects to a running Trino instance (host/port from env vars `TRINO_HOST=localhost`, `TRINO_PORT=8080`, or CLI args).
2. Creates an Iceberg test schema and table if they don't exist:
   - `CREATE SCHEMA IF NOT EXISTS iceberg.test_fixtures`
   - `CREATE TABLE IF NOT EXISTS iceberg.test_fixtures.orders (id BIGINT, name VARCHAR, amount DECIMAL(10,2), ts TIMESTAMP(6) WITH TIME ZONE, status VARCHAR) WITH (partitioning = ARRAY['day(ts)'])`
   - Insert 100+ sample rows spanning multiple days/partitions.
3. For each query in the set:
   - `simple_select`: `SELECT id, name FROM iceberg.test_fixtures.orders WHERE id > 10`
   - `full_scan`: `SELECT * FROM iceberg.test_fixtures.orders`
   - `aggregate`: `SELECT status, COUNT(*), SUM(amount) FROM iceberg.test_fixtures.orders GROUP BY status`
   - `join`: `SELECT a.id, a.name, b.status FROM iceberg.test_fixtures.orders a JOIN iceberg.test_fixtures.orders b ON a.id = b.id WHERE a.amount > 100`
   - `iceberg_partition_filter`: `SELECT * FROM iceberg.test_fixtures.orders WHERE ts >= TIMESTAMP '2025-01-15 00:00:00 UTC' AND ts < TIMESTAMP '2025-01-16 00:00:00 UTC'`
4. For each query, run:
   - `EXPLAIN (FORMAT JSON) <query>` -- save result to `tests/fixtures/explain/{version}/{name}.json`
   - `EXPLAIN ANALYZE <query>` -- save result to `tests/fixtures/explain/{version}/{name}_analyze.txt`
5. Accept `--version` CLI arg (default: auto-detect from `SELECT node_version FROM system.runtime.nodes`).
6. Create output directories if they don't exist.
7. Use the `trino` Python client library for connections.

**Capture process for multi-version fixtures:**

For Trino 480 (current docker-compose):
- Run `docker compose -f .testing/docker-compose.yml up -d` (if not already running).
- Wait for Trino readiness.
- Run `python scripts/capture_fixtures.py --version 480`.
- Capture all 5 query pairs (JSON + text) = 10 files.

For Trino 455 and 429:
- These versions may not be available in the current docker-compose stack.
- **Pragmatic approach**: Capture Trino 480 fixtures with the full query set. For 455 and 429, capture at minimum `simple_select` and `aggregate` (the two simplest queries) by temporarily changing the Trino image tag in `.testing/docker-compose.yml` and re-running the capture script.
- If 429 or 455 have Iceberg/Lakekeeper compatibility issues (Lakekeeper may not work with older Trino), capture those versions with a simpler setup (e.g., memory connector or Hive) and document the limitation. The point is to verify EXPLAIN JSON structure stability across versions.
- Store whatever is captured. The fixture corpus is additive -- more versions can be added later.

**Important:** The capture script and fixture capture may require the docker-compose stack to be running. If the executor cannot run the stack (no Docker), create the capture script and at minimum populate Trino 480 fixtures. For 455 and 429, if capture is not possible, create synthetic fixture files based on the JSON structure documented in 03-RESEARCH.md, clearly marked with a comment `// Synthetic fixture - replace with live capture from Trino {version}`. This ensures snapshot tests can be written and run immediately.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && ls tests/fixtures/explain/480/simple_select.json tests/fixtures/explain/480/simple_select_analyze.txt tests/fixtures/explain/429/simple_select.json tests/fixtures/explain/429/simple_select_analyze.txt 2>&1 && python -c "import json; json.load(open('tests/fixtures/explain/480/simple_select.json'))" 2>&1</automated>
  </verify>
  <acceptance_criteria>
    - scripts/capture_fixtures.py exists and contains `EXPLAIN (FORMAT JSON)` and `EXPLAIN ANALYZE`
    - tests/fixtures/explain/480/ directory contains at least simple_select.json and simple_select_analyze.txt
    - tests/fixtures/explain/429/ directory contains at least simple_select.json and simple_select_analyze.txt
    - tests/fixtures/explain/455/ directory contains at least simple_select.json and simple_select_analyze.txt (or nearest available version)
    - All .json fixture files are valid JSON (parseable by json.load)
    - All _analyze.txt fixture files are non-empty text
    - scripts/capture_fixtures.py accepts --version CLI argument
  </acceptance_criteria>
  <done>
    Fixture corpus captured from 3 Trino versions. Capture script exists for re-running.
    All fixture files are valid and represent real (or realistic synthetic) Trino EXPLAIN output.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Syrupy snapshot tests for fixture corpus</name>
  <files>
    tests/parser/test_fixture_snapshots.py
    pyproject.toml
  </files>
  <read_first>
    src/mcp_trino_optimizer/parser/__init__.py
    src/mcp_trino_optimizer/parser/models.py
    src/mcp_trino_optimizer/parser/parser.py
    tests/fixtures/explain/480/simple_select.json
    tests/fixtures/explain/480/simple_select_analyze.txt
    pyproject.toml
  </read_first>
  <behavior>
    - Test: Every .json fixture file in tests/fixtures/explain/{version}/ parses via parse_estimated_plan without error
    - Test: Every _analyze.txt fixture file parses via parse_executed_plan without error
    - Test: Parsed EstimatedPlan from each JSON fixture matches its syrupy snapshot
    - Test: Parsed ExecutedPlan from each text fixture matches its syrupy snapshot
    - Test: No fixture produces a ParseError
    - Test: Schema drift warnings (if any) are captured in the snapshot
    - Test: Fixture from each version has typed PlanNode tree with at least one node
  </behavior>
  <action>
**Create `tests/parser/test_fixture_snapshots.py`:**

Use `pytest.mark.parametrize` to iterate over all fixture files. For each version directory (480, 455, 429):

```python
import json
from pathlib import Path
import pytest
from syrupy.assertion import SnapshotAssertion
from mcp_trino_optimizer.parser import parse_estimated_plan, parse_executed_plan

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "explain"

def _collect_fixtures():
    """Collect all fixture files as (version, name, path, type) tuples."""
    fixtures = []
    for version_dir in sorted(FIXTURE_DIR.iterdir()):
        if not version_dir.is_dir():
            continue
        version = version_dir.name
        for f in sorted(version_dir.iterdir()):
            if f.suffix == ".json":
                fixtures.append((version, f.stem, f, "estimated"))
            elif f.name.endswith("_analyze.txt"):
                fixtures.append((version, f.stem, f, "executed"))
    return fixtures

@pytest.mark.parametrize("version,name,path,plan_type", _collect_fixtures(),
                         ids=lambda x: f"{x}" if isinstance(x, str) else None)
def test_fixture_parses_without_error(version, name, path, plan_type):
    """Every fixture file must parse without raising."""
    text = path.read_text()
    if plan_type == "estimated":
        plan = parse_estimated_plan(text, trino_version=version)
        assert plan.root is not None
        assert len(list(plan.walk())) >= 1
    else:
        plan = parse_executed_plan(text, trino_version=version)
        assert plan.root is not None
        assert len(list(plan.walk())) >= 1

@pytest.mark.parametrize("version,name,path,plan_type", _collect_fixtures(),
                         ids=lambda x: f"{x}" if isinstance(x, str) else None)
def test_fixture_snapshot(version, name, path, plan_type, snapshot: SnapshotAssertion):
    """Parsed output must match the stored snapshot."""
    text = path.read_text()
    if plan_type == "estimated":
        plan = parse_estimated_plan(text, trino_version=version)
    else:
        plan = parse_executed_plan(text, trino_version=version)
    # Snapshot the model_dump() output for readable diffs
    assert plan.model_dump() == snapshot
```

The parametrize IDs should combine version + name + type for clear test names.

**Update `pyproject.toml`** if syrupy is not already configured:
- Ensure `syrupy>=5.1.0` is in `[project.optional-dependencies]` dev group or `[tool.uv.dev-dependencies]`.
- Add syrupy config if needed: `[tool.syrupy]` section or let it use defaults (JSON serializer is fine for pydantic model_dump output).

**First run with `--snapshot-update`:**
After creating the test file, run `uv run pytest tests/parser/test_fixture_snapshots.py --snapshot-update` to generate initial snapshots. Then run without the flag to verify they match.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && uv run pytest tests/parser/test_fixture_snapshots.py -x -v 2>&1 | tail -30</automated>
  </verify>
  <acceptance_criteria>
    - tests/parser/test_fixture_snapshots.py contains `from syrupy` import
    - tests/parser/test_fixture_snapshots.py contains `parse_estimated_plan` and `parse_executed_plan`
    - tests/parser/test_fixture_snapshots.py contains `snapshot` parameter in at least one test function
    - tests/parser/test_fixture_snapshots.py uses pytest.mark.parametrize over fixture files
    - Snapshot files exist in tests/parser/__snapshots__/ (created by syrupy)
    - `uv run pytest tests/parser/test_fixture_snapshots.py -x` exits 0
    - `uv run pytest tests/parser/ -x` exits 0 (all parser tests including snapshots)
    - pyproject.toml contains `syrupy` in dev dependencies
  </acceptance_criteria>
  <done>
    Every fixture file from all 3 Trino versions parses without error and has a stored syrupy snapshot.
    Snapshot tests are gated in CI. When Trino changes a field, the snapshot diff shows exactly what changed.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Fixture files -> parser | Test fixtures are checked into the repo; trusted but could contain unexpected structures |
| docker-compose Trino -> capture script | Live Trino output captured by the script is trusted (local dev environment) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-03-06 | T (Tampering) | Fixture files in repo | accept | Fixtures are checked into git; any tampering is visible in git diff. Low risk -- they are test data, not production config. |
| T-03-07 | I (Information Disclosure) | Capture script credentials | mitigate | Capture script connects to local Trino with no auth. Script must NOT accept or store Trino credentials in fixture files. Verify no `Authorization` headers appear in captured output. |
</threat_model>

<verification>
1. `uv run pytest tests/parser/test_fixture_snapshots.py -x -v` -- all snapshot tests pass
2. `uv run pytest tests/parser/ -x` -- all parser tests pass (models + parser + normalizer + snapshots)
3. `ls tests/fixtures/explain/*/` shows files for 3 versions
4. `python -c "import json; [json.load(open(f)) for f in __import__('pathlib').Path('tests/fixtures/explain').rglob('*.json')]"` -- all JSON fixtures valid
</verification>

<success_criteria>
- Fixture corpus spans 3 Trino versions with EXPLAIN JSON + EXPLAIN ANALYZE text for each
- Every fixture parses without error through the Phase 3 parser
- Syrupy snapshots gate all parsed output in CI
- Capture script exists for re-running when a new Trino version is added
- No regression in existing tests
</success_criteria>

<output>
After completion, create `.planning/phases/03-plan-parser-normalizer/03-02-SUMMARY.md`
</output>
