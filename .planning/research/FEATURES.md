# Feature Research

**Domain:** Trino + Iceberg query optimization MCP server
**Researched:** 2026-04-11
**Confidence:** HIGH (core optimization rules, Iceberg metadata, MCP primitives grounded in official docs; differentiators drawn from well-documented pain points)

## Scope Note

This document is opinionated. It treats the target user as a data engineer staring at a slow Trino + Iceberg query inside Claude Code. Everything is filtered through: "does this feature save me a 45-minute EXPLAIN ANALYZE debugging session?" If the answer is no, it is not a table stake.

Primary competition is NOT other MCP servers — it is:
1. Hand-reading `EXPLAIN ANALYZE` output
2. Trino Web UI Stage Performance tab
3. Ad-hoc SQL against `system.runtime.*` and Iceberg metadata tables
4. Internal Slack channels and Confluence runbooks
5. dbt-profiler / SQLMesh / bespoke dashboards (adjacent, not direct)

---

## Feature Landscape

### Table Stakes (Users Expect These)

If any of these are missing, an experienced Trino + Iceberg engineer will close the tool within five minutes and go back to `EXPLAIN ANALYZE`.

| # | Feature | Why Expected | Complexity | Notes |
|---|---------|--------------|------------|-------|
| T1 | **`analyze_trino_query` end-to-end pipeline** | Single entry point. User pastes SQL, gets structured findings + recommendations. Matches the "one prompt, full answer" MCP mental model. | HIGH | Depends on T2–T6. This is the crown-jewel tool. |
| T2 | **EXPLAIN (FORMAT JSON) fetch + parse into typed operator tree** | Without a parsed plan, every other feature is string-matching guesswork. | HIGH | Must normalize EXPLAIN vs EXPLAIN ANALYZE shape differences. Iceberg-specific operators (`IcebergTableScan`, split info) must be first-class. |
| T3 | **EXPLAIN ANALYZE fetch with per-operator CPU / wall / input rows / peak memory / distribution percentiles** | These are the exact fields engineers read today. CPU distribution percentiles (p50/p90/p99) are the skew detection signal. | HIGH | Trino exposes p01/p05/p10/p25/p50/p75/p90/p95/p99 — preserve them. |
| T4 | **Iceberg metadata reads: `$snapshots`, `$files`, `$manifests`, `$partitions`, `$history`, `$refs`** | Any Iceberg diagnostic is impossible without these. Each is read as a separate entity, so permissions must be handled per-table. | MEDIUM | Requires `SELECT` grant on each metadata table. |
| T5 | **Live + Offline dual mode** | Live mode for engineers with cluster access; offline mode for analysts who only have a pasted plan. Offline mode is what makes this a "paste in Claude Code" tool. | MEDIUM | Offline mode is the underrated MVP feature — lowers activation cost to zero. |
| T6 | **Deterministic rule engine — 10+ rules, each testable in isolation, producing structured findings** | Determinism is the whole trust story. LLMs hallucinate; rules do not. Re-running the same input must yield identical output. | HIGH | See "Optimization Rules" section below for the non-negotiable minimum set. |
| T7 | **Partition pruning failure detection** | The #1 real-world cliff in Trino + Iceberg. A partition transform mismatch (e.g., `day(ts)` vs `ts >= '2026-04-11 14:30'`) silently disables pruning. | MEDIUM | Detect by comparing filter predicates against Iceberg partition spec + checking scan row counts vs table totals. |
| T8 | **Dynamic filtering not applied detection** | Second-biggest real-world cliff. DF only works when the join predicate is on a partitioned / sorted / bloom-indexed column on the probe side. Most users don't realize when it silently falls back. | MEDIUM | Detect by looking for `DynamicFilter` in probe-side scan of join plan nodes. |
| T9 | **Missing / stale statistics detection** | Without `ANALYZE`, CBO falls back to `ELIMINATE_CROSS_JOINS` and join reordering degrades. Checking `system.metadata.*` + Iceberg file stats reveals this immediately. | LOW | Flag any scan whose cost estimate is missing or where stats are older than last snapshot. |
| T10 | **Small-files / split explosion detection** | Iceberg best practice is ~100MB target file size. High split count = file open overhead dominates. Query `$files` for file size distribution. | LOW | Histogram over `$files.file_size_in_bytes`. Flag if p50 < 16MB or split count > 10k. |
| T11 | **Delete-file accumulation detection (position + equality deletes)** | MoR v2 tables accumulate delete files over time; each data file can have 100+ delete files attached, degrading reads drastically. Trino's `$partitions` does NOT currently expose delete-file metrics, so this requires `$files` + cross-reference. | MEDIUM | Known Trino gap (issue #28910). Worth a dedicated rule; clear recommendation is `ALTER TABLE ... EXECUTE optimize` / `remove_orphan_files` / `expire_snapshots`. |
| T12 | **Prioritized, structured recommendations (severity × impact × confidence)** | Users don't want 47 findings. They want "fix these three, in this order, and here's why." | MEDIUM | JSON schema must be stable — LLM clients key off field names. |
| T13 | **Each recommendation includes: reasoning, expected impact, risk level, validation steps** | Distinguishes a tool from a linter. "Add ANALYZE" without "re-run EXPLAIN ANALYZE and compare scanned bytes" is a half-answer. | LOW | Template per rule. |
| T14 | **Read-only safety guarantee — never issues DML/DDL/DDL-adjacent statements** | LLM agent invocation model: one hole = one exploit. Must be enforced by construction (parser-level denylist), not just "don't call it." | LOW | Mentioned in PROJECT.md; listing it here for completeness — it is a feature, not a side-effect. |
| T15 | **Structured JSON output for every tool, with strict JSON Schema** | MCP tools are only useful to LLM clients if the schema is stable and typed. Free-form markdown breaks downstream automation. | LOW | Output schema is part of the public API. |
| T16 | **`get_explain_json`, `get_explain_analyze`, `get_table_statistics` as standalone tools** | Escape hatch. When the rule engine misses something, an agent still needs raw plan / stats access. These compose. | LOW | Thin wrappers around the Trino adapter. |
| T17 | **`trino_session_properties` reference resource** | Half of real-world tuning is session-property adjustment (`join_reordering_strategy`, `join_distribution_type`, `join_max_broadcast_table_size`, `use_preferred_write_partitioning`, `task_concurrency`, etc.). An LLM cannot suggest these reliably without a grounded reference. | LOW | Static Markdown resource keyed to current Trino version. Must be refreshed when Trino versions change. |
| T18 | **`iceberg_best_practices` resource** | Same story — grounds the LLM. Covers partition transforms, file sizes, compaction, snapshot expiration, metadata maintenance. | LOW | Static curated content. |
| T19 | **`query_anti_patterns` resource** | The catalog of "don't do this" — `SELECT *` on wide columnar tables, `WHERE function(column) = literal`, correlated subqueries over large tables, `DISTINCT` + `ORDER BY` combos, etc. | LOW | Text content, no code. |
| T20 | **`optimize_trino_query` MCP prompt** | The "how do I use this thing" entry point. A one-click prompt that fires `analyze_trino_query` with the right framing and renders the output as a human-readable report. | LOW | Prompt template. Claude Code surfaces it as `/mcp__trino-optimizer__optimize_trino_query`. |
| T21 | **Structured query logging of every Trino statement issued** | Auditability. Required because an LLM is invoking it. Users will ask "what did you run on my cluster?" | LOW | Write-ahead log with timestamps, user, statement hash, duration. |
| T22 | **Auth: no-auth / basic / JWT** | Covers OSS Trino, self-hosted, Starburst Galaxy, Ahana. Without this the tool doesn't connect. | LOW | PROJECT.md-stated constraint. |

