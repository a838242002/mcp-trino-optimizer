# Phase 2: Trino Adapter & Read-Only Gate - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-12
**Phase:** 02-trino-adapter-read-only-gate
**Areas discussed:** Cancellation protocol, JWT auth source, Integration test harness, Offline mode ingress

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Cancellation protocol & query-id capture | Main research unknown; adapter API shape | ✓ |
| JWT auth source & refresh strategy | Env/file/callable; per-request semantics | ✓ |
| Integration test harness choice | testcontainers vs fake vs hybrid | ✓ |
| Offline mode ingress shape | Raw text vs file path; classifier scope | ✓ |

**User's choice:** All four areas selected for discussion.

---

## Cancellation protocol & query-id capture

### Q1: Adapter call shape for reliable cancellation

| Option | Description | Selected |
|--------|-------------|----------|
| QueryHandle pattern | Thread-safe cell populated by to_thread wrapper; `.cancel()` method; clean API | ✓ |
| AsyncExitStack + contextvar | Contextvar set by to_thread wrapper; subtle under thread-pool execution | |
| Raw httpx async path | Bypass trino-python-client; reimplements auth/retry/cursor | |

**User's choice:** QueryHandle pattern
**Notes:** Matches how the sync client exposes query_id. Testable. Recommended option accepted.

### Q2: Timeout UX

| Option | Description | Selected |
|--------|-------------|----------|
| Partial results + structured timeout note | Per K-Decision #13; TimeoutResult dataclass | ✓ |
| Fail-fast with structured error | Contradicts K-Decision #13 | |
| Per-tool decision | Pushes complexity to every tool handler | |

**User's choice:** Partial results + structured timeout note
**Notes:** Aligns with locked project decision #13.

### Q3: Timeout budget source

| Option | Description | Selected |
|--------|-------------|----------|
| Settings default + per-call override | `MCPTO_TRINO_QUERY_TIMEOUT_SEC` + optional kwarg | ✓ |
| Settings default only | Global, inflexible | |
| Per-call only | Explicit but noisy | |

**User's choice:** Settings default + per-call override
**Notes:** Recommended option accepted.

### Q4: Cancel acknowledgment

| Option | Description | Selected |
|--------|-------------|----------|
| Await confirmation with bounded retry | Poll `/v1/query/{id}/info` with exponential backoff cap ~4s | ✓ |
| Fire-and-forget | Success criterion requires verification; rejected | |
| Await via system.runtime.queries | Adds second SQL call; overkill | |

**User's choice:** Await confirmation with bounded retry
**Notes:** Matches success criterion 3 ("no query remains in system.runtime.queries after the cancel").

---

## JWT auth source & refresh strategy

### Q1: JWT source on each Trino call

| Option | Description | Selected |
|--------|-------------|----------|
| Env var, per-call re-read | Zero refresh machinery; sidecar refreshers work | ✓ |
| File path with mtime watch | More moving parts | |
| Callable hook | Plugin discovery complexity; deferred to v2+ | |

**User's choice:** Env var per-call re-read + ALSO provide basic auth by username + password
**Notes:** User added a requirement — Basic auth (username + password) must also be supported.
Basic auth is already listed in TRN-03, so not scope creep. Led to Q2 locking the auth-mode shape.

### Q2: Basic auth sourcing + mode selection

| Option | Description | Selected |
|--------|-------------|----------|
| Env vars + auth-mode setting | `MCPTO_TRINO_AUTH_MODE: Literal['none','basic','jwt']` with fail-fast validator | ✓ |
| Auto-detect from whatever is set | Harder to debug stale credentials | |
| Env vars + Typer CLI flags | More surface area | |

**User's choice:** Env vars + auth-mode setting
**Notes:** Fail-fast on missing required fields for the selected mode. No fallback chains.

### Q3: 401 retry policy

| Option | Description | Selected |
|--------|-------------|----------|
| Retry once with fresh re-read + structured log | Minimum useful behavior for expiring JWTs | ✓ |
| Fail fast on first 401 | Simpler but less resilient | |
| Configurable retry count | Overkill; hides real problems | |

**User's choice:** Retry once with fresh re-read
**Notes:** `trino_auth_retry` structured log event with `{request_id, query_id, attempt, auth_mode}`.

---

## Integration test harness choice

### Q1: Test stack shape

| Option | Description | Selected |
|--------|-------------|----------|
| testcontainers Trino + minimal Iceberg | Real Trino 480 + Lakekeeper + MinIO + Postgres; closest to prod | ✓ |
| Hybrid: recording fake + real behind flag | Fake drift risk | |
| Standalone trino, no Iceberg in Phase 2 | Defers Iceberg tests to Phase 9 | |

**User's choice:** testcontainers Trino + minimal Iceberg
**Notes:** Ships `.testing/docker-compose.yml` that Phase 9 promotes/refines into production shape.

### Q2: CI wiring

| Option | Description | Selected |
|--------|-------------|----------|
| Enable on ubuntu-latest, push-to-main only | Flip `if: false` stub to push-to-main trigger; skip PRs | ✓ |
| Enable on every PR, ubuntu-latest | ~5 min PR latency penalty | |
| Manual dispatch only | Too permissive for load-bearing safety code | |

**User's choice:** Enable on ubuntu-latest, push-to-main only
**Notes:** Developers run `pytest -m integration` locally when modifying adapter code.

---

## Offline mode ingress shape

### Q1: OfflinePlanSource input shape

| Option | Description | Selected |
|--------|-------------|----------|
| Raw text argument, bounded | `fetch(plan_json: str)` with schema-lint maxLength; zero filesystem access | ✓ |
| Raw text OR file path | Opens path traversal surface; adds sandbox complexity | |
| Raw text + optional generating SQL | Classifier runs on SQL if supplied; more code paths | |

**User's choice:** Raw text argument, bounded
**Notes:** `MAX_PLAN_JSON_LEN = 1_000_000` in `safety/schema_lint.py`. Cleanest sandboxing.

### Q2: Classifier scope for offline path

| Option | Description | Selected |
|--------|-------------|----------|
| Classifier is adapter-scoped, not port-scoped | Live `TrinoClient` only calls `assert_read_only`; offline exempt | ✓ |
| Classifier runs on every PlanSource | Dead code path in offline mode | |
| Architectural test covers any `sql:` param in adapters | Broader coverage but more work upfront | |

**User's choice:** Classifier is adapter-scoped, not port-scoped
**Notes:** TRN-05 architectural test targets live `TrinoClient` only. OfflinePlanSource has no SQL to classify.

---

## Final check

### Q: Write CONTEXT.md or discuss more gray areas?

| Option | Description | Selected |
|--------|-------------|----------|
| Write CONTEXT.md | Four areas cover the load-bearing gray areas; planner handles remainder | ✓ |
| Discuss SqlClassifier allowlist shape | Planner can handle from TRN-04 | |
| Discuss capability probe granularity | Planner can handle from research | |

**User's choice:** Write CONTEXT.md
**Notes:** Remaining items (classifier allowlist details, capability probe fields, error taxonomy) deferred to planner's discretion based on STACK.md, PITFALLS.md, SUMMARY research.
