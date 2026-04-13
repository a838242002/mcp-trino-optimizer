---
phase: 5
slug: recommendation-engine
status: verified
threats_open: 0
asvs_level: 1
created: 2026-04-14
---

# Phase 5 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| RuleFinding.evidence -> impact extractor | Evidence dicts originate from rule logic which processes user-origin SQL plans | Numeric values (could be NaN, negative, extremely large) |
| RuleFinding.evidence -> template rendering | Evidence values originate from user SQL via plan parsing | String/numeric values into narrative text |
| RuleFinding.message -> recommendation body | message field may contain user-origin text | User-controlled strings (NEVER used in templates) |
| Session property names -> SET SESSION output | Property names must come from embedded data module | Hardcoded identifiers only |
| RuleFinding.evidence -> health aggregation | Iceberg rule evidence dicts may contain user-origin table names | Structured field values |
| ExecutedPlan nodes -> bottleneck ranking | Plan node data originates from Trino EXPLAIN ANALYZE | Typed numeric fields (cpu_time_ms, wall_time_ms) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-05-01 | Tampering | impact.py extractor | mitigate | `safe_float()` guards in all 14 extractors; `get_impact()` clamps result to [0.0, 1.0]; exception handler returns DEFAULT_IMPACT | closed |
| T-05-02 | Denial of Service | scoring.py | accept | Bounded arithmetic: max score = 4 * 1.0 * 1.0 = 4.0; no amplification vector | closed |
| T-05-03 | Tampering | templates.py | mitigate | Identifier-only regex whitelist (`^[a-zA-Z0-9._\-/]+$`); non-matching strings produce `[redacted]`; `test_templates.py` injects SQL injection across all 14 rules and asserts absence | closed |
| T-05-04 | Information Disclosure | session_properties.py | mitigate | `SESSION_PROPERTIES` dict is hardcoded; `build_set_session_statements` only looks up from this dict, never fabricates names from user input | closed |
| T-05-05 | Tampering | conflicts.py | accept | All rejected findings preserved as `ConsideredButRejected` with explicit reasons; no findings silently dropped | closed |
| T-05-06 | Elevation of Privilege | engine.py | mitigate | `isinstance(r, RuleFinding)` filter at pipeline entry; RuleError/RuleSkipped excluded; no dynamic code execution; tested in `test_engine.py` | closed |
| T-05-07 | Tampering | health.py | mitigate | Zero `.message` field references in narrative; templates use only `{table_name}`, `{health_score}`, `{details}` with hardcoded detail strings | closed |
| T-05-08 | Denial of Service | bottleneck.py | accept | Single O(n) walk; `recommender_top_n_bottleneck` constrained to max 50 in Settings; no amplification vector | closed |
| T-05-09 | Tampering | bottleneck.py narrative | mitigate | Narrative uses only PlanNode typed fields (`node.id`, `node.operator_type`, computed `cpu_pct`, `cpu_time_ms`); no user-origin strings interpolated | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-05-01 | T-05-02 | Priority score is bounded arithmetic (max 4.0); no amplification vector exists | gsd-security-auditor | 2026-04-14 |
| AR-05-02 | T-05-05 | Conflict resolution is by design deterministic with full audit trail via ConsideredButRejected | gsd-security-auditor | 2026-04-14 |
| AR-05-03 | T-05-08 | Bottleneck ranking is O(n) single-pass with bounded output (max 50); no resource exhaustion path | gsd-security-auditor | 2026-04-14 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-04-14 | 9 | 9 | 0 | gsd-security-auditor |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-04-14
