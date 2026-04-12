---
phase: "02"
slug: trino-adapter-read-only-gate
status: secured
threats_open: 0
threats_closed: 17
asvs_level: 1
created: "2026-04-12"
audited: "2026-04-12"
---

# Phase 02 — Security: trino-adapter-read-only-gate

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| User SQL → SqlClassifier | Untrusted SQL string from MCP tool input | Raw SQL (untrusted) |
| Settings env vars → Auth builder | Secrets (JWT, password) flow from env to HTTP headers | SecretStr credentials |
| User pasted JSON → OfflinePlanSource | Untrusted JSON text from tool input | Raw bytes (size-capped) |
| MCP tool input → TrinoClient | Untrusted SQL crosses into Trino adapter | Classified SQL only |
| TrinoClient → Trino cluster | Classified SQL sent over HTTP REST | Read-only SQL |
| Worker thread → async event loop | query_id flows back via QueryIdCell | Internal identifier |
| Trino cluster → CapabilityMatrix | Version string from system table | Semi-trusted metadata |
| User table name → fetch_iceberg_metadata | Table identifier components used in SQL | Allowlist-validated identifier |
| Docker compose stack → test code | Integration tests trust the compose stack | Test-only credentials |
| Test DDL helper → Trino | Bypasses classifier for seeding | DDL (test-only) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-02-01 | Tampering | classifier.py | mitigate | AST-based allowlist via `sqlglot.parse`; multi-statement rejected; non-allowlist Command nodes rejected at `_ALLOWED_NODE_TYPES` | closed |
| T-02-02 | Tampering | classifier.py | mitigate | Comment-wrapped DDL safe: sqlglot strips comments before AST; unicode tricks neutralized during tokenization | closed |
| T-02-03 | Info Disclosure | auth.py | mitigate | JWT stored as `SecretStr`; structlog denylist covers authorization header; `PerCallJWTAuthentication` reads env at call time, never stores | closed |
| T-02-04 | Elevation | settings.py | mitigate | `_require_trino_auth_fields` model_validator fails fast on invalid auth config before any network call | closed |
| T-02-05 | DoS | json_plan_source.py | mitigate | `MAX_PLAN_BYTES = 1_000_000`; `_validate_size` called before `orjson.loads()` in all three fetch methods | closed |
| T-02-06 | Tampering | OfflinePlanSource | accept | Offline JSON parsed into dict only — no SQL execution, no network calls. Phase 8 tool layer wraps with `wrap_untrusted()` when echoing back. | closed |
| T-02-07 | Tampering | client.py | mitigate | `assert_read_only(sql)` is first line of every sql-taking public method (6 methods verified) | closed |
| T-02-08 | DoS | pool.py | mitigate | `ThreadPoolExecutor(max_workers=4)` + `asyncio.Semaphore(4)`; `TrinoPoolBusyError` raised on overflow; semaphore leak fixed with `asyncio.shield()` | closed |
| T-02-09 | DoS | handle.py / client.py | mitigate | Confirmed cancel via `DELETE /v1/query/{qid}` + polling; wall-clock deadline enforced; `TimeoutResult` returned on expiry | closed |
| T-02-10 | Info Disclosure | client.py | mitigate | Raw SQL never logged; only `SHA-256` hex digest recorded as `statement_hash` | closed |
| T-02-11 | Repudiation | client.py | mitigate | Every query logged with `request_id`, `query_id`, `statement_hash`, `duration_ms`, `auth_mode` | closed |
| T-02-12 | Spoofing | capabilities.py | accept | Version string from `system.runtime.nodes` trusted-within-network; rogue cluster is inside user's own deployment | closed |
| T-02-13 | Tampering | live_catalog_source.py | mitigate | `_ALLOWED_SUFFIXES` frozenset + allowlist enforced at `TrinoClient` level; catalog names double-quoted in SQL; all SQL through `SqlClassifier` | closed |
| T-02-14 | Elevation | capabilities.py | mitigate | `MINIMUM_TRINO_VERSION = 429`; `TrinoVersionUnsupported` raised for clusters below threshold | closed |
| T-02-15 | Elevation | tests/integration/fixtures.py | mitigate | DDL bypass lives in `tests/` only; uses `trino.dbapi` directly; `TrinoClient` not imported | closed |
| T-02-16 | Info Disclosure | .env.example | mitigate | All secret fields commented out (including `MCPTO_HTTP_BEARER_TOKEN` — fixed 2026-04-12); no real tokens committed | closed |
| T-02-17 | DoS | docker-compose | accept | Compose binds to `127.0.0.1` only; local-dev/CI only, not production | closed |

---

## Accepted Risks

| Threat ID | Rationale | Owner |
|-----------|-----------|-------|
| T-02-06 | Offline JSON is never executed as SQL. Phase 8 adds `wrap_untrusted()` at the tool layer. | Phase 8 |
| T-02-12 | Rogue Trino version string is inside the user's own deployment boundary — not an external threat. | infra |
| T-02-17 | Compose stack only reachable at `127.0.0.1`; not exposed in production. | dev/CI |

---

## Audit Trail

### Security Audit 2026-04-12

| Metric | Count |
|--------|-------|
| Threats in register | 17 |
| Verified closed | 13 |
| Accepted (no verification needed) | 3 |
| Fixed during audit | 1 (T-02-16: `.env.example` bearer token commented out) |
| Open after audit | 0 |

Audited by: gsd-security-auditor (automated) + orchestrator fix pass.