### Differentiators (Competitive Advantage)

These are what make this MCP server genuinely better than `EXPLAIN ANALYZE` + Slack + hand-written runbooks. They are the reason someone picks this over rolling their own internal dashboard.

| # | Feature | Value Proposition | Complexity | Notes |
|---|---------|-------------------|------------|-------|
| D1 | **Partition-transform-aware predicate analysis** | Detects when a user's `WHERE ts BETWEEN ...` doesn't match `day(ts)` / `hour(ts)` / `bucket(N, id)` partitioning, and generates a pruning-friendly rewrite (e.g., `WHERE ts >= TIMESTAMP '2026-04-11 00:00:00' AND ts < TIMESTAMP '2026-04-12 00:00:00'`). This is the single biggest win in real deployments. | HIGH | Requires parsing filter expression, cross-referencing Iceberg partition spec, and proving semantic equivalence. |
| D2 | **Session-property recommendations with exact `SET SESSION` statements** | Instead of "consider tuning join distribution," emits `SET SESSION join_distribution_type = 'BROADCAST'; SET SESSION join_max_broadcast_table_size = '200MB';` with reasoning and rollback instructions. Actionable, not advisory. | MEDIUM | Requires the `trino_session_properties` reference and rule-to-property mapping. |
| D3 | **Before/after comparison with delta percentages across wall time, CPU, scanned bytes, peak memory, split count, stage CPU skew** | Closes the loop. The user runs the original, applies the fix, runs again, and gets a structured diff — not a mental calculation from two terminal windows. | MEDIUM | `compare_query_runs` tool. Parses two EXPLAIN ANALYZE outputs and produces a delta report. |
| D4 | **Skew detection via CPU/wall time distribution percentiles** | The p99/p50 ratio on any stage is the skew signal. Most users don't read those percentiles manually. Auto-flag anything where p99 > 5× p50. | LOW | Trino already exposes the percentiles; just needs interpretation. |
| D5 | **Iceberg-specific "health summary" for every scanned table** | For each table touched by the query: snapshot count, small-file ratio, delete-file ratio, stale stats, last compaction time, partition spec evolution history. One glance tells you whether the table is the problem or the query is. | MEDIUM | Queries `$snapshots`, `$files`, `$manifests`, `$history`. High-leverage: users rarely inspect these manually. |
| D6 | **Safe SQL rewrites with a semantic-preservation proof + diff view** | Not just "here's the new SQL" — "here's the new SQL, here's a colored diff, and here is why it's semantically identical (projection pruning / predicate pushdown / EXISTS↔JOIN under NOT NULL)." Diff + proof builds trust. | HIGH | Needs a SQL parser (sqlglot) and rewrite rules that each come with a preservation argument. |
| D7 | **`iceberg_query_review` prompt — full table-health + query-health audit workflow** | A single invocation that looks at the query AND every table it touches AND the Iceberg metadata AND the cluster stats. This is the "I inherited a slow dashboard, help" workflow. | MEDIUM | Orchestrates multiple tool calls behind one prompt. |
| D8 | **Operator-level bottleneck ranking with a natural-language narrative per operator** | "Fragment 2's HashJoin is 78% of CPU time because probe side has 2.1B rows with no dynamic filter. Here's why DF wasn't applied: build side estimate is missing because `ANALYZE` was never run on `orders`." Grounded narrative beats raw numbers. | MEDIUM | Rule engine findings → structured narrative template. LLM clients can use this directly. |
| D9 | **Projection pushdown effectiveness check** | Explicitly detects `SELECT *` on wide tables and quantifies the I/O penalty (scanned columns / total columns). Iceberg is columnar; this is almost always a meaningful win. | LOW | Compare projected columns to table schema. |
| D10 | **Bloom filter / sort order / file-level stats advisory** | Recommends adding/tuning Iceberg bloom filters on high-cardinality predicate columns, and sort orders for range scans. Currently a rarely-used Iceberg feature because nobody knows when to reach for it. | MEDIUM | Requires knowing cardinality + predicate patterns + file-level min/max spread. |
| D11 | **Cost-vs-actual divergence reporter** | Compares CBO cost estimates from EXPLAIN to actuals from EXPLAIN ANALYZE and flags operators where the optimizer was wrong by >5×. This is a smoking gun for "ANALYZE is stale" or "stats don't match reality." | MEDIUM | Needs both plans + correlation by node ID. |
| D12 | **Claude Code-native workflow: paste SQL → get report → click into specific findings** | The user is already in Claude Code. The tool shouldn't require context-switching. Prompts are surfaced via `/mcp__trino-optimizer__optimize_trino_query`; resources via `@` autocomplete. Output is formatted so that clicking into a finding loads the relevant session properties / anti-pattern resource inline. | LOW | Mostly UX: prompt framing, response structure, resource naming. High leverage despite low complexity. |
| D13 | **Deterministic fixture replay for rule validation** | Every rule has a fixture plan; fixture → expected output is a regression test. When a user reports "this rule missed my case," we add their plan as a fixture. Over time, the rule engine's real-world coverage grows. Matters because it makes bug reports actionable. | LOW | Enables fast iteration, not a user-visible feature per se, but it's what makes the tool reliable. |
| D14 | **Partition spec evolution awareness** | Iceberg supports partition spec evolution. Most tools assume the latest spec applies to all files, but old files may have a different spec. Detecting this and warning the user avoids confusing pruning diagnostics. | MEDIUM | Requires reading `$files.spec_id` and cross-referencing historical specs. |
| D15 | **Manifest fragmentation detection** | High manifest count = slow scan planning even before any data is read. Recommends `ALTER TABLE ... EXECUTE optimize_manifests`. | LOW | Query `$manifests`, count + size distribution. |

