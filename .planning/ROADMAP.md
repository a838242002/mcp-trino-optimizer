# Roadmap: mcp-trino-optimizer

**Created:** 2026-04-11
**Granularity:** standard
**Core Value:** Turn opaque Trino query performance problems into actionable, evidence-backed optimization reports that a user (or an LLM agent) can trust and apply safely.

**Source inputs:**
- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md` (102 v1 requirements)
- `.planning/research/SUMMARY.md` §7 (reconciled 9-phase proposal)
- `.planning/research/ARCHITECTURE.md` §13 (topological build order)
- `.planning/research/PITFALLS.md` (pitfall-to-phase mapping)

**Phase derivation rationale:**
Requirements cluster naturally into 9 functional areas that map one-to-one onto the research SUMMARY §7 proposal: platform safety → Trino adapter → plan parser → rule engine → recommendation engine → rewrite engine → comparison engine → MCP surface → integration stack. ARCHITECTURE.md collapses this to 5 (foundation → adapters → rules → higher engines → MCP), but PITFALLS's finer slicing gives each phase a single sharp demonstrable deliverable and matches the categories already present in REQUIREMENTS.md. At standard granularity (5-8 preferred), 9 phases is at the upper edge but each phase has a distinct user-observable output and a distinct failure mode, so consolidation would conflate orthogonal concerns.

**Coverage:** 102 / 102 v1 requirements mapped (Unmapped: 0)

---

## Phases

- [x] **Phase 1: Skeleton & Safety Foundation** - Server boots on stdio and Streamable HTTP, answers `initialize`, exposes `mcp_selftest`, ships via uv/uvx/pip/Docker; all critical safety foundations (stdio discipline, redaction, untrusted envelope, strict schemas) in place
- [x] **Phase 2: Trino Adapter & Read-Only Gate** - Live Trino client with AST-based read-only classifier, cancel/timeout propagation, async wrapper, version + capability probes, offline plan source; no plan parsing yet (completed 2026-04-12)
- [x] **Phase 3: Plan Parser & Normalizer** - Typed `EstimatedPlan` / `ExecutedPlan` from `EXPLAIN (FORMAT JSON)` and `EXPLAIN ANALYZE`, tolerant-tree with `raw` bags, multi-version Trino fixture corpus parses clean (completed 2026-04-12)
- [ ] **Phase 4: Rule Engine & 13 Deterministic Rules** - Plugin registry, prefetch + isolated-failure engine, all table-stakes rules (R1-R9 + I1/I3/I6/I8 + D11) producing `RuleFinding` with evidence
- [ ] **Phase 5: Recommendation Engine** - Scored, prioritized `Recommendation` objects with conflict resolution, audited rule-ID-keyed templates, session-property grounding, Iceberg table health summary, operator bottleneck ranking
- [ ] **Phase 6: Safe SQL Rewrite Engine** - sqlglot-AST whitelist rewrites (projection pruning, function-wrapped predicate unwrap, partition-transform-aligned rewrite) with preconditions, diff, and round-trip validation
- [ ] **Phase 7: Comparison Engine** - CPU-time-primary before/after `ComparisonReport` with N=5 paired alternation, snapshot pinning, correctness-delta check, HIGH/MEDIUM/LOW confidence classifier
- [ ] **Phase 8: MCP Surface (Tools, Resources, Prompts)** - All 8 tools, 4 resources, 3 prompts wired onto the shared FastMCP app via thin service-layer handlers; strict JSON Schemas everywhere; static tool descriptions
- [ ] **Phase 9: Integration Stack & CI** - Productized docker-compose (Trino 480 + Lakekeeper + Postgres + MinIO), testcontainers integration tests, prompt-injection adversarial corpus, install matrix CI on {3.11, 3.12, 3.13} × {mac, linux, win}

## Phase Details

### Phase 1: Skeleton & Safety Foundation
**Goal**: A pip/uvx/Docker-installable MCP server starts on stdio and Streamable HTTP, answers `initialize`, exposes `mcp_selftest`, and every critical day-one safety pitfall (stdio stdout discipline, redaction, untrusted-content envelope convention, strict JSON schema posture) is enforced before a single Trino-touching line of code lands.
**Depends on**: Nothing (first phase)
**Requirements**: PLAT-01, PLAT-02, PLAT-03, PLAT-04, PLAT-05, PLAT-06, PLAT-07, PLAT-08, PLAT-09, PLAT-10, PLAT-11, PLAT-12, PLAT-13
**Success Criteria** (what must be TRUE):
  1. A user on macOS, Linux, or Windows can run `uv tool install mcp-trino-optimizer`, `uvx mcp-trino-optimizer`, or `pip install mcp-trino-optimizer`, add the documented `mcpServers` block to Claude Code, and the `mcp_selftest` tool returns server version, transport, and a round-trip echo payload — no Trino required.
  2. A CI test sends a JSON-RPC `initialize` frame over stdio and asserts that every byte written to stdout is part of a valid JSON-RPC frame (no stray `print()`, logging, or `warnings` output ever reaches stdout); all logs appear on stderr only as structured JSON with `request_id`, `tool_name`, `git_sha`, `package_version`, and ISO8601 UTC timestamp. (PLAT-05, PLAT-06 — §6.1 safety items 1 and 3)
  3. A unit test that attempts to log a dict containing `Authorization`, `X-Trino-Extra-Credentials`, or `credential.*` asserts the value is hard-redacted to `[REDACTED]` before the log line is emitted. (PLAT-07 — §6.1 safety item 3)
  4. Every MCP tool registered at startup has a JSON Schema with `additionalProperties: false`, bounded string `maxLength` (SQL ≤ 100KB), identifier `pattern`, and bounded arrays; a schema-lint test fails if any tool is missing any of these. Every tool response that embeds a user-origin string wraps it in an `{ "source": "untrusted", "content": "..." }` envelope, enforced by a shared `wrap_untrusted()` helper that tool tests exercise from day one. (PLAT-10, PLAT-11 — §6.1 safety items 2 and 4)
  5. The CI install-matrix confirms successful install and `initialize` round-trip on Python 3.11, 3.12, and 3.13 across macOS, Linux, and Windows runners; the README contains copy-pasteable Claude Code `mcpServers` JSON for stdio, Streamable HTTP, and Docker install paths, and a CLAUDE.md defining coding rules, DoD, validation workflow, and safe-execution boundaries. (PLAT-12, PLAT-13)
**Plans**: 6 plans across 4 waves
  - [x] 01-01-test-harness-scaffold-PLAN.md — Wave 0: pyproject.toml, package shells, Wave 0 stub tests
  - [x] 01-02-safety-primitives-PLAN.md — Wave 1: envelope + stdout_guard + schema_lint
  - [x] 01-03-settings-logging-runtime-PLAN.md — Wave 1: Settings + logging_setup + _runtime + _context
  - [x] 01-04-app-tools-transports-cli-PLAN.md — Wave 2: app + selftest tool + transports + CLI
  - [x] 01-05-docker-docs-PLAN.md — Wave 3: Dockerfile + README + CONTRIBUTING.md + .env.example + LICENSE
  - [x] 01-06-ci-precommit-PLAN.md — Wave 3: GitHub Actions CI 9-cell matrix + pre-commit hooks
**UI hint**: no
**Needs research**: no

### Phase 2: Trino Adapter & Read-Only Gate
**Goal**: Every code path that reaches Trino is forced through a single `sqlglot`-AST-based `SqlClassifier` gate at the adapter boundary, runs inside an `asyncio.to_thread` bounded pool, and can be cancelled with a guaranteed `DELETE /v1/query/{queryId}` on the cluster. The live `PlanSource`/`StatsSource`/`CatalogSource` adapters plus the `OfflinePlanSource` both exist and share the ports defined in ARCHITECTURE.md — but no parsing, rules, or tool wiring is done yet.
**Depends on**: Phase 1
**Requirements**: TRN-01, TRN-02, TRN-03, TRN-04, TRN-05, TRN-06, TRN-07, TRN-08, TRN-09, TRN-10, TRN-11, TRN-12, TRN-13, TRN-14, TRN-15
**Success Criteria** (what must be TRUE):
  1. An architectural unit test introspects every public method of the Trino adapter client and asserts the first executable line calls `assert_read_only(sql)`; the classifier itself has unit tests proving it rejects `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE`, `CALL`, multi-statement blocks, comment-wrapped DDL, Unicode-escape tricks, and recursively rejects `EXPLAIN ANALYZE <inner>` when `<inner>` is not on the allowlist. (TRN-04, TRN-05 — §6.2 safety items 5 and 7)
  2. A developer can point the server at a running Trino cluster and fetch `EXPLAIN (FORMAT JSON)`, `EXPLAIN ANALYZE (FORMAT JSON)`, and `EXPLAIN (TYPE DISTRIBUTED)` for a read-only query using no-auth, Basic, or JWT-bearer auth; the JWT is read per-request and never appears in any log line. (TRN-01, TRN-03, TRN-09, TRN-11)
  3. An integration test starts a long-running Trino query, cancels it via the adapter's cancel API, and verifies the corresponding `DELETE /v1/query/{queryId}` call was observed by a recording Trino fixture; no query remains in `system.runtime.queries` after the cancel. All Trino calls occur via `asyncio.to_thread` with a bounded 4-worker thread pool and the MCP event loop never blocks (verified via an event-loop-lag probe in tests). (TRN-02, TRN-06, TRN-15 — §6.2 safety items 6 and 7)
  4. On adapter init, the server probes `SELECT node_version FROM system.runtime.nodes` and the Iceberg catalog config, records a capability matrix, and refuses to initialize against Trino < 429 with a structured error; a rule requiring a newer Trino reports `rule_skipped: requires_trino >= X` as a structured finding, never an exception. (TRN-07, TRN-08, TRN-14 — §6.2 safety item 7)
  5. The adapter can read `system.runtime.*`, `system.metadata.*`, and Iceberg metadata tables (`$snapshots`, `$files`, `$manifests`, `$partitions`, `$history`, `$refs`) for a user-supplied table via the `StatsSource`/`CatalogSource` ports; the `OfflinePlanSource` accepts a pasted `EXPLAIN (FORMAT JSON)` text payload and produces output indistinguishable by the downstream pipeline from the live-mode output (same port, same return type). (TRN-10, TRN-12, TRN-13)
**Plans**: 5 plans across 3 waves
  - [x] 02-01-classifier-auth-settings-PLAN.md — Wave 1: SqlClassifier + error taxonomy + auth builder + settings extension
  - [x] 02-02-hexagonal-ports-offline-PLAN.md — Wave 1: Hexagonal ports (PlanSource/StatsSource/CatalogSource) + OfflinePlanSource
  - [x] 02-03-trino-client-pool-cancel-PLAN.md — Wave 2: TrinoClient + QueryHandle + pool + cancel + logging + architectural invariant test
  - [x] 02-04-capabilities-live-adapters-PLAN.md — Wave 2: CapabilityMatrix + version probe + live port adapters
  - [x] 02-05-integration-harness-ci-PLAN.md — Wave 3: Integration test harness (docker-compose + testcontainers) + CI wiring
**UI hint**: no
**Needs research**: done — see 02-RESEARCH.md

### Phase 3: Plan Parser & Normalizer
**Goal**: Raw Trino `EXPLAIN` JSON is converted into two distinct typed plan classes (`EstimatedPlan` from `EXPLAIN`, `ExecutedPlan` from `EXPLAIN ANALYZE`) that tolerate version drift via per-node `raw` dict bags, normalize common operator variants (`ScanFilterProject`, `Project` wrappers), and expose Iceberg operator details (split count, file count, partition spec id). The multi-version fixture corpus that every rule will depend on is captured and snapshot-gated.
**Depends on**: Phase 2 (for live fixture capture from the Trino adapter)
**Requirements**: PLN-01, PLN-02, PLN-03, PLN-04, PLN-05, PLN-06, PLN-07
**Success Criteria** (what must be TRUE):
  1. Given a Trino `EXPLAIN (FORMAT JSON)` fixture from any of at least three supported Trino versions (429, a middle LTS, and 480+), the parser returns an `EstimatedPlan` without error and every node preserves its original fields inside a `raw` dict alongside typed fields; adding an unknown node type or a renamed field in one version does not raise — it records a `schema_drift_warning` in the plan result. (PLN-01, PLN-02, PLN-07)
  2. Given an `EXPLAIN ANALYZE (FORMAT JSON)` fixture, the parser returns an `ExecutedPlan` whose nodes expose per-operator CPU time, wall time, input/output rows, input/output bytes, peak memory, and exchange metadata as typed fields that a developer can read without dict lookups. (PLN-01, PLN-03)
  3. For an `IcebergTableScan` node, the parsed output exposes split count, file count, and partition spec identifier as first-class typed fields, sourced from the operator's raw detail string and cross-checked against the multi-version fixture snapshots. (PLN-04)
  4. A plan shape containing `ScanFilterProject` is normalized by the parser into the equivalent `TableScan + filter + projection` structure before any consumer sees it; a test fixture with a `Project` wrapper around a scan can be found by a "find scan under this subtree" walk without special-casing. (PLN-05)
  5. The multi-version fixture corpus (at least one `EXPLAIN` + one `EXPLAIN ANALYZE` per version × three versions) is stored in the repo, is gated by a `syrupy` snapshot test in CI, and every fixture parses without error; when a future Trino version adds a field, the snapshot test surfaces it as a diff rather than a crash. (PLN-06)
**Plans**: 3 plans across 2 waves + 1 gap closure
  - [x] 03-01-parser-models-normalizer-PLAN.md — Wave 1: PlanNode models, dual-path parser (JSON + text), normalizer, port/adapter migration
  - [x] 03-02-fixture-corpus-snapshots-PLAN.md — Wave 2: Multi-version fixture capture script + corpus, syrupy snapshot tests
  - [x] 03-03-iceberg-split-count-fix-PLAN.md — Gap closure: fix `iceberg_split_count` always-None (Trino 480 `Splits: N` format + `:=` operator detection fix)
**UI hint**: no
**Needs research**: done — see 03-RESEARCH.md

### Phase 4: Rule Engine & 13 Deterministic Rules
**Goal**: The deterministic core of the product — a plugin registry of rules that each consume a typed plan plus declared evidence, produce structured `RuleFinding` objects pointing at specific plan operator IDs, and never let one rule's failure abort the analysis. Ships all the table-stakes rules plus the differentiator rules that justify the tool over `EXPLAIN ANALYZE` + Slack + runbooks.
**Depends on**: Phase 3
**Requirements**: RUL-01, RUL-02, RUL-03, RUL-04, RUL-05, RUL-06, RUL-07, RUL-08, RUL-09, RUL-10, RUL-11, RUL-12, RUL-13, RUL-14, RUL-15, RUL-16, RUL-17, RUL-18, RUL-19, RUL-20, RUL-21
**Success Criteria** (what must be TRUE):
  1. A developer can write a new `Rule` subclass, register it via the plugin registry, declare its evidence requirement (`PLAN_ONLY`, `PLAN_WITH_METRICS`, `TABLE_STATS`, or `ICEBERG_METADATA`), and the engine runs it against any compatible plan without touching engine code; the engine prefetches the union of all required evidence exactly once per analysis. (RUL-01, RUL-02)
  2. When one rule raises an exception, the engine emits a structured `rule_error` finding and all other rules still run to completion; when a rule requires evidence that is not available (e.g., `ICEBERG_METADATA` in offline mode, or a feature gated by `capability_matrix < trino_480`), the engine emits a structured `rule_skipped` finding and the analysis still completes. (RUL-03, RUL-04)
  3. Running the engine on a hand-crafted synthetic-minimum fixture for any of the 13 rules (R1 missing/stale stats, R2 partition pruning failure, R3 predicate pushdown failure, R4 dynamic filtering not applied, R5 broadcast too big, R6 join order inversion, R7 CPU/wall skew, R8 excessive exchange, R9 low-selectivity scan, I1 Iceberg small files, I3 delete-file accumulation, I6 stale snapshots, I8 partition transform mismatch, plus D11 cost-vs-actual divergence) produces exactly the expected `RuleFinding` with `rule_id`, `severity`, `confidence`, human message, and a machine-readable evidence payload referencing the specific plan operator IDs the rule matched. (RUL-05, RUL-07 through RUL-20)
  4. Every rule ships with three fixture classes: a synthetic-minimum unit fixture, a realistic-from-compose fixture (captured via the Phase 3 multi-version corpus), and a negative-control fixture that the rule must NOT trigger on; the negative-control tests serve as regression guards against false positives and are part of CI. (RUL-06)
  5. Every rule threshold is declared in a config-overridable constants file with a sourced citation comment (no magic numbers); changing a threshold via config re-runs the fixture tests and at least one negative-control starts or stops triggering — verified by a parameterized test that proves the thresholds are actually data-driven. (RUL-21)
**Plans**: *(Not yet planned — run `/gsd-plan-phase 4` to generate plans)*
**UI hint**: no
**Needs research**: yes — partition-transform semantics per Trino version (Trino issue #19266) for R2/I8, and the `$files` cross-reference workaround for Trino issue #28910 for I3 (since `$partitions` does not expose delete metrics). Trigger `/gsd-research-phase` before planning.

### Phase 5: Recommendation Engine
**Goal**: Turn raw `RuleFinding` observations into prioritized, grounded, actionable `Recommendation` objects that an LLM caller or a human can apply directly. Conflict resolution for overlapping rules, audited templates keyed by rule ID (no free-form user text ever flowing into recommendation bodies), session-property grounding via the `trino_session_properties` resource, and the two narrative differentiators (table health summary, operator bottleneck ranking) all land here.
**Depends on**: Phase 4
**Requirements**: REC-01, REC-02, REC-03, REC-04, REC-05, REC-06, REC-07
**Success Criteria** (what must be TRUE):
  1. Given a set of `RuleFinding` objects, the recommender returns a list of `Recommendation` objects sorted by priority = severity × impact × confidence; each recommendation carries reasoning, expected impact, risk level, confidence level, and a list of validation steps the user can run to verify the fix. (REC-01, REC-02)
  2. When two rules attach to the same operator with conflicting recommendations, a test asserts the higher-confidence recommendation wins, the lower is demoted to a `considered_but_rejected` entry with an explicit reason, and the final output contains both the winner and the rejected alternative for auditability. (REC-04)
  3. Recommendation narrative is composed entirely from templates keyed by `rule_id` that live in source control; a unit test injects a user-origin SQL string containing a prompt-injection attempt and asserts that string never appears verbatim in any recommendation body — only templated references to plan operator IDs and rule-declared evidence fields do. (REC-03)
  4. When a rule's fix is a Trino session property, the recommendation embeds the exact `SET SESSION` statement using the property name read from the `trino_session_properties` resource; a test with a stub resource that omits a property name asserts the recommendation falls back to an advisory-only message rather than fabricating a property name. (REC-05)
  5. For any analysis that touches an Iceberg table, the recommender emits an Iceberg table health summary with snapshot count, small-file ratio, delete-file ratio, partition spec evolution state, and last compaction reference, plus an operator-level bottleneck ranking with a templated natural-language narrative for the top N operators — both rendered from structured evidence with no free-form text. (REC-06, REC-07)
**Plans**: *(Not yet planned — run `/gsd-plan-phase 5` to generate plans)*
**UI hint**: no
**Needs research**: no

### Phase 6: Safe SQL Rewrite Engine
**Goal**: A tight whitelist of `sqlglot`-AST-based SQL rewrites (regex forbidden) that preserve semantics by construction, each ships with declared preconditions, a unified diff, a justification, and — when live mode is available — a round-trip `COUNT + HASH` equivalence check on sample data. `dangerous_rewrites: false` is the default and all three-valued-logic / NULL / ordering traps stay advisory-only.
**Depends on**: Phase 4 (rules drive rewrites, e.g., I8 → partition-transform-aligned rewrite)
**Requirements**: RWR-01, RWR-02, RWR-03, RWR-04, RWR-05, RWR-06, RWR-07
**Success Criteria** (what must be TRUE):
  1. A developer can hand the rewrite engine a `SELECT *` query against an Iceberg table and receive back a rewritten query with enumerated used columns, a unified diff between original and rewritten, a list of checked preconditions, a justification, and a "not-verified-equivalent" disclaimer when live validation is not available. All parsing and regeneration is done via `sqlglot` with the Trino dialect — a code search asserts zero regex-based SQL manipulation in the rewrite module. (RWR-01, RWR-02, RWR-04)
  2. Given a `DATE(ts) = '2025-01-01'` predicate on a timestamp column, the engine emits a function-wrapped-predicate-unwrap rewrite to a half-open timestamp range; given a `ts = '2025-01-01'` predicate on a `day(ts)`-partitioned Iceberg table, the engine emits a partition-transform-aligned predicate rewrite fed by the Phase 4 I8 rule. (RWR-02, D1)
  3. Every rewrite declares its preconditions explicitly and refuses with a structured `precondition_failed` reason when any precondition is violated; a unit test feeds each whitelisted transform a query that violates one precondition at a time and asserts the refusal reason is specific and machine-readable. (RWR-03)
  4. With `dangerous_rewrites: false` (the default), a query pattern matching `NOT IN ↔ NOT EXISTS`, `LEFT JOIN` predicate motion, correlated subquery unwrap, window frame mutation, `CASE` restructuring, `UNNEST`, UDFs, or `WITH RECURSIVE` returns only advisory-only notes — never a rewrite; a test asserts none of those transforms can ever appear in the rewrite output under the default config. `EXISTS ↔ JOIN` is off by default and, when enabled, only runs when join keys are provably `NOT NULL` from catalog introspection. (RWR-05, RWR-07)
  5. When live mode is available, an integration test runs a rewrite through the engine, executes both the original and rewritten SQL against the compose stack, computes `SELECT COUNT(*), SUM(HASH(...))` on both, and asserts the rewrite is either marked "validated — equivalent" or "failed validation" with the delta surfaced; any non-zero delta forces a failed validation regardless of what the transform logic says. (RWR-06)
**Plans**: *(Not yet planned — run `/gsd-plan-phase 6` to generate plans)*
**UI hint**: no
**Needs research**: yes — `sqlglot` Trino dialect expression-walking API (precondition checks + rewrite construction) and property-based equivalence testing patterns (hypothesis vs custom fixtures). Trigger `/gsd-research-phase` before planning.

### Phase 7: Comparison Engine
**Goal**: Honest before/after measurement — CPU time as the primary metric (never wall time), N=5 paired-alternation runs with first discarded, Iceberg snapshot pinned so both runs see identical data, a zero-row-delta correctness check, and a HIGH/MEDIUM/LOW confidence classification based on CPU-time delta versus median absolute deviation. The comparison engine is the feedback loop that closes the rewrite story.
**Depends on**: Phase 3 (plan parser), Phase 6 (rewrites produce the "after" SQL)
**Requirements**: CMP-01, CMP-02, CMP-03, CMP-04, CMP-05, CMP-06
**Success Criteria** (what must be TRUE):
  1. A developer can hand the comparison tool two `EXPLAIN ANALYZE` runs and receive back a structured `ComparisonReport` containing CPU time (primary, labelled), wall time (reported but labelled "volatile — do not use for go/no-go"), scanned bytes, peak memory, shuffle bytes, stage count, and output row count with absolute deltas and % change for each. (CMP-01, CMP-02)
  2. In live mode, a comparison over two SQL statements runs N=5 paired alternations (A, B, A, B, A, B, A, B, A, B), discards the first run as warm-up, pins the Iceberg snapshot on both queries so both runs see identical data, and reports the CPU-time median with median absolute deviation (MAD) across the retained runs. (CMP-03)
  3. An integration test runs a comparison across an Iceberg snapshot boundary (by committing a write to the table between the two runs) and asserts the comparator returns a structured `snapshot_boundary_error` and refuses to produce a report. (CMP-04)
  4. An integration test runs a comparison where the rewritten SQL returns a different number of output rows than the original and asserts the comparator surfaces this as a potential correctness bug — not as a "win" — in the structured report. (CMP-05)
  5. Given the same paired run data, the comparator emits a `confidence` field of HIGH / MEDIUM / LOW based on the CPU-time delta divided by the MAD (HIGH when delta > 3×MAD and consistent sign, MEDIUM for mixed evidence, LOW when delta is within noise), and the classification appears alongside the raw numbers so a caller can show the user whether to trust the result. (CMP-06)
**Plans**: *(Not yet planned — run `/gsd-plan-phase 7` to generate plans)*
**UI hint**: no
**Needs research**: no

### Phase 8: MCP Surface (Tools, Resources, Prompts)
**Goal**: Wire Phases 2 through 7 onto the shared `FastMCP` app object via a thin service layer. All 8 tools, 4 resources, and 3 prompts ship with strict JSON Schemas, static descriptions loaded at startup (preventing tool-description prompt injection), untrusted-content envelopes on every user-origin payload, and `analyze_trino_query` supports partial-results-on-timeout. The single `FastMCP` app is reused by stdio and Streamable HTTP transports with zero transport-aware code in tool handlers.
**Depends on**: Phases 2, 3, 4, 5, 6, 7
**Requirements**: MCP-01, MCP-02, MCP-03, MCP-04, MCP-05, MCP-06, MCP-07, MCP-08, MCP-09, MCP-10, MCP-11, MCP-12, MCP-13, MCP-14, MCP-15, MCP-16, MCP-17, MCP-18
**Success Criteria** (what must be TRUE):
  1. From a Claude Code session, a user can invoke all 8 tools against a running server and get structured responses: `analyze_trino_query` runs the end-to-end pipeline (plan fetch → rules → recommender → report) with partial-results-on-timeout on a budget breach; `get_explain_json`, `get_explain_analyze`, and `get_table_statistics` return raw structured data; `detect_optimization_issues` returns findings; `suggest_optimizations` returns recommendations; `rewrite_sql` returns rewrites with diffs; `compare_query_runs` returns a `ComparisonReport`. `get_explain_analyze` refuses execution when the pre-flight CBO cost gate (estimated `cpuCost` or `outputBytes` over budget) is breached and returns a structured refusal. (MCP-01 through MCP-08)
  2. All 4 resources (`trino_optimization_playbook`, `iceberg_best_practices`, `trino_session_properties`, `query_anti_patterns`) are readable from a Claude Code session via `@`-autocomplete and return curated markdown loaded via `importlib.resources` from the installed package (no filesystem assumptions); the `trino_session_properties` resource is the single source of truth consumed by the Phase 5 recommender. (MCP-09, MCP-10, MCP-11, MCP-12, MCP-18)
  3. All 3 prompts (`optimize_trino_query`, `iceberg_query_review`, `generate_optimization_report`) are listable from a Claude Code session, render from jinja templates, and when invoked against the server produce tool-call sequences that the server's tools satisfy end-to-end. (MCP-13, MCP-14, MCP-15)
  4. A code review asserts every tool handler is under ~30 lines and delegates to the service layer; the same `FastMCP` app object is wired to both stdio and Streamable HTTP transports via `app.py` with zero transport-aware branches inside any tool handler; a snapshot test of the registered tool descriptions asserts they are identical across restarts (no user input flows into descriptions, preventing tool-description prompt injection). (MCP-16, MCP-17)
  5. Every tool schema still satisfies the Phase 1 strict-schema posture (`additionalProperties: false`, bounded `maxLength`, identifier `pattern`, bounded arrays) — verified by a schema-lint test that scans all registered tools — and every tool output containing a user-origin string wraps it in the `untrusted_content` envelope established in Phase 1. (reinforces PLAT-10, PLAT-11)
**Plans**: *(Not yet planned — run `/gsd-plan-phase 8` to generate plans)*
**UI hint**: no
**Needs research**: no

### Phase 9: Integration Stack & CI
**Goal**: Productize the docker-compose validation stack (Trino 480 + Lakekeeper Iceberg REST catalog + PostgreSQL + MinIO), wire the realistic-fixture capture pass into the test suite, run the prompt-injection adversarial corpus against every tool, and prove the `{3.11, 3.12, 3.13} × {linux, mac, win}` install matrix works in CI. This is the phase that proves the system works end-to-end against a real stack rather than just fixtures.
**Depends on**: Phase 8 (tools must exist before adversarial corpus can probe them)
**Requirements**: TST-01, TST-02, TST-03, TST-04, TST-05, TST-06, TST-07, TST-08
**Success Criteria** (what must be TRUE):
  1. A developer can clone the repo and run `docker compose up` to start Trino 480 + Lakekeeper + PostgreSQL + MinIO on `127.0.0.1` only, and `pytest -m integration` passes against it using `testcontainers[trino,minio]` and the `DockerCompose` fixture class; integration tests are opt-in in CI via the `@pytest.mark.integration` marker so the fast path still runs on every commit. (TST-01, TST-02)
  2. Every Phase 4 rule has CI coverage from all three fixture classes — synthetic (unit), realistic-from-compose (captured against the productized stack), and negative-control — and every negative-control is exercised on each CI run as a regression guard against false positives. A `syrupy` snapshot test covers the full `AnalysisReport` JSON output for a canonical query set and fails on any diff. (TST-03, TST-04)
  3. A stdio-cleanliness test in CI boots the server, sends a JSON-RPC `initialize`, and asserts that stdout contains only valid JSON-RPC frames (bytes between frames must be empty) — the same day-one guard from Phase 1 now exercised against the full production wiring. (TST-05)
  4. A prompt-injection adversarial corpus runs against every MCP tool and asserts: (a) the server never passes untrusted content outside a typed envelope in any tool response, and (b) the SQL classifier gate rejects injected DDL/DML wrapped in SQL comments, Unicode tricks, and multi-statement blocks. (TST-06)
  5. `.env.example` ships randomized MinIO credentials (re-rolled by a setup script), compose binds every service to `127.0.0.1` only, `gitleaks` runs in CI on every commit, and the install-matrix CI builds and runs the smoke test (stdio `initialize` + `mcp_selftest` round trip) on `{3.11, 3.12, 3.13} × {macOS, Linux, Windows}`; a matrix failure blocks merge. (TST-07, TST-08)
**Plans**: *(Not yet planned — run `/gsd-plan-phase 9` to generate plans)*
**UI hint**: no
**Needs research**: yes — Lakekeeper compose configuration for the `trinodb/trino:480` combination, MinIO bucket/policy bootstrap sequence, `testcontainers` `DockerCompose` wait strategies, and sourcing/authoring the prompt-injection adversarial corpus (OWASP LLM Top 10 / promptfoo vs custom). Trigger `/gsd-research-phase` before planning.

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Skeleton & Safety Foundation | 6/6 | Complete | 2026-04-12 |
| 2. Trino Adapter & Read-Only Gate | 5/5 | Complete | 2026-04-12 |
| 3. Plan Parser & Normalizer | 2/2 | Complete | 2026-04-12 |
| 4. Rule Engine & 13 Deterministic Rules | 0/? | Not started | - |
| 5. Recommendation Engine | 0/? | Not started | - |
| 6. Safe SQL Rewrite Engine | 0/? | Not started | - |
| 7. Comparison Engine | 0/? | Not started | - |
| 8. MCP Surface (Tools, Resources, Prompts) | 0/? | Not started | - |
| 9. Integration Stack & CI | 0/? | Not started | - |

## Requirement Coverage

Every v1 REQ-ID is mapped to exactly one phase. No orphans, no duplicates.

| REQ-ID | Phase | REQ-ID | Phase | REQ-ID | Phase |
|--------|-------|--------|-------|--------|-------|
| PLAT-01 | 1 | TRN-01 | 2 | PLN-01 | 3 |
| PLAT-02 | 1 | TRN-02 | 2 | PLN-02 | 3 |
| PLAT-03 | 1 | TRN-03 | 2 | PLN-03 | 3 |
| PLAT-04 | 1 | TRN-04 | 2 | PLN-04 | 3 |
| PLAT-05 | 1 | TRN-05 | 2 | PLN-05 | 3 |
| PLAT-06 | 1 | TRN-06 | 2 | PLN-06 | 3 |
| PLAT-07 | 1 | TRN-07 | 2 | PLN-07 | 3 |
| PLAT-08 | 1 | TRN-08 | 2 | RUL-01 | 4 |
| PLAT-09 | 1 | TRN-09 | 2 | RUL-02 | 4 |
| PLAT-10 | 1 | TRN-10 | 2 | RUL-03 | 4 |
| PLAT-11 | 1 | TRN-11 | 2 | RUL-04 | 4 |
| PLAT-12 | 1 | TRN-12 | 2 | RUL-05 | 4 |
| PLAT-13 | 1 | TRN-13 | 2 | RUL-06 | 4 |
| RUL-07 | 4 | TRN-14 | 2 | RUL-08 | 4 |
| RUL-09 | 4 | TRN-15 | 2 | RUL-10 | 4 |
| RUL-11 | 4 | REC-01 | 5 | RUL-12 | 4 |
| RUL-13 | 4 | REC-02 | 5 | RUL-14 | 4 |
| RUL-15 | 4 | REC-03 | 5 | RUL-16 | 4 |
| RUL-17 | 4 | REC-04 | 5 | RUL-18 | 4 |
| RUL-19 | 4 | REC-05 | 5 | RUL-20 | 4 |
| RUL-21 | 4 | REC-06 | 5 | REC-07 | 5 |
| RWR-01 | 6 | CMP-01 | 7 | MCP-01 | 8 |
| RWR-02 | 6 | CMP-02 | 7 | MCP-02 | 8 |
| RWR-03 | 6 | CMP-03 | 7 | MCP-03 | 8 |
| RWR-04 | 6 | CMP-04 | 7 | MCP-04 | 8 |
| RWR-05 | 6 | CMP-05 | 7 | MCP-05 | 8 |
| RWR-06 | 6 | CMP-06 | 7 | MCP-06 | 8 |
| RWR-07 | 6 | MCP-07 | 8 | MCP-08 | 8 |
| MCP-09 | 8 | MCP-10 | 8 | MCP-11 | 8 |
| MCP-12 | 8 | MCP-13 | 8 | MCP-14 | 8 |
| MCP-15 | 8 | MCP-16 | 8 | MCP-17 | 8 |
| MCP-18 | 8 | TST-01 | 9 | TST-02 | 9 |
| TST-03 | 9 | TST-04 | 9 | TST-05 | 9 |
| TST-06 | 9 | TST-07 | 9 | TST-08 | 9 |

**Coverage totals by phase:**

| Phase | Count | Requirements |
|-------|-------|--------------|
| 1 | 13 | PLAT-01..13 |
| 2 | 15 | TRN-01..15 |
| 3 | 7  | PLN-01..07 |
| 4 | 21 | RUL-01..21 |
| 5 | 7  | REC-01..07 |
| 6 | 7  | RWR-01..07 |
| 7 | 6  | CMP-01..06 |
| 8 | 18 | MCP-01..18 |
| 9 | 8  | TST-01..08 |
| **Total** | **102** | **100% v1 coverage, 0 unmapped** |

## Research-Needed Phases

These phases trigger `/gsd-research-phase` before planning, per research SUMMARY §7.2:

| Phase | Research need |
|-------|---------------|
| 2 | trino-python-client cancellation mechanics, JWT refresh hooks, Lakekeeper config API |
| 3 | Multi-version EXPLAIN JSON fixture capture (highest single unknown in the project) |
| 4 | Partition-transform semantics per Trino version (#19266); Iceberg delete-file workaround (#28910) |
| 6 | sqlglot expression-walking API; property-based equivalence testing patterns |
| 9 | Lakekeeper compose, MinIO bootstrap, testcontainers wait strategies, prompt-injection corpus sourcing |

Phases 1, 5, 7, 8 proceed directly to planning — patterns are well-established in existing research files.

---

*Roadmap created: 2026-04-11*
*Last updated: 2026-04-11 after initialization*
