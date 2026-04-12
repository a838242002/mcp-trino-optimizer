---
phase: "05"
plan: "02"
subsystem: recommender
tags: [conflicts, templates, session-properties, engine, prompt-injection, deterministic]
dependency_graph:
  requires: [recommender.models, recommender.scoring, recommender.impact, rules.findings, adapters.trino.capabilities]
  provides: [recommender.conflicts.resolve_conflicts, recommender.templates.render_recommendation, recommender.session_properties.build_set_session_statements, recommender.engine.RecommendationEngine]
  affects: [recommender.__init__]
tech_stack:
  added: []
  patterns: [identifier-only-sanitization, conflict-pair-declaration, session-property-version-gating]
key_files:
  created:
    - src/mcp_trino_optimizer/recommender/conflicts.py
    - src/mcp_trino_optimizer/recommender/templates.py
    - src/mcp_trino_optimizer/recommender/session_properties.py
    - src/mcp_trino_optimizer/recommender/engine.py
    - tests/recommender/test_conflicts.py
    - tests/recommender/test_templates.py
    - tests/recommender/test_session_properties.py
    - tests/recommender/test_engine.py
  modified:
    - src/mcp_trino_optimizer/recommender/__init__.py
decisions:
  - "Identifier-only sanitization for template evidence values -- strings with spaces/special chars produce [redacted] instead of partial filtering"
  - "Conflict resolution uses confidence-first, severity-second, rule_id-third tiebreaking"
  - "Session properties use Protocol-based duck typing for capability_matrix parameter"
metrics:
  duration: "8m 59s"
  completed: "2026-04-12T20:10:28Z"
  tasks_completed: 2
  tasks_total: 2
  tests_added: 67
  files_created: 8
  files_modified: 1
---

# Phase 5 Plan 2: Conflicts, Templates, Session Properties, and Engine Summary

Conflict resolution for 3 declared pairs, identifier-sanitized narrative templates for all 14 rules, Trino session property version gating, and RecommendationEngine orchestrating the full pipeline from findings to sorted RecommendationReport.

## Task Results

| Task | Name | Commit | Tests | Status |
|------|------|--------|-------|--------|
| 1 | Conflict resolution + session property data module | `6ccf9d8` | 26 | PASS |
| 2 | Narrative templates + RecommendationEngine + prompt-injection test | `d7ac93d` | 41 | PASS |

## Implementation Details

### Conflict Resolution (conflicts.py)
- `CONFLICT_PAIRS`: bidirectional R1/D11, R2/R9, R5/R8
- `ScoredFinding`: NamedTuple pairing RuleFinding with priority_score
- `resolve_conflicts`: groups by operator overlap (or same-analysis sentinel for Iceberg rules with empty operator_ids), then picks winner by confidence > severity > alphabetical rule_id
- Losers preserved as `ConsideredButRejected` with explanation string

### Session Properties (session_properties.py)
- `SessionProperty`: pydantic model with name, description, default, valid_range, min_trino_version, category, set_session_template
- 5 curated properties: join_distribution_type, join_max_broadcast_table_size, enable_dynamic_filtering, task_concurrency, join_reordering_strategy
- `RULE_SESSION_PROPERTIES`: maps R4, R5, R6, R7, R8 to their relevant properties
- `build_set_session_statements`: version-gated builder returning SET SESSION or advisory strings
- Protocol-based duck typing for capability_matrix (accepts CapabilityMatrix or any object with trino_version_major)

### Narrative Templates (templates.py)
- 14 rule templates with reasoning, expected_impact, validation_steps, risk_level
- Identifier-only sanitization: evidence string values must match `^[a-zA-Z0-9._\-/]+$` or produce `[redacted]`
- `defaultdict(lambda: "N/A")` for missing evidence keys
- Prompt-injection defense verified: `'; DROP TABLE users; --` produces `[redacted]` in all fields

### RecommendationEngine (engine.py)
- Pipeline: filter findings -> compute impact -> compute priority -> assign tier -> resolve conflicts -> render templates -> build session statements -> sort descending
- Filters RuleError/RuleSkipped from EngineResult list (T-05-06)
- Session property statements are None when rule has no properties, advisory when offline
- Configurable tier thresholds from Settings or defaults

## Decisions Made

1. **Identifier-only sanitization**: Rather than stripping individual dangerous characters (which leaves "DROP TABLE" intact), we reject any string containing spaces or special characters. This is stricter but eliminates all injection vectors. Legitimate evidence values like table names and operator IDs are always identifier-shaped.
2. **Protocol-based duck typing**: `build_set_session_statements` accepts any object with `trino_version_major` attribute, not just `CapabilityMatrix`. This simplifies testing with dataclass stubs.
3. **Alphabetical rule_id tiebreaker**: When confidence and severity both tie, lower rule_id wins. This ensures deterministic output.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Template sanitization approach changed from character stripping to identifier whitelist**
- **Found during:** Task 2
- **Issue:** Plan suggested safe_evidence filter keeping str/int/float and using format_map. Initial character-stripping approach left "DROP TABLE" intact because those are normal alphanumeric characters.
- **Fix:** Switched to identifier-only whitelist regex; non-matching strings produce "[redacted]"
- **Files modified:** src/mcp_trino_optimizer/recommender/templates.py
- **Commit:** d7ac93d

## Verification

```
tests/recommender/test_conflicts.py: 10 passed
tests/recommender/test_session_properties.py: 16 passed
tests/recommender/test_templates.py: 22 passed
tests/recommender/test_engine.py: 19 passed
Total recommender suite: 146 passed (including 79 from Plan 01)
Lint: All checks passed (ruff)
```

## Known Stubs

None -- all modules are fully implemented with real logic and complete test coverage.

## Threat Flags

None -- no new security surface introduced beyond what the plan's threat model covers (T-05-03 through T-05-06 all mitigated and tested).

## Self-Check: PASSED

- All 8 created files verified present on disk
- Both commits (6ccf9d8, d7ac93d) verified in git log
- 146 recommender tests passing, lint clean