### Anti-Features (Commonly Requested, Often Problematic)

These are scope traps. Each has surface appeal and each would destroy the value proposition.

| # | Anti-Feature | Why Requested | Why Problematic | Alternative |
|---|--------------|---------------|-----------------|-------------|
| A1 | **Unsafe semantic-changing rewrites (correlated subquery → join, DISTINCT removal, implicit cast coercions, NULL-handling changes)** | "Just make it faster, I don't care how." | A single silent correctness bug destroys all trust. The user is running financial / operational queries; "mostly correct" is worse than slow. PROJECT.md already lists this out of scope — keep it there. | Advisory-only mode: flag the anti-pattern, explain the rewrite, require the human to approve + apply. |
| A2 | **Arbitrary SELECT execution ("preview the query so I can see results")** | Users want to see output; obvious ergonomic win. | Immediately weaponizable by an LLM agent. A query can scan petabytes, leak data, or exfiltrate PII. Blast radius is unbounded. | Keep to EXPLAIN / EXPLAIN ANALYZE / metadata reads only. If users need previews, they run them in their normal client. |
| A3 | **DDL/DML generation for compaction (`ALTER TABLE ... EXECUTE optimize`)** | The tool detects a compaction need; letting it run the fix is the obvious next step. | Compaction can be hours-long, expensive, and affects production tables. Turning an MCP server into an operator is a scope explosion and a safety hazard. | Generate the statement as a recommendation with risk level and cost estimate. Let a human run it. |
| A4 | **A reimplementation of Trino's CBO** | "If we parse the plan, we can do better than Trino's optimizer." | Trino's CBO is thousands of engineer-years. We cannot beat it; we can only advise it. PROJECT.md already excludes this. | Feed better stats into Trino's CBO (via ANALYZE recommendations), adjust session properties, and trust the engine. |
| A5 | **Multi-engine support (Spark, Presto OSS, DuckDB, Snowflake, BigQuery) in v1** | "Why limit to Trino? Add them all!" | Each engine has different plan formats, statistics semantics, rule sets, and correctness guarantees. A tool that's mediocre at five engines is worse than a tool that's excellent at one. | Architect for extensibility (plugin rule engine), ship only Trino+Iceberg in v1. |
| A6 | **Non-Iceberg table format rules (Hive, Delta, Hudi)** | Same reasoning as A5. | Each format has different metadata shapes, different compaction semantics, different delete-file models. Iceberg expertise does not transfer. | Architect rules with a format-specific interface; ship Iceberg only. |
| A7 | **A query editor / syntax-highlighted UI in the server** | "Wouldn't it be nice to edit the query in the tool?" | Server != client. Claude Code, Claude Desktop, and custom MCP clients already provide the UI. Building one is wasted effort and creates two places to fix bugs. | Server-only. Clients handle presentation. |
| A8 | **Automatic periodic background analysis ("watch my cluster and tell me what's slow")** | "Run this on a schedule." | Cron jobs + dashboards are a different product. Makes the server stateful, increases surface area, duplicates observability tools. | Users invoke on-demand via MCP. If they want scheduling, they wire it to their scheduler. |
| A9 | **Full-text storage of query history for training / ML** | "If you have everything, you can learn patterns." | Privacy nightmare, storage explosion, and no proven value over deterministic rules. PROJECT.md sets "deterministic rules first" as a core principle. | Log only what's necessary for audit (statement hash, timing). No query text storage beyond session. |
| A10 | **"AI-generated" rewrites (LLM-authored SQL with no grounding)** | "Let Claude write the rewrite." | This is exactly the failure mode the grounded rule engine exists to prevent. Hallucinated rewrites silently break correctness. | Rule engine proposes rewrites from a fixed catalog of safe transforms. LLM narrates, does not generate. |
| A11 | **Kerberos / mTLS auth in v1** | "Enterprise needs it." | Pulls JVM-ish complexity, cert management, and platform-specific code into a pure-Python server. | Ship basic + JWT. Add per user request. PROJECT.md already defers. |
| A12 | **A generic "query advisor" that pretends to handle any SQL** | "Be general." | Generic advice is worthless advice. Users want Trino + Iceberg specifics, not "consider adding indexes" (Iceberg has no indexes in the traditional sense). | Be aggressively specific. Reference Trino session property names. Reference Iceberg metadata table names. Specificity is the product. |
| A13 | **Writing to Trino event listener / query telemetry** | "We could log to Trino's event listener for better data." | Requires cluster-side plugin install; now you have a distributed component. Out of scope, wrong deployment model. | Stick to client-side read access. |
| A14 | **Cached analysis results across sessions** | "Don't re-analyze the same query twice." | Cache invalidation on a live cluster (new snapshots, new stats, changed data) is hard. Determinism is already the win; caching adds complexity without user value. | Re-run each invocation. Fast path is already fast because rules are cheap. |

---

## The Optimization Rules That Actually Matter

This is a functional-area deep dive. Each rule is a T6 sub-feature. The rule engine is useless if it doesn't cover these specifically — these are the real-world pain points, not theoretical ones.

### Query analysis rules (beyond basic string matching)

