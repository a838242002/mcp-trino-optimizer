---
phase: 04
slug: rule-engine-13-deterministic-rules
status: verified
threats_open: 0
asvs_level: 2
created: 2026-04-13
---

# Phase 4 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Plan JSON → Rule bodies | Trino EXPLAIN JSON parsed into typed PlanNode objects before rules consume them | Plan metadata: operator types, row counts, byte estimates, table names — no user PII |
| Env overrides → RuleThresholds | OS environment variables read by pydantic-settings at startup | Numeric thresholds only; validated by pydantic field constraints |
| EvidenceBundle → RuleEngine | Pre-fetched stats/catalog data passed as a dataclass to each rule | Aggregate statistics: row counts, file counts, snapshot timestamps — no user PII |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-04-01 | Tampering | RuleThresholds env overrides | mitigate | Pydantic `ge=0` on int fields; `ge=0.0, le=1.0` on ratio fields; `ValidationError` on any out-of-range override | closed |
| T-04-02 | Information Disclosure | RuleError.message | accept | Error messages come from exception str(); no user-controlled input reaches rule bodies — EvidenceBundle contains typed data only | closed |
| T-04-03 | Denial of Service | _parse_table_ref regex | mitigate | `re.match()` with anchored patterns; 1000-char cap on table string (`_TABLE_STR_MAX_LEN = 1000`) applied before any regex | closed |
| T-04-04 | Elevation of Privilege | rules package imports | mitigate | Zero `from mcp_trino_optimizer.adapters` imports in rules/; docstring in base.py enforces this; verified by mypy + grep pre-commit check | closed |
| T-04-05 | Repudiation | engine.run() audit trail | accept | Low risk in Phase 4 (no MCP wiring yet); Phase 8 will add structured logging of rule findings with request_id | closed |
| T-04-06 | Denial of Service | R3 sqlglot.parse_one() | mitigate | Wrapped in `try/except (sqlglot.errors.ParseError, Exception)`; falls back to regex detection on parse error; never crashes on unparseable predicate | closed |
| T-04-07 | Information Disclosure | R1/R2 evidence dict | accept | Evidence values are plan-derived strings (operator types, table names) — no user PII; safe to include in findings | closed |
| T-04-08 | Tampering | R2 "constraint on [" string check | accept | Trino-format constraint strings come from trusted Trino plan JSON, not user input; no injection risk via descriptor field | closed |
| T-04-09 | Spoofing | R4 dynamicFilterAssignments string match | accept | String matching on plan details is deterministic; malformed details worst case = false negative (rule doesn't fire), not a false positive | closed |
| T-04-10 | Denial of Service | R7 statistics.median() on large node list | accept | plan.walk() on largest realistic Trino plan is <10k nodes; stdlib statistics.median() is O(n log n); no DoS risk at this scale | closed |
| T-04-11 | Tampering | D11 NaN/div-zero | mitigate | `safe_float()` guards all estimate reads; `if estimated is None: continue`; `if estimated <= 0: continue`; `if actual is None or actual == 0: continue` before division | closed |
| T-04-12 | Information Disclosure | R5/R8 evidence dict with byte estimates | accept | Byte estimates are CBO internals from the Trino plan — no user PII or secrets | closed |
| T-04-13 | Denial of Service | R6 join-child indexing | mitigate | `if len(node.children) < 2: continue` guard before accessing `children[1]`; single-child joins skip safely | closed |
| T-04-14 | Denial of Service | I6 datetime.fromisoformat() on large snapshots list | accept | `max_metadata_rows=10_000` caps the list size; parsing 10k timestamps is <1ms | closed |
| T-04-15 | Denial of Service | I8 regex on details list | mitigate | `_DETAIL_MAX_LEN = 1000`; detail strings capped before regex; explicit character classes `\d{4}`, `\d{2}` — no unbounded quantifiers; wrapped in `try/except (ValueError, AttributeError)` | closed |
| T-04-16 | Information Disclosure | I3 evidence dict with file path counts | accept | File counts and record counts are aggregate statistics — no PII; file paths NOT included in evidence (only counts/ratios) | closed |
| T-04-17 | Tampering | I1/I3 content field type checking | mitigate | `f.get("content") in (1, 2)` and `f.get("content") == 0` handle None/wrong type safely via Python semantics (no KeyError, no TypeError) | closed |
| T-04-18 | Spoofing | I6 snapshot_count threshold check | accept | Count from catalog metadata is trusted server response; no user can inject arbitrary snapshot counts | closed |
| T-04-19 | Elevation of Privilege | rules/__init__.py auto-import | mitigate | All 13 rule modules imported via explicit named `import` statements; no `importlib`, `__import__()`, or glob-based discovery | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-04-01 | T-04-02 | RuleError.message contains only exception strings; no user-controlled input reaches rule bodies (EvidenceBundle is typed, plan-derived data) | gsd-security-auditor | 2026-04-13 |
| AR-04-02 | T-04-05 | No MCP wiring in Phase 4; full audit trail with request_id deferred to Phase 8 tool wiring | gsd-security-auditor | 2026-04-13 |
| AR-04-03 | T-04-07 | Evidence dict values are plan-derived (operator types, table names from Trino EXPLAIN JSON) — no user PII | gsd-security-auditor | 2026-04-13 |
| AR-04-04 | T-04-08 | Constraint strings originate from trusted Trino server response; user cannot inject into descriptor fields | gsd-security-auditor | 2026-04-13 |
| AR-04-05 | T-04-09 | R4 string matching on plan details is deterministic; worst-case malformed input is a false negative (rule doesn't fire), not a false positive | gsd-security-auditor | 2026-04-13 |
| AR-04-06 | T-04-10 | R7 uses statistics.median() on plan nodes; realistic Trino plans have <10k nodes; O(n log n) is not a DoS risk at this scale | gsd-security-auditor | 2026-04-13 |
| AR-04-07 | T-04-12 | Byte estimates in R5/R8 evidence are CBO internals from Trino EXPLAIN — no PII or secrets | gsd-security-auditor | 2026-04-13 |
| AR-04-08 | T-04-14 | max_metadata_rows=10_000 caps snapshot list; parsing 10k ISO timestamps is sub-millisecond | gsd-security-auditor | 2026-04-13 |
| AR-04-09 | T-04-16 | I3 evidence contains only file counts and delete ratios — no file paths, no PII | gsd-security-auditor | 2026-04-13 |
| AR-04-10 | T-04-18 | Snapshot count originates from Lakekeeper/Iceberg catalog metadata — trusted server response | gsd-security-auditor | 2026-04-13 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-04-13 | 19 | 19 | 0 | gsd-security-auditor (Phase 4 initial audit) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter
