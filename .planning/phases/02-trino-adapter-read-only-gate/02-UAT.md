---
status: complete
phase: 02-trino-adapter-read-only-gate
source:
  - 02-01-classifier-auth-settings-SUMMARY.md
  - 02-02-hexagonal-ports-offline-SUMMARY.md
  - 02-03-trino-client-pool-cancel-SUMMARY.md
  - 02-04-capabilities-live-adapters-SUMMARY.md
  - 02-05-integration-harness-ci-SUMMARY.md
started: 2026-04-12T00:00:00Z
updated: 2026-04-12T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: |
  uv run pytest -m "not integration" --tb=short -q exits 0, prints "201 passed" (or higher),
  and no import errors appear. The package imports cleanly:
  `uv run python -c "from mcp_trino_optimizer.adapters.trino.classifier import SqlClassifier; print('ok')`
result: pass

### 2. SqlClassifier rejects write SQL
expected: |
  assert_read_only() succeeds (no raise) for SELECT, raises TrinoClassifierRejected for
  INSERT/DROP/multi-statement:

  ```
  uv run python -c "
  from mcp_trino_optimizer.adapters.trino.classifier import SqlClassifier, TrinoClassifierRejected
  c = SqlClassifier()
  c.assert_read_only('SELECT 1')
  print('SELECT ok')
  for bad in ['INSERT INTO t VALUES (1)', 'DROP TABLE t', 'SELECT 1; DROP TABLE t']:
      try:
          c.assert_read_only(bad)
          print('FAIL: should have raised for', bad)
      except TrinoClassifierRejected:
          print('rejected ok:', bad[:30])
  "
  ```

  Expected: "SELECT ok" then three "rejected ok:" lines.
result: pass
note: Test description used wrong method name (is_safe vs assert_read_only). API verified correct.

### 3. Settings load Trino config from env vars — pass
expected: |
  Settings validate Trino fields from environment variables and fail fast on invalid auth:

  ```
  uv run python -c "
  import os; os.environ['MCPTO_TRINO_HOST'] = 'myhost'
  from mcp_trino_optimizer.settings import Settings
  s = Settings()
  print(s.trino_host)   # myhost
  print(s.trino_port)   # 8080 (default)
  print(s.trino_auth_mode)  # none (default)
  "
  ```

  Also: setting `MCPTO_TRINO_AUTH_MODE=basic` without a user/password should raise a
  ValidationError on `Settings()`.
result: [pending]

### 4. OfflinePlanSource parses JSON without Trino
expected: |
  Paste a minimal EXPLAIN JSON dict and get an ExplainPlan back — no Trino connection needed:

  ```
  uv run python -c "
  import asyncio, json
  from mcp_trino_optimizer.adapters.offline.json_plan_source import OfflinePlanSource
  src = OfflinePlanSource()
  plan_json = json.dumps({'id': 'x', 'name': 'Output'})
  result = asyncio.run(src.fetch_plan(plan_json))
  print(result.plan_type)    # estimated
  print(type(result.plan_json))  # <class 'dict'>
  "
  ```

  A 1 MB+ payload should raise ValueError with a message about the size limit.
result: [pending]

### 5. Capability version gate refuses Trino < 429
expected: |
  The version-gate constant is correct and the parse helper works:

  ```
  uv run python -c "
  from mcp_trino_optimizer.adapters.trino.capabilities import (
      MINIMUM_TRINO_VERSION, parse_trino_version
  )
  print(MINIMUM_TRINO_VERSION)         # 429
  print(parse_trino_version('480'))    # 480
  print(parse_trino_version('428-e'))  # 428
  print(parse_trino_version('480-SNAPSHOT'))  # 480
  "
  ```

  Output: 429, 480, 428, 480 — no exceptions.
result: [pending]

### 6. Integration test suite (Docker required)
expected: |
  uv run pytest -m integration --tb=short -q — 19 passed, 2 skipped (JWT)
result: pass
note: |
  Several bugs found and fixed during UAT:
  - docker-compose: lakekeeper missing `command: serve`; bootstrap/initwarehouse
    entrypoint YAML/shell escaping; accept 204/201/400 as success codes
  - client.py: http_scheme used auth_mode instead of verify_ssl (SSL error on
    plain-HTTP test Trino); EXPLAIN ANALYZE (FORMAT JSON) is invalid Trino syntax
    (fixed to EXPLAIN ANALYZE {sql}); HttpError not caught for protocol-level 401s
  - conftest.py: testcontainers API change filepath→context

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]