| Rule ID | Detects | Why It Matters | Complexity |
|---------|---------|----------------|------------|
| R1 | Missing / stale table statistics (no `ANALYZE` ever run, or `ANALYZE` older than newest snapshot) | CBO falls back to `ELIMINATE_CROSS_JOINS` without stats; join order degrades catastrophically. | LOW |
| R2 | Partition pruning failure (filter doesn't match partition transform) | Primary real-world cliff. Silent; user sees full scan. | MEDIUM |
| R3 | Predicate pushdown failure (function-wrapped column: `WHERE DATE(ts) = ...`, `WHERE LOWER(col) = ...`) | Prevents pruning and file-level stat filtering. | LOW |
| R4 | Dynamic filtering not applied (join build side estimate missing, or probe scan lacks `DynamicFilter`) | Second-biggest real-world cliff. | MEDIUM |
| R5 | Join build side too large (broadcast join on >100MB table without `join_max_broadcast_table_size` tuning) | Blows up memory or silently falls back to partitioned. | LOW |
| R6 | Join order inversion (large table on build side, small on probe side) | CBO couldn't reorder due to missing stats. | LOW |
| R7 | CPU skew (p99/p50 > 5× on any stage's CPU distribution) | Classic hot-key / hot-partition signal. | LOW |
| R8 | Excessive exchange volume (shuffle bytes > scan bytes on any fragment) | Wrong distribution type, or missing partition-aware insert. | MEDIUM |
| R9 | Low-selectivity scan (output rows / input rows < 1% with no partition pruning) | Reading too much to throw most of it away. | LOW |
| R10 | `SELECT *` on wide columnar table (projected / total > 50%) | Defeats columnar I/O benefits. | LOW |
| R11 | `ORDER BY` without `LIMIT` on large result | Full global sort; almost always unintended. | LOW |
| R12 | `DISTINCT` over high-cardinality columns without `approx_distinct` | Memory pressure; often user doesn't need exactness. | LOW |
| R13 | Subquery in `IN` clause that should be `EXISTS` (or vice versa) | Can change plan significantly. | MEDIUM |
| R14 | Correlated subquery in `SELECT` list (flagged, not rewritten — unsafe) | Advisory only (see A1). | LOW |
| R15 | Window function without partitioning on large data | Unpartitioned window = single-stage bottleneck. | LOW |
| R16 | Cost-estimate vs actual divergence > 5× on any operator | Smoking gun for stale stats. | MEDIUM |

### Iceberg-specific rules (the differentiator territory)

| Rule ID | Detects | Why It Matters | Complexity |
|---------|---------|----------------|------------|
| I1 | Small-files explosion (p50 file size < 16MB, or split count > 10k) | File open overhead dominates. | LOW |
| I2 | Manifest fragmentation (too many manifests, or manifests not clustered by partition) | Slow scan planning before any data is read. | LOW |
| I3 | Position delete file accumulation (> N delete files per data file) | MoR degradation; query merges at read time. Known blind spot: Trino's `$partitions` doesn't expose delete metrics (issue #28910), must cross-reference `$files`. | MEDIUM |
| I4 | Equality delete file accumulation | Similar to I3 but with its own performance profile — equality deletes are re-applied per read. | MEDIUM |
| I5 | Dangling deletes (delete files referring to data files that are no longer live) | Pure waste; cleaned up by `optimize`. | LOW |
| I6 | Stale snapshot accumulation (> 500 snapshots, or oldest snapshot > 7 days past retention) | Metadata overhead; recommend `expire_snapshots`. | LOW |
| I7 | Partition spec evolution with mixed-spec file set | Pruning diagnostics may be misleading. | MEDIUM |
| I8 | Partition transform mismatch between query filter and partition spec | Direct feed into D1. | MEDIUM |
| I9 | Missing bloom filter on high-cardinality equality predicate | Unused Iceberg feature that would help this query. | MEDIUM |
| I10 | Sort order / clustering advisory (range scan on unsorted column with high file-level min/max overlap) | Hints at a `rewrite_data_files` with `SORT_ORDER`. | MEDIUM |
| I11 | Table with missing / never-run Iceberg `compute_table_statistics` | CBO can use Iceberg-native stats; many tables never have them computed. | LOW |

### Safe rewrites (high leverage, low risk)

The rewrite engine should only touch rewrites where semantic preservation is provable. Anything in the "tempting but unsafe" column is flagged as advisory only.

**High-leverage AND safe:**

| Rewrite | Why Safe | Why High-Leverage |
|---------|----------|-------------------|
| Projection pruning (`SELECT *` → enumerate used columns) | Only the columns the query actually references are kept; result set unchanged. | Columnar I/O dominated by scanned-column count. |
| Partition-transform-aligned predicate rewrite (`WHERE ts BETWEEN '2026-04-11 00:00' AND '2026-04-11 23:59'` → `WHERE ts >= TIMESTAMP '2026-04-11 00:00:00' AND ts < TIMESTAMP '2026-04-12 00:00:00'`) | Inclusive-end vs half-open is semantically preserved when the end value cleanly maps; otherwise we don't rewrite. | Enables partition pruning — the #1 win. |
| Function-wrapped predicate unwrapping (`WHERE DATE(ts) = '2026-04-11'` → `WHERE ts >= TIMESTAMP '2026-04-11 00:00' AND ts < TIMESTAMP '2026-04-12 00:00'`) | Provable equivalence for specific function classes (`DATE`, `YEAR`, `DATE_TRUNC` with constant unit). | Enables pushdown. |
| Partial aggregation hint via session property | Session property doesn't change SQL semantics. | Significant CPU reduction. |
| `EXISTS` vs `JOIN` conversion where both sides are `NOT NULL` | Only rewritten when a `NOT NULL` constraint exists on the join key. | Cleaner plan, sometimes better CBO handling. |
| Redundant `DISTINCT` removal where an upstream key guarantees uniqueness | Provable via Iceberg partition key + filter. Only applied when provable. | Removes a whole aggregation stage. |

**Tempting but unsafe (advisory only, never rewritten):**

| Anti-Rewrite | Why Tempting | Why Unsafe |
|--------------|--------------|------------|
| Correlated subquery → join | Often 10× faster. | NULL handling, duplicate-row semantics, and multi-row mismatches. |
| `NOT IN` → `NOT EXISTS` | Simpler plan. | `NOT IN` returns empty if any RHS row is NULL; `NOT EXISTS` does not. |
| `COUNT(DISTINCT x)` → `approx_distinct(x)` | Fast. | Changes the answer. User must approve. |
| Removing `ORDER BY` in subqueries | Ordering is often unused downstream. | Some engines rely on subquery ordering; also nondeterministic results break tests. |
| Implicit cast simplification (`WHERE string_col = 42` → `WHERE string_col = '42'`) | Enables pushdown. | The semantics of cast comparison differ from string comparison in edge cases. |
| Pushing predicates through `LEFT JOIN` onto the right side | Faster. | Changes which rows are preserved when the right side has no match. |

---

## Recommendation Output — What Makes It Actionable

A recommendation is useless unless it answers:
1. **What is wrong?** (rule finding + evidence pointing at a specific plan operator)
2. **Why is it wrong?** (rule narrative referencing Trino / Iceberg mechanics)
3. **How do I fix it?** (concrete action: SQL rewrite, `SET SESSION`, `ANALYZE` command, `ALTER TABLE EXECUTE optimize`, bloom filter addition, etc.)
4. **What's the risk?** (risk level: NONE / LOW / MEDIUM / HIGH, with reasoning)
5. **How do I validate the fix?** (re-run EXPLAIN ANALYZE, diff with `compare_query_runs`, specific metrics to watch)
6. **What's the expected impact?** (quantified where possible: "scan bytes should drop from 4.2TB to ~12GB")
7. **How confident are we?** (HIGH / MEDIUM / LOW — function of rule determinism and evidence completeness)

Recommendations should be sortable by `priority = severity × impact × confidence`. The top 3 should be surfaced by default; the rest available on demand. This is what separates a recommendation engine from a linter.

---

## Before/After Comparison — What Metrics Matter

When comparing two `EXPLAIN ANALYZE` runs via `compare_query_runs`:

| Metric | Why It Matters | Target Delta |
|--------|----------------|--------------|
| Wall time | User-visible performance. | Must improve or match. |
| Total CPU time | Cluster cost. | Should improve; stable means fix didn't help. |
| Scanned bytes | I/O cost; often the biggest lever. | Should drop dramatically when pruning is fixed. |
| Split count | File open overhead. | Should drop after compaction fixes. |
| Peak memory (per stage) | Blowup risk. | Watch for regressions — rewrites can trade CPU for memory. |
| Stage CPU skew (p99/p50 ratio) | Skew detection. | Should decrease; if unchanged, skew is a data issue. |
| Exchange bytes (shuffle volume) | Network cost. | Distribution strategy changes show up here. |
| Output rows (per stage) | Correctness regression check. | Must be identical. Any divergence = correctness bug. |
| CBO estimate vs actual divergence | Stats freshness check. | Should converge after `ANALYZE`. |

Critical: **output rows must be identical after a rewrite**. If they diverge, the tool must loudly surface it as a potential correctness bug, not a performance win.

---

## MCP Resources — What LLMs Actually Need

Resources are read-only grounding content. They exist specifically to prevent the LLM client from hallucinating session property names, syntax, or best practices. Every resource should be:
- Curated (not generated)
- Version-pinned to a specific Trino + Iceberg version
- Written for an LLM consumer (structured, predictable headings, no ambiguous prose)

| Resource | Contents | Why It Matters |
|----------|----------|----------------|
| `trino_optimization_playbook` | Step-by-step playbooks for the top 10 rules: "Partition pruning failure," "Stale stats," "Join skew," etc. Each playbook is action → validation → rollback. | The LLM client cites this when explaining its recommendations. |
| `iceberg_best_practices` | Target file sizes, partition transform selection guide, MoR vs CoW tradeoffs, snapshot retention, delete-file cleanup, manifest maintenance. | Grounds Iceberg advice. |
| `trino_session_properties` | Full reference of session properties relevant to optimization: `join_reordering_strategy`, `join_distribution_type`, `join_max_broadcast_table_size`, `use_preferred_write_partitioning`, `task_concurrency`, `dynamic_filtering_wait_timeout`, etc. Each entry: name, type, default, what it does, when to change it. | LLMs hallucinate property names constantly. This is the single most valuable grounding resource. |
| `query_anti_patterns` | Catalog of `SELECT *`, function-wrapped predicates, correlated subqueries, `ORDER BY` without `LIMIT`, `DISTINCT` on high-cardinality, etc. Each with an explanation of why it's bad in Trino specifically. | Gives the LLM a named vocabulary for findings. |
| `iceberg_metadata_tables_reference` (add this) | Every `$`-prefixed metadata table, its columns, and what diagnostic each column enables. | Even experienced engineers don't remember the full schema of `$manifests` or `$files`. |
| `trino_explain_format_reference` (add this) | Guide to reading EXPLAIN JSON and EXPLAIN ANALYZE output: what fields mean, how to interpret distribution percentiles, how fragments map to stages. | The parser is internal, but the LLM sometimes needs to explain the output. |

PROJECT.md currently lists the first four. Adding `iceberg_metadata_tables_reference` and `trino_explain_format_reference` is recommended.

---

## MCP Prompts — Workflows That Justify Invocation

Prompts are what users type (or click). In Claude Code they appear as `/mcp__trino-optimizer__<name>`. Each prompt should correspond to a real workflow.

| Prompt | Workflow | When User Invokes |
|--------|----------|-------------------|
| `optimize_trino_query` | Paste SQL → full analysis → top 3 fixes | "My query is slow." Default entry point. |
| `iceberg_query_review` | Analyze query + audit every Iceberg table it touches (health, stats, files, deletes, snapshots) | "I inherited this dashboard and it's slow, help." Broader than `optimize_trino_query`. |
| `generate_optimization_report` | Produce a shareable Markdown report with findings, rewrites, validation plan | "I need to send this to my team / ticket / Slack." |
| `compare_before_after` (add this) | Paste two EXPLAIN ANALYZE outputs → structured delta report | "I applied a fix, did it work?" |
| `diagnose_partition_pruning` (add this) | Drill down specifically into why partition pruning isn't working | Specialized workflow for the most common cliff. |
| `diagnose_iceberg_table_health` (add this) | Just the table-health check, no query analysis | "Is this table healthy?" without needing a specific slow query. |

Prompts are cheap; more targeted prompts = better Claude Code UX because the user can pick the exact workflow.

---

## Claude Code Integration — What "Good" Looks Like

The user is in Claude Code, editing dbt models or ad-hoc SQL, and a query is slow. The experience should be:

1. User types `/mcp__trino-optimizer__optimize_trino_query` (or mentions "this query is slow" and Claude auto-picks the tool).
2. The server runs `EXPLAIN (FORMAT JSON)` + `EXPLAIN ANALYZE` (live mode) or accepts pasted EXPLAIN (offline mode).
3. The server parses the plan, runs the rule engine, and returns structured findings + recommendations.
4. Claude Code renders findings as a prioritized list with collapsible sections. Each finding references a specific plan operator and, where relevant, an MCP resource (e.g., `@trino_session_properties`).
5. For each recommendation, Claude shows: narrative, exact action (SQL / `SET SESSION`), risk level, validation steps.
6. User applies the fix, re-runs, optionally uses `/mcp__trino-optimizer__compare_before_after` for the delta report.

The key UX principles:
- **No context switching.** User never leaves Claude Code.
- **Resources appear via `@`.** Typing `@trino_session_properties` in any conversation pulls in the reference.
- **Output is structured JSON-rendered-as-Markdown.** Not free-form prose; Claude Code can navigate sections.
- **Actionable language.** "Run `ANALYZE TABLE orders`" — not "consider running ANALYZE on orders."
- **Exact evidence.** Every finding cites the specific fragment ID, operator, and metric value. No hand-waving.
- **Respects the agent loop.** The agent can invoke the server multiple times in one turn (fetch plan → detect issues → suggest fixes → rewrite SQL → validate), so each tool must be safe to call many times.

---

## Feature Dependencies

```
                          ┌──────────────────────────┐
                          │  Trino HTTP REST Client  │  (T22 auth)
                          └──────────┬───────────────┘
                                     │
               ┌─────────────────────┼──────────────────────┐
               │                     │                      │
          ┌────▼────┐          ┌─────▼─────┐          ┌─────▼──────┐
          │ Explain │          │ Iceberg   │          │ System     │
          │ Fetcher │          │ Metadata  │          │ Runtime    │
          │  (T2/T3)│          │ Fetcher   │          │ Fetcher    │
          └────┬────┘          │  (T4)     │          │            │
               │               └─────┬─────┘          └─────┬──────┘
               │                     │                      │
               └─────────────────────┼──────────────────────┘
                                     │
                          ┌──────────▼──────────┐
                          │   Plan Parser (T2)  │
                          │   Typed operator    │
                          │   tree + stats      │
                          └──────────┬──────────┘
                                     │
                          ┌──────────▼──────────┐
                          │  Rule Engine (T6)   │
                          │  R1–R16, I1–I11     │
                          └──────────┬──────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
      ┌───────▼────────┐    ┌────────▼────────┐    ┌────────▼────────┐
      │ Recommendation │    │  SQL Rewrite    │    │ Comparison      │
      │ Engine (T12/13)│    │  Engine (D6)    │    │ Engine (D3)     │
      └───────┬────────┘    └────────┬────────┘    └────────┬────────┘
              │                      │                      │
              └──────────────────────┼──────────────────────┘
                                     │
                          ┌──────────▼──────────┐
                          │ MCP Tool Layer (T1, │
                          │ T15, T16)           │
                          └──────────┬──────────┘
                                     │
                ┌────────────────────┼──────────────────────┐
                │                    │                      │
          ┌─────▼──────┐     ┌───────▼───────┐      ┌───────▼────────┐
          │ MCP Tools  │     │ MCP Resources │      │ MCP Prompts    │
          │ (T1, T16)  │     │ (T17/18/19)   │      │ (T20, D7)      │
          └────────────┘     └───────────────┘      └────────────────┘

 Live mode ──requires──> Trino HTTP REST Client
 Offline mode ──enhances──> Plan Parser (bypasses live fetch)
 Rule Engine ──requires──> Plan Parser
 SQL Rewrite Engine ──requires──> Plan Parser + Rule Engine + SQL Parser (sqlglot)
 Comparison Engine ──requires──> Two parsed plans (live mode OR two offline inputs)
 Iceberg Health Summary (D5) ──requires──> Iceberg Metadata Fetcher
 Partition-aware rewrites (D1) ──requires──> SQL Rewrite Engine + Iceberg Metadata Fetcher
 Session-property recommendations (D2) ──requires──> Rule Engine + trino_session_properties resource
 `iceberg_query_review` prompt (D7) ──requires──> Rule Engine + Iceberg Health Summary
 Cost-vs-actual divergence (D11) ──requires──> Both EXPLAIN and EXPLAIN ANALYZE for the same query
 Rule Engine determinism (D13) ──enhances──> every rule (enables fixture-based testing)
```

### Dependency Notes

- **Rule Engine requires Plan Parser:** every rule operates on the typed operator tree, not on raw JSON. Without a parser, rules become string matching.
- **SQL Rewrite Engine requires Rule Engine AND a SQL parser:** rewrites are keyed to specific findings (e.g., "partition pruning failure → partition-aligned predicate"). The SQL parser (`sqlglot`) is a separate dependency — it parses the query text, not the plan.
- **Comparison Engine requires two parsed plans:** trivially available in live mode, harder in offline mode because the user must paste two outputs. Design the tool to accept either.
- **Iceberg diagnostics (I1–I11) require the Iceberg Metadata Fetcher:** which in turn requires `SELECT` permission on each metadata table. Live mode only; offline mode cannot inspect metadata (call this out to users).
- **Session-property recommendations (D2) require the `trino_session_properties` resource:** otherwise the LLM will hallucinate property names. Treat the resource as part of the tool's correctness surface.
- **Cost-vs-actual divergence (D11) requires both EXPLAIN and EXPLAIN ANALYZE:** not just EXPLAIN ANALYZE. This means a two-fetch flow in live mode, or two paste inputs in offline mode.
- **Partition-transform-aware rewrite (D1) needs BOTH the SQL Rewrite Engine AND the Iceberg Metadata Fetcher:** because rewrites require the partition spec. This is the highest-leverage differentiator and the most cross-cutting dependency.
- **Conflicts:** there are no internal feature conflicts. The main "conflict" is between safety and convenience (A1–A3); PROJECT.md already resolves this in favor of safety.

---

## MVP Definition

The MVP is ruthlessly focused on: **"Paste a Trino + Iceberg query in Claude Code, get a trustworthy, grounded analysis and top 3 fixes with exact actions."** Everything else is post-MVP.

### Launch With (v1)

- [ ] **T1 `analyze_trino_query`** — single-entry pipeline. Without this, the tool has no front door.
- [ ] **T2 Plan parser** — typed operator tree from EXPLAIN JSON. Foundation for everything.
- [ ] **T3 EXPLAIN ANALYZE fetcher with distribution percentiles** — grounds rule evidence.
- [ ] **T4 Iceberg metadata fetcher** — `$snapshots`, `$files`, `$manifests`, `$partitions`. Iceberg rules depend on it.
- [ ] **T5 Live + Offline dual mode** — offline mode is the "zero activation cost" feature.
- [ ] **T6 Rule engine with R1, R2, R3, R4, R7, R9, R10, I1, I3, I6 (10 rules)** — the core deterministic rules covering the real-world cliffs.
- [ ] **T7 Partition pruning failure** — the #1 win.
- [ ] **T8 Dynamic filtering detection** — the #2 win.
- [ ] **T9 Stale-stats detection** — the #3 win.
- [ ] **T10 Small-files detection** — easy, high-visibility Iceberg win.
- [ ] **T11 Delete-file accumulation detection** — the Iceberg MoR pain point.
- [ ] **T12 Prioritized structured recommendations** — with reasoning, risk, validation.
- [ ] **T14 Read-only safety guarantee** — non-negotiable.
- [ ] **T15 Strict JSON schemas** — public API.
- [ ] **T16 `get_explain_json`, `get_explain_analyze`, `get_table_statistics`** — escape hatches.
- [ ] **T17 `trino_session_properties` resource** — grounds the LLM.
- [ ] **T18 `iceberg_best_practices` resource** — grounds the LLM.
- [ ] **T19 `query_anti_patterns` resource** — grounds the LLM.
- [ ] **T20 `optimize_trino_query` prompt** — front-door workflow.
- [ ] **T21 Structured query logging** — audit trail.
- [ ] **T22 Basic + JWT auth** — cluster access.
- [ ] **D1 Partition-transform-aware predicate analysis** — the #1 differentiator. This is THE reason users pick this tool. Worth the HIGH complexity.
- [ ] **D2 Session-property recommendations with exact `SET SESSION` statements** — makes advice actionable.
- [ ] **D5 Iceberg table health summary** — high leverage, moderate complexity.
- [ ] **D12 Claude Code-native workflow UX** — the "feels good" layer. Low complexity, high impact.
- [ ] **D13 Deterministic fixture replay** — required for testing, enables iteration speed.

### Add After Validation (v1.x)

Trigger: v1 ships, users confirm the core loop works, and we hear specific requests.

- [ ] **D3 `compare_query_runs`** — add once users are applying fixes and asking "did it work?" Likely the first post-MVP ask.
- [ ] **D6 Safe SQL rewrite engine** — rewrites are high value but HIGH complexity and correctness-critical. Better to ship advisory-only in v1 and add rewrites once the rule engine is battle-tested.
- [ ] **D4 CPU distribution skew detection** — easy to add once percentiles are parsed. Low cost, worth doing early in v1.x.
- [ ] **D8 Operator-level narrative** — once recommendations are validated, upgrade the prose quality.
- [ ] **D9 Projection pushdown effectiveness check** — simple rule once the parser is stable.
- [ ] **D11 Cost-vs-actual divergence reporter** — needs both EXPLAIN and EXPLAIN ANALYZE in a single flow; easier after the parser matures.
- [ ] **I7 Partition spec evolution awareness** — MEDIUM complexity, user hasn't asked for it yet.
- [ ] **I10 Sort order / clustering advisory** — MEDIUM complexity, more specialized users.
- [ ] **D7 `iceberg_query_review` prompt** — orchestration on top of existing tools, add once tools are stable.
- [ ] **`compare_before_after` prompt** — add with D3.
- [ ] **`iceberg_metadata_tables_reference` and `trino_explain_format_reference` resources** — useful additions; low cost.

### Future Consideration (v2+)

Trigger: product-market fit is confirmed; specific user requests justify the complexity.

- [ ] **D10 Bloom filter / sort order advisory** — niche but high-value when it hits.
- [ ] **D14 Partition spec evolution cross-snapshot analysis** — rare in the wild.
- [ ] **Multi-engine extensibility (Spark / Presto OSS)** — only if user demand is loud. PROJECT.md deliberately defers.
- [ ] **Non-Iceberg table formats (Delta, Hudi)** — only with demand.
- [ ] **Kerberos / mTLS auth** — only on user request.
- [ ] **AWS Glue / Nessie catalog support** — PROJECT.md deferred; revisit with demand.
- [ ] **Query lineage across multi-query sessions** — interesting but scope-creepy.
- [ ] **Historical trend analysis ("this query got 40% slower over 30 days")** — requires state; changes the product shape.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| T1 `analyze_trino_query` | HIGH | HIGH | P1 |
| T2 Plan parser | HIGH | HIGH | P1 |
| T3 EXPLAIN ANALYZE + percentiles | HIGH | HIGH | P1 |
| T4 Iceberg metadata fetcher | HIGH | MEDIUM | P1 |
| T5 Live + offline dual mode | HIGH | MEDIUM | P1 |
| T6 Rule engine (10 rules) | HIGH | HIGH | P1 |
| T7 Partition pruning rule | HIGH | MEDIUM | P1 |
| T8 Dynamic filtering rule | HIGH | MEDIUM | P1 |
| T9 Stale stats rule | HIGH | LOW | P1 |
| T10 Small-files rule | HIGH | LOW | P1 |
| T11 Delete-file rule | HIGH | MEDIUM | P1 |
| T12 Prioritized recommendations | HIGH | MEDIUM | P1 |
| T14 Read-only safety | HIGH | LOW | P1 |
| T15 JSON schemas | HIGH | LOW | P1 |
| T16 Standalone tool primitives | MEDIUM | LOW | P1 |
| T17 Session properties resource | HIGH | LOW | P1 |
| T18 Iceberg best practices resource | MEDIUM | LOW | P1 |
| T19 Anti-patterns resource | MEDIUM | LOW | P1 |
| T20 Optimize prompt | HIGH | LOW | P1 |
| T21 Structured logging | MEDIUM | LOW | P1 |
| T22 Basic + JWT auth | HIGH | LOW | P1 |
| D1 Partition-transform-aware rewrite | HIGH | HIGH | P1 |
| D2 Session-property exact recs | HIGH | MEDIUM | P1 |
| D5 Iceberg health summary | HIGH | MEDIUM | P1 |
| D12 Claude Code native UX | HIGH | LOW | P1 |
| D13 Fixture replay testing | HIGH | LOW | P1 |
| D3 compare_query_runs | HIGH | MEDIUM | P2 |
| D4 Skew detection | MEDIUM | LOW | P2 |
| D6 SQL rewrite engine (broader) | HIGH | HIGH | P2 |
| D8 Operator narrative | MEDIUM | MEDIUM | P2 |
| D9 Projection pushdown rule | MEDIUM | LOW | P2 |
| D11 Cost-vs-actual divergence | HIGH | MEDIUM | P2 |
| D7 iceberg_query_review prompt | MEDIUM | MEDIUM | P2 |
| D15 Manifest fragmentation rule | MEDIUM | LOW | P2 |
| D10 Bloom filter advisory | MEDIUM | MEDIUM | P3 |
| D14 Partition spec evolution rule | LOW | MEDIUM | P3 |
| I10 Sort order advisory | LOW | MEDIUM | P3 |
| Multi-engine / Delta / Hudi | LOW | HIGH | P3 (deferred) |

**Priority key:**
- **P1** — Must have for launch. Without any one of these, the tool fails to deliver on its core value.
- **P2** — Add in v1.x after real users confirm the core loop works.
- **P3** — Defer until product-market fit and explicit demand.

---

## Competitor Feature Analysis

| Feature | Trino Web UI | `EXPLAIN ANALYZE` + Slack | Internal dashboards | dbt-profiler / SQLMesh | **Our Approach** |
|---------|--------------|---------------------------|---------------------|------------------------|------------------|
| Parsed plan with typed operators | Partial (Stage Performance tab) | No (raw text) | Varies | No | **Yes, first-class — the foundation** |
| Per-rule deterministic findings | No | No (human judgment) | Sometimes | No | **Yes, 10+ rules with fixtures** |
| Iceberg metadata integration | No | Manual queries | Sometimes | No | **Yes, integrated into rules** |
| Partition transform awareness | No | Manual reasoning | No | No | **Yes, as a dedicated rule + rewrite** |
| Delete-file accumulation detection | No (`$partitions` gap, issue #28910) | Manual queries to `$files` | Rarely | No | **Yes, cross-reference `$files`** |
| Session property recommendations with exact statements | No | Verbal / runbook | No | No | **Yes, grounded in session-props resource** |
| Safe SQL rewrites with semantic proof | No | Manual | No | No | **Yes, from a fixed catalog of safe transforms** |
| Before/after comparison with deltas | Partial (two UI tabs) | Two terminals | Varies | No | **Yes, structured delta report** |
| Grounded LLM integration (MCP resources) | No | No | No | No | **Yes — this is the entire differentiator in the MCP era** |
| Read-only safety guarantee | N/A | Manual | Varies | N/A | **Yes, by construction** |
| Offline (no-cluster) mode | No | Yes (trivially) | No | No | **Yes, same tools without cluster** |
| Works inside the user's editor | No | No | No | No | **Yes, via Claude Code MCP** |

The competitive gap isn't the individual features — it's the combination: **deterministic rule engine + Iceberg-aware metadata + MCP-native UX + grounded LLM advice.** Nobody else has all four.

---

## Confidence Assessment

| Area | Confidence | Reason |
|------|------------|--------|
| Core optimization rules (R1–R16) | HIGH | Grounded in Trino official docs, Iceberg docs, and well-documented real-world pain points. CBO / dynamic filtering / partition pruning behavior is explicitly documented. |
| Iceberg-specific rules (I1–I11) | HIGH | Grounded in Trino Iceberg connector docs and known issues (`$partitions` delete-metric gap, issue #28910). |
| Safe vs unsafe rewrites | HIGH | The unsafe list is well-known SQL semantics (NULL handling, NOT IN, etc). The safe list is narrower by design. |
| MCP prompt / resource patterns | HIGH | Grounded in MCP docs; verified Claude Code surfaces `@resources` and `/mcp__server__prompt`. |
| Claude Code UX predictions | MEDIUM | Based on documented MCP integration behavior. Real UX quality depends on prompt design iteration. |
| Session property recommendations | MEDIUM | Specific property names verified (`join_reordering_strategy`, `join_distribution_type`, `join_max_broadcast_table_size`) but full mapping from rule → property combination is empirical and will evolve. |
| Quantitative thresholds (p50 < 16MB, p99/p50 > 5×, > 500 snapshots, split count > 10k) | MEDIUM | Drawn from community best practices (e.g., Iceberg 100MB target file size). Will need tuning with real data. Flagged for validation during implementation. |
| Bloom filter / sort order effectiveness | MEDIUM | Iceberg supports them; real-world effectiveness depends on data patterns. D10 deferred for this reason. |

---

## Gaps and Open Questions

These are areas where the research could not give a confident answer and that will need phase-specific follow-up:

1. **Exact thresholds for "unhealthy" Iceberg tables** — what counts as too many snapshots, too small a file, too many delete files? These depend on deployment. The tool should expose these as configurable knobs with sensible defaults drawn from Iceberg community guidance.
2. **How `$partitions` delete-file gap (Trino issue #28910) is actually resolved** — the current recommendation is to cross-reference `$files`, but the Trino team may ship a fix. Monitor and switch when available.
3. **Semantic-preservation proof strategy for partition-transform rewrites (D1)** — specifically for edge cases like timezone-shifted timestamps, `BETWEEN` with inclusive bounds crossing partition boundaries, and fractional-second precision. May need to be conservative (refuse to rewrite when proof is ambiguous).
4. **LLM prompt framing for "narrative per finding" (D8)** — this is partly an LLM-consumer UX question. Will need iteration with real queries.
5. **Offline-mode feature parity** — Iceberg metadata rules (I1–I11) require a live cluster; offline mode should clearly indicate which findings are unavailable and why.
6. **`sqlglot` coverage for Trino dialect** — the rewrite engine depends on a SQL parser that handles Trino-specific syntax. Coverage should be verified during implementation; fallback is to skip rewrites on unparseable statements rather than produce broken SQL.

---

## Sources

- Trino Iceberg connector documentation — https://trino.io/docs/current/connector/iceberg.html
- Trino EXPLAIN ANALYZE documentation — https://trino.io/docs/current/sql/explain-analyze.html
- Trino Cost-based optimizer documentation — https://trino.io/docs/current/optimizer/cost-based-optimizations.html
- Trino Optimizer properties — https://trino.io/docs/current/admin/properties-optimizer.html
- Trino Dynamic filtering documentation — https://trino.io/docs/current/admin/dynamic-filtering.html
- Trino CBO introduction blog — https://trino.io/blog/2019/07/04/cbo-introduction.html
- Trino episode 11 — Dynamic filtering and dynamic partition pruning — https://trino.io/episodes/11.html
- Trino blog — date predicates with Iceberg — https://trino.io/blog/2023/04/11/date-predicates.html
- Trino blog — Iceberg internals deep dive — https://trino.io/blog/2021/08/12/deep-dive-into-iceberg-internals.html
- Trino issue #28910 — `$partitions` metadata table missing delete file metrics — https://github.com/trinodb/trino/issues/28910
- Trino issue #12617 — Remove unused position and equality deletes when running Iceberg `optimize` — https://github.com/trinodb/trino/issues/12617
- Trino issue #19266 — Push down partition pruning when filter doesn't fully match partition transform — https://github.com/trinodb/trino/issues/19266
- Trino issue #24086 — Delete files not removed after running Iceberg maintenance ops — https://github.com/trinodb/trino/issues/24086
- Starburst blog — Iceberg partitioning and performance optimizations in Trino — https://www.starburst.io/blog/iceberg-partitioning-and-performance-optimizations-in-trino-partitioning/
- Starburst blog — The file explosion problem in Apache Iceberg — https://www.starburst.io/blog/apache-iceberg-files/
- Cloudera blog — Optimization Strategies for Iceberg Tables — https://www.cloudera.com/blog/technical/optimization-strategies-for-iceberg-tables.html
- Apache Iceberg Spark procedures documentation — https://iceberg.apache.org/docs/latest/spark-procedures/
- Celerdata — Trino Query Optimization Best Practices — https://celerdata.com/glossary/trino-query-optimization
- e6data — Trino Query Performance Optimization Guide — https://www.e6data.com/query-and-cost-optimization-hub/how-to-optimize-trino-query-performance
- Model Context Protocol official site — https://modelcontextprotocol.io/
- Claude Code MCP integration docs — https://code.claude.com/docs/en/mcp

---

*Feature research for: Trino + Iceberg query optimization MCP server*
*Researched: 2026-04-11*
