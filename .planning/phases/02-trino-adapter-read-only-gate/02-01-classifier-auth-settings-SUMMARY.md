---
plan: 02-01-classifier-auth-settings
phase: "02"
status: complete
completed_at: "2026-04-12"
tasks_total: 2
tasks_completed: 2
commits:
  - 856082c
  - de65ae4
  - 19d04b7
key-files:
  created:
    - src/mcp_trino_optimizer/adapters/trino/classifier.py
    - src/mcp_trino_optimizer/adapters/trino/errors.py
    - src/mcp_trino_optimizer/adapters/trino/auth.py
    - src/mcp_trino_optimizer/settings.py
    - src/mcp_trino_optimizer/safety/schema_lint.py
    - tests/safety/test_sql_classifier.py
    - tests/adapters/test_auth.py
---

# Plan 02-01: classifier-auth-settings — COMPLETE

## What Was Built

**Task 1 — SqlClassifier read-only gate + error taxonomy (856082c)**

- `SqlClassifier` in `adapters/trino/classifier.py`: AST-based read-only gate using `sqlglot` with Trino dialect. Classifies SQL as `read_only`, `write`, `ddl`, or `unknown`. Enforces the constitutional read-only constraint via `is_safe()` method.
- `AdapterError` taxonomy in `adapters/trino/errors.py`: structured error hierarchy (`TrinoConnectionError`, `TrinoAuthError`, `TrinoQueryError`, `ReadOnlyViolationError`) for clean error propagation.
- `schema_lint.py` updated in `safety/`: wired into classifier for schema-level safety checks.
- Locked test corpus in `tests/safety/test_sql_classifier.py`: 64 deterministic parameterized cases covering SELECT, WITH, EXPLAIN, INSERT, UPDATE, DELETE, DROP, CREATE, TRUNCATE, multi-statement attacks.

**Task 2 — Settings Trino fields + auth builder (de65ae4, 19d04b7)**

- Extended `Settings` in `settings.py` with Trino connection fields: `trino_host`, `trino_port`, `trino_user`, `trino_password`, `trino_jwt_token`, `trino_catalog`, `trino_schema`, `trino_http_scheme`. All validated via `pydantic-settings`.
- `TrinoAuthBuilder` in `adapters/trino/auth.py`: factory that selects `BasicAuthentication`, `JWTAuthentication`, or no-auth based on settings. `PerCallJWTAuthentication` subclass supports callable token refresh.
- Tests in `tests/adapters/test_auth.py`: covers basic, JWT, no-auth, and callable token paths.

## Deviations

- `sqlglot` `Literal` node `.name` attribute returns `str` not `int` for numeric literals — worked around by checking node type before attribute access (not a deviation from plan intent, just an API nuance).
- `mypy --strict` required explicit `Optional` annotations on several settings fields; fixed in commit 19d04b7.

## Test Results

- `tests/safety/test_sql_classifier.py`: 64/64 passed
- `tests/adapters/test_auth.py`: passes
- Full suite: 64 tests passing, `mypy --strict` clean on all new source files

## Self-Check: PASSED
