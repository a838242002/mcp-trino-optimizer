# Project Research Summary

**Project:** mcp-trino-optimizer
**Domain:** Python MCP server that analyzes and safely rewrites Trino SQL running against Apache Iceberg data lakes
**Researched:** 2026-04-11
**Confidence:** HIGH

> This is a distillation of `STACK.md`, `FEATURES.md`, `ARCHITECTURE.md`, and `PITFALLS.md`. Do not treat it as a replacement for those files — treat it as the shared index that requirements and roadmap both load. Each section tells you which source file to consult for depth.

---

## 1. Executive Summary

We are building a **Python 3.11+ MCP server** whose core is a **deterministic rule engine** that turns Trino `EXPLAIN (FORMAT JSON)` / `EXPLAIN ANALYZE` output plus Iceberg metadata into **prioritized, evidence-backed optimization recommendations** and, where provably safe, **semantics-preserving SQL rewrites**. The server exposes 8 MCP tools, 4+ resources, and 3+ prompts over both the **`stdio`** transport (Claude Code, Claude Desktop) and the modern **Streamable HTTP** transport (hosted). It ships as `uv` + `pyproject` + Docker, and is validated against a local docker-compose stack (Trino + Lakekeeper Iceberg REST catalog + PostgreSQL + MinIO).

The product exists because Trino+Iceberg performance cliffs (partition pruning failure, dynamic-filter silent fallback, stats staleness, small-files explosion, delete-file accumulation) are currently diagnosed by humans reading `EXPLAIN ANALYZE` by hand. An LLM left to its own devices hallucinates session property names, invents cost estimates, and proposes rewrites that silently change semantics. Our wedge is the opposite principle: **deterministic rules are the source of truth; the LLM only narrates findings it is handed.** Every recommendation must carry evidence pointing at a specific plan operator.

The dominant risks are **not performance or novelty** — they are **safety and correctness**. A single DML/DDL bypass turns this server into an LLM-driven exploit. A single "safe" rewrite that is wrong under three-valued logic destroys trust. A single stray `print()` on the stdio transport corrupts the JSON-RPC channel and bricks the Claude Code integration. These three classes of failure are all Phase 1 concerns and are called out explicitly below.

---

## 2. Cross-Cutting Decisions (Binding on Requirements & Roadmap)

These decisions are consistent across all four research files and should be treated as load-bearing inputs to requirements and the roadmap. They are **not** open for re-litigation at phase planning time.

| # | Decision | Source | Why it is load-bearing |
|---|---|---|---|
| 1 | Python 3.11+ (3.12 for Docker); `uv` + `hatchling` + `pyproject.toml` | STACK | Every other choice (MCP SDK, pydantic 2, sqlglot, modern typing) assumes this |
| 2 | Official `mcp` SDK >=1.27.0, <2, using `FastMCP` | STACK | Only supported path; v2 is breaking, pin the major |
| 3 | HTTP REST Trino via `trino-python-client` (no JDBC, no JVM) | STACK, PROJECT | Constitutional — PROJECT.md constraint |
| 4 | `sqlglot` (Trino dialect) is the only SQL parser/rewriter | STACK, PITFALLS | Rewrites need an AST; `sqlparse`/`sqlfluff` cannot produce one safely |
| 5 | Ports-and-adapters (hexagonal) architecture with `PlanSource` / `StatsSource` / `CatalogSource` protocols | ARCHITECTURE | The only way live mode and offline mode share one pipeline without branching |
| 6 | Deterministic rule engine is the core; all output is structured Pydantic models with JSON Schema | ARCHITECTURE, FEATURES, PITFALLS | Grounding story, auditability story, LLM-safety story all depend on this |
| 7 | Read-only by construction via a single `SqlClassifier` gate at the adapter layer, using `sqlglot` AST inspection | ARCHITECTURE, PITFALLS | The only safe implementation; regex gates are guaranteed-bypassable |
| 8 | stdio AND Streamable HTTP transports from day one; **not** legacy HTTP+SSE | STACK, PITFALLS | See §3 — this corrects PROJECT.md language |
| 9 | `structlog` → stderr only, with redaction allowlist for secrets | STACK, PITFALLS | stdio channel safety + credential hygiene |
| 10 | Local integration stack: **Trino 480 + Lakekeeper + PostgreSQL + MinIO** via docker-compose | STACK, ARCHITECTURE, PITFALLS | Lakekeeper has the cleanest docker story; decision is reversible but default |
| 11 | Rules produce `RuleFinding` (observations); a separate `recommend/` layer produces `Recommendation` (prioritized actions) | ARCHITECTURE, FEATURES | Rule code stays clean; priority/impact scoring is a second-pass concern |
| 12 | Rewrites use a tight whitelist; anything not provably semantics-preserving is advisory-only | FEATURES, PITFALLS | Correctness is non-negotiable; PROJECT.md already excludes unsafe rewrites |
| 13 | Every MCP tool I/O payload has strict JSON Schema with `maxLength`, `pattern`, `additionalProperties: false` | ARCHITECTURE, PITFALLS | Loose schemas are a prompt-injection lever |
| 14 | Every user-origin string (SQL, pasted EXPLAIN, Trino error messages) is wrapped in an `untrusted_content` envelope in tool output | PITFALLS | Indirect prompt injection defense — the LLM caller's input is our output |
| 15 | Primary comparison metric is **CPU time**, not wall time; N=5 paired-alternation runs; pinned Iceberg snapshot | PITFALLS, FEATURES | Benchmarks-that-lie is the single biggest trust hazard of the comparison engine |

---

## 3. Tensions & Corrections Across Research (Read Me First)

### 3.1 PROJECT.md says "HTTP/SSE" — STACK says Streamable HTTP. Resolve in favor of STACK.

PROJECT.md currently lists **"Both `stdio` and `HTTP/SSE` MCP transports from day one"**. STACK research establishes that:

- Legacy **HTTP+SSE** was deprecated in the MCP spec revision **2025-03-26**.
- The current transport is **Streamable HTTP** (single `/mcp` endpoint, bidirectional, resumable).
- The official `mcp` SDK (`>=1.27.0`) supports Streamable HTTP as `transport="streamable-http"`.
- Anthropic's Connectors Directory requires Streamable HTTP for new servers.

**Correction to apply in requirements:** wherever PROJECT.md says "HTTP/SSE", the intended meaning is **Streamable HTTP**. The stdio requirement is unchanged. Requirements doc should include a one-line note that this is a terminology update reflecting the 2025-03-26 spec; the user intent ("local + remote from day one") is preserved in full.

Both ARCHITECTURE.md (§9 transport table) and PITFALLS.md (Pitfall 7) assume the correction has been made. Any future doc that says "SSE" in the context of this project is wrong.

### 3.2 Local Iceberg REST catalog choice: Lakekeeper (default) vs Polaris/Nessie (alternatives)

- STACK recommends **Lakekeeper** for the docker-compose stack (Apache licence, Rust, simple compose, explicitly Trino-tested).
- PITFALLS (#14) flags that *any* choice here will drift from real prod catalogs (Polaris, Tabular, AWS Glue) and recommends an **Iceberg capability probe** at startup plus offline-mode as the "prod parity" story.
- ARCHITECTURE is catalog-agnostic — the `CatalogSource` port means the choice is reversible without touching the core.

**Resolution:** Default to Lakekeeper, ship the capability probe in Phase 2, position offline mode as the prod-validation workflow. Do not pretend integration tests prove prod compatibility.

### 3.3 No other material disagreements

STACK, FEATURES, ARCHITECTURE, and PITFALLS are consistent on:
- Deterministic rules first, LLM narrative second.
- The 8 tools / 4+ resources / 3+ prompts surface listed in PROJECT.md.
- The dual live-vs-offline execution model.
- The whitelist approach to rewrites.
- The critical role of the `$snapshots` / `$files` / `$manifests` / `$partitions` / `$history` Iceberg metadata tables.

---

## 4. Table Stakes — Consolidated Must-Haves

These are the features without which "an experienced Trino+Iceberg engineer closes the tab within five minutes" (FEATURES). Requirements must list every item here; roadmap must deliver every item before the v1 milestone. Each item is tagged with the FEATURES ID where applicable for traceability.

### 4.1 Server platform & safety (Phase 1)
- **stdio + Streamable HTTP transports** from day one, with stdio channel hygiene (stdout redirected, all logs to stderr, self-test tool).
- **Read-only enforcement by construction** — `sqlglot`-AST-based `SqlClassifier` at the adapter layer, allowlist of `SELECT`/`EXPLAIN`/`EXPLAIN ANALYZE`/`SHOW`/`DESCRIBE`/metadata-table queries, multi-statement rejected, `EXPLAIN ANALYZE <inner>` recursively validated. [T14]
- **Structured query logging** of every Trino statement with request_id, statement hash, duration, caller. Propagated to Trino as `X-Trino-Source` + `X-Trino-Client-Tags`. [T21]
- **Structured logging (structlog) to stderr only**, with redaction allowlist for `Authorization`, `X-Trino-Extra-Credentials`, and `credential.*`. [PITFALLS 15, 18]
- **Untrusted-content envelope** for any user-origin string in tool output. [PITFALLS 8]
- **Strict JSON Schemas** on every MCP tool — `maxLength` on strings (SQL: 100KB), `pattern` on identifiers, `additionalProperties: false`, bounded arrays. [T15, PITFALLS 13]
- **Packaging**: `uv tool install`, `uvx`, and `pip` install paths all tested; README has copy-pasteable Claude Code `mcpServers` JSON for each. [PITFALLS 16]
- **Configuration via `pydantic-settings`** (env > config file > default), secrets as `SecretStr`, JWT read per-request for rotation.
- **Docker image** (python:3.12-slim-bookworm, multi-stage, ~100MB, stdio default, HTTP via flag).

### 4.2 Trino adapter (Phase 2)
- **HTTP REST client via `trino-python-client`**, wrapped in `asyncio.to_thread` with a bounded thread pool — never called directly from an `async def` handler. [PITFALLS 11]
- **Auth**: no-auth, Basic, JWT bearer (token read per-request, never logged). [T22]
- **EXPLAIN (FORMAT JSON)**, **EXPLAIN ANALYZE (FORMAT JSON)**, **EXPLAIN (TYPE DISTRIBUTED)**. [T2, T3]
- **Cancel + timeout protection** — every query has a wall-clock budget; on cancel, explicit `DELETE /v1/query/{queryId}` sent to Trino so nothing orphans on the cluster. [PITFALLS 12]
- **Trino version probe** at adapter init (`SELECT node_version FROM system.runtime.nodes`), feeding a capability matrix that rules can query. [PITFALLS 19]
- **Iceberg capability probe** to record catalog type, Iceberg format version, metadata-table availability. [PITFALLS 14]
- **System + Iceberg metadata reads**: `system.runtime.*`, `system.metadata.*`, `$snapshots`, `$files`, `$manifests`, `$partitions`, `$history`, `$refs`. [T4]

### 4.3 Plan parser (Phase 3)
- **Typed tolerant tree**: pydantic models with `raw: dict[str, Any]` bags on every node so unknown/renamed fields survive Trino version drift. [PITFALLS 1]
- **Two distinct plan types**: `EstimatedPlan` (from `EXPLAIN`) and `ExecutedPlan` (from `EXPLAIN ANALYZE`). Rules declare which they support; engine filters by availability. [PITFALLS 2]
- **Iceberg operator awareness**: `IcebergTableScan`, split info, manifest reads. [T2]
- **Plan normalization**: collapse `ScanFilterProject` into `TableScan+filter+projection`, walk transparently through `Project` nodes when searching for scans. [PITFALLS 3]
- **Multi-version fixture corpus** (3+ Trino versions) that every rule must parse cleanly.

### 4.4 Rule engine with 10+ real rules (Phase 4)
Each rule is deterministic, fixture-tested in isolation, produces structured `RuleFinding` with severity + evidence + trace of matched operator IDs. Minimum set (non-negotiable, from FEATURES):
- **R1** missing/stale table statistics
- **R2** partition pruning failure (the #1 real-world cliff)
- **R3** predicate pushdown failure (function-wrapped column)
- **R4** dynamic filtering not applied (the #2 cliff)
- **R5** large build side / broadcast too big
- **R6** join order inversion
- **R7** CPU skew (p99/p50 > 5× on any stage)
- **R8** excessive exchange volume
- **R9** low-selectivity scan
- **I1** Iceberg small-files explosion (p50 < 16MB or split count > 10k)
- **I2** manifest fragmentation
- **I3/I4** position + equality delete file accumulation (with the Trino #28910 workaround — cross-reference `$files`)
- **I6** stale snapshot accumulation
- **I8** partition transform mismatch (feeds D1 rewrite)

Each rule must have three fixture classes: synthetic-minimum, realistic-from-compose, and negative-control. [PITFALLS 3]

### 4.5 Recommendation engine (Phase 5)
- **Priority scoring**: severity × impact × confidence. [T12]
- **Conflict resolution stage**: when two rules attach to the same operator with conflicting recommendations, the higher-confidence one wins and the other is demoted to "considered but rejected" with reasoning. [PITFALLS 17]
- **Audited recommendation templates keyed by rule ID** — free-form text never flows from user input to recommendation output. [PITFALLS 8]
- Every recommendation carries: reasoning, expected impact, risk level, validation steps, confidence. [T13]

### 4.6 Safe SQL rewrite engine (Phase 6)
Whitelist only:
- Projection pruning (`SELECT *` → enumerate used columns).
- Partition-transform-aligned predicate rewrite.
- Function-wrapped predicate unwrapping (`DATE(ts) = X` → half-open timestamp range).
- Early/partial aggregation session-property hints.
- `EXISTS ↔ JOIN` **only** when join key is provably `NOT NULL`.

Every rewrite ships with diff + unified preconditions checked + justification. `dangerous_rewrites: false` by default. Round-trip `COUNT + hash` validation on sample data when live. [T14, PITFALLS 4, FEATURES D6]

### 4.7 Comparison engine (Phase 7)
- Primary metric: **CPU time**. Wall time reported but marked "volatile — do not use for go/no-go". [PITFALLS 10]
- **N=5 runs, paired alternation, first run discarded, Iceberg snapshot pinned**; refuse comparison across a snapshot boundary.
- Output-rows delta must be zero; any divergence is surfaced as a potential correctness bug, not a win.
- Confidence classifier: HIGH / MEDIUM / LOW based on CPU-time delta vs MAD.

### 4.8 MCP surface (Phase 8)
- **8 tools**: `analyze_trino_query`, `get_explain_json`, `get_explain_analyze`, `get_table_statistics`, `detect_optimization_issues`, `suggest_optimizations`, `rewrite_sql`, `compare_query_runs`. [T1, T16]
- **Resources** (static markdown in package data, loaded via `importlib.resources`): `trino_optimization_playbook`, `iceberg_best_practices`, `trino_session_properties`, `query_anti_patterns`. [T17–T19]
- **Prompts** (jinja templates): `optimize_trino_query`, `iceberg_query_review`, `generate_optimization_report`. [T20]

### 4.9 Testing & validation (Phase 9, threaded through all phases)
- Unit tests with fixture plans for every rule.
- Snapshot tests (`syrupy`) on `AnalysisReport` JSON.
- Integration tests via `testcontainers[trino,minio]` + `DockerCompose` (opt-in via `@pytest.mark.integration`).
- Prompt-injection adversarial corpus.
- stdio-cleanliness test: send `initialize`, assert stdout is valid JSON-RPC only.
- Install-matrix CI: `{3.11, 3.12, 3.13} × {macOS, Linux, Windows}`.

---

## 5. Differentiators — What to Prioritize vs Defer

From FEATURES §Differentiators (D1–D15), these are the features that justify the tool's existence over `EXPLAIN ANALYZE` + Slack + runbooks.

### 5.1 v1 differentiators — ship in the roadmap (high ROI, moderate complexity)

| # | Differentiator | Why ship v1 | Phase |
|---|---|---|---|
| **D1** | Partition-transform-aware predicate analysis + rewrite | The single biggest real-world win. Directly addresses the #1 Trino+Iceberg cliff. | 4 (detect) + 6 (rewrite) |
| **D2** | Session-property recommendations with exact `SET SESSION` statements | Grounds the LLM; "actionable not advisory"; needs only the `trino_session_properties` resource + rule→property mapping. | 5 |
| **D3** | Before/after comparison with structured delta (implements `compare_query_runs`) | Closes the feedback loop; required by PROJECT.md table stakes. | 7 |
| **D4** | Skew detection via CPU/wall p99/p50 ratio | Trivial to compute, high value; Trino already exposes the percentiles. | 4 |
| **D5** | Iceberg table health summary (snapshot count, small-file ratio, delete ratio, spec evolution, last compaction) | Diagnostic leverage per table is huge; piggybacks on Phase 2 metadata reads. | 5 |
| **D6** | Safe rewrites with semantic-preservation proof + diff view | This is the trust mechanism for the rewrite engine. | 6 |
| **D8** | Operator-level bottleneck ranking with a grounded natural-language narrative per operator | Templated from structured findings; LLM clients render this directly. | 5 |
| **D9** | Projection pushdown effectiveness (`SELECT *` impact quantified) | Trivial; almost always a win on Iceberg. | 4 + 6 |
| **D11** | Cost-vs-actual divergence reporter (CBO estimate vs ANALYZE actuals > 5× on any operator) | Smoking gun for stale stats; feeds R1. | 4 |
| **D12** | Claude Code–native UX (prompt framing, resource `@`-autocomplete, rendered finding structure) | Low complexity, huge UX lift; it's the reason to be an MCP server. | 8 |
| **D13** | Deterministic fixture replay for rule validation | Makes bug reports actionable; enables the "add fixture from user report" feedback loop. | 4 (infra) |

### 5.2 Defer to v1.1 / v2 (valuable but not needed for launch)

| # | Differentiator | Why defer | Revisit when |
|---|---|---|---|
| **D7** | `iceberg_query_review` "audit every touched table" prompt | Orchestrates multiple existing tools; nice polish but not load-bearing. | After v1 ships, once the primitives exist. |
| **D10** | Bloom filter / sort order / file-level stats advisory | Rarely-used Iceberg feature; needs cardinality analysis to be useful. | After user feedback confirms demand. |
| **D14** | Partition spec evolution awareness | Important for a minority of tables; complicates the `$files` reader. | When a user reports misleading diagnostics on evolved tables. |
| **D15** | Manifest fragmentation dedicated rule | Covered by a cruder "manifest count" check in I2; dedicated analysis can wait. | After the base I2 rule exists. |

### 5.3 Never ship (anti-features consolidated from FEATURES A1–A14)

- Unsafe semantic-changing rewrites (PROJECT.md + A1 + PITFALLS 4).
- Arbitrary SELECT execution for result preview (A2).
- DDL/DML generation that *executes* compaction; we *recommend* it (A3).
- Multi-engine support, non-Iceberg table formats, CBO replacement (A4–A6).
- A query editor UI (A7).
- Background scheduling / watch mode (A8).
- Query text storage beyond session (A9).
- LLM-authored rewrites (A10).
- Kerberos / mTLS (A11) — deferred explicitly.
- Generic "query advisor" framing (A12).
- Trino event-listener plugin (A13).
- Cross-session caching (A14).

---

## 6. Critical Safety Pitfalls — Must Be Addressed in Phase 1

These are the pitfalls that destroy the product if missed. They are **all Phase 1 or Phase 2 concerns** regardless of how the roadmap is sliced, because a later fix is either a rewrite (architecture) or a trust-destroying incident (safety). Every one of these must be called out as a Phase 1 acceptance criterion.

### 6.1 MUST land in Phase 1 (skeleton)

1. **stdio stdout discipline** (PITFALLS 7) — before any import that might print, `sys.stdout = sys.stderr`, then the MCP SDK writes to a dedicated pristine fd. structlog pinned to stderr. `warnings` captured into logging. CI test sends `initialize` and asserts stdout is valid JSON-RPC only. **This is the single most common MCP debugging issue; a day-one miss means Claude Code integration is silently broken.**
2. **Untrusted-content envelope in tool outputs** (PITFALLS 8) — adopt the typed `source: untrusted` field convention from the very first tool schema. Retrofitting this is a full schema bump later.
3. **Structured logging with redaction allowlist** (PITFALLS 15, 18) — `Authorization`, `X-Trino-Extra-Credentials`, `credential.*` hard-redacted; every log line has `request_id`, `tool_name`, `git_sha`, `package_version`, ISO8601 UTC timestamp. Unit test: attempting to log a dict with `authorization` key produces `[REDACTED]`.
4. **Request-scope `contextvars.ContextVar` for `request_id`** — so every downstream log line correlates without plumbing.
5. **Install path matrix + Claude Code config docs** (PITFALLS 16) — `uv tool install`, `uvx`, `pip` all tested; README has copy-pasteable `mcpServers` JSON.
6. **Cross-platform hygiene** (PITFALLS 20) — `pathlib.Path` everywhere, `encoding="utf-8"` on every `open`, `.gitattributes` LF on fixtures.

### 6.2 MUST land in Phase 2 (Trino adapter)

7. **AST-based read-only SQL gate via `sqlglot`** (PITFALLS 9, ARCHITECTURE §10) — allowlist of statement types, multi-statement rejected, `EXPLAIN ANALYZE` recursively validated. Located in `safety/classifier.py`; called from the first line of every Trino client method; unit test asserts the invariant by introspecting all public methods of the adapter.
8. **`asyncio.to_thread` wrapper around the sync `trino-python-client`** (PITFALLS 11) — bounded thread pool, default 4, config-driven.
9. **Cancel + timeout propagation** (PITFALLS 12) — every query has a wall-clock budget; on cancel/timeout the adapter sends `DELETE /v1/query/{queryId}` and awaits confirmation. No orphaned queries on the cluster.
10. **Trino version probe + capability matrix** (PITFALLS 19) — capability-gated rules report "skipped — requires Trino ≥ Y" as a structured finding, never as an exception.
11. **`EXPLAIN ANALYZE` cost gate** (PITFALLS 2, 8) — pre-flight `EXPLAIN` for CBO estimate, refuse ANALYZE if `cpuCost`/`outputBytes` above budget, enforce timeout.

### 6.3 Other critical pitfalls by phase

- **Phase 3 (parser)**: tolerant typed tree with `raw` bags; two distinct plan classes for estimated vs executed; multi-version fixture corpus (PITFALLS 1, 2).
- **Phase 4 (rules)**: three fixture classes per rule (synthetic/realistic/negative); evidence contract with declared fields; data-driven thresholds with citations; plan normalization before rule matching (PITFALLS 3, 5, 6).
- **Phase 5 (recommender)**: conflict-resolution stage (PITFALLS 17).
- **Phase 6 (rewrite)**: whitelist + preconditions + `NOT NULL` verification + round-trip validation; never touch correlated subqueries, `NOT IN`, `LEFT JOIN` predicates, `CASE`, window frames, `UNNEST`, UDFs, `WITH RECURSIVE` (PITFALLS 4).
- **Phase 7 (compare)**: CPU time primary, N=5 paired alternation, snapshot-pinned, correctness-delta check (PITFALLS 10).
- **Phase 8 (MCP surface)**: strict schemas with `maxLength`/`pattern`/`additionalProperties: false`; static tool descriptions loaded at startup; long-running job pattern for `analyze_trino_query` (PITFALLS 8, 12, 13).
- **Phase 9 (integration)**: Iceberg capability probe, prompt-injection corpus, MinIO credentials via `.env` with random defaults, `127.0.0.1`-bind in compose, gitleaks in CI (PITFALLS 14, 15).

---

## 7. Phase Ordering — Reconciled Recommendation

Two explicit orderings exist in the research files:

- **ARCHITECTURE §13** suggests **5 phases** reflecting the topological build order of the codebase (foundation → adapters → rules → higher engines → MCP surface).
- **PITFALLS** organizes itself around a **9-phase mapping** (skeleton → Trino adapter → parser → rules → recommender → rewrite → compare → MCP surface → integration) that matches the seven functional-areas-plus-two-wrappers in PROJECT.md.

These do not conflict — ARCHITECTURE's 5 phases collapse **Rules + Recommender + Rewrite + Compare** into one big build-out, and ARCHITECTURE's "Phase 1 Foundation" is a superset of PITFALLS's "Phase 1 Skeleton" plus the parser.

**Recommended reconciliation:** follow PITFALLS's 9-phase structure because (a) it aligns with the natural "ship one functional area at a time" cadence, (b) it yields clearer acceptance criteria per phase, (c) each phase produces something demonstrable. Within each phase, use ARCHITECTURE's topological order (§13) as the internal build sequence.

### 7.1 Proposed phases

**Phase 1 — Skeleton & Safety Foundation**
- *Rationale:* Nothing else can land safely without stdio discipline, logging, schemas, packaging, cross-platform hygiene, and the shared `FastMCP` app object. Every critical pitfall from §6.1 lives here.
- *Delivers:* An MCP server that starts on stdio and Streamable HTTP, answers `initialize`, exposes a `mcp_selftest` tool, and ships via `uv tool install` / `uvx` / `pip` / Docker. No Trino connection yet.
- *Uses:* Python 3.11+, `mcp[cli]`, `pydantic`, `pydantic-settings`, `structlog`, `orjson`, `typer`, `uvicorn`, `hatchling`, `uv`, `ruff`, `mypy`.
- *Delivers domain models:* `TrinoQuery`, `ExplainPlan` (skeleton), `RuleFinding`, `Recommendation`, `RewriteResult`, `ComparisonReport` (all pydantic).
- *Avoids pitfalls:* 7 (stdio), 8 (untrusted envelope convention), 15 (credential logging), 16 (install paths), 18 (observability gaps), 20 (cross-platform).
- *Research flag:* **No deeper research needed.** Well-documented territory. Proceed directly to implementation.

**Phase 2 — Trino Adapter + Read-Only Gate**
- *Rationale:* Everything else depends on a safe, cancellable, async-friendly Trino client. The SQL AST gate lives here, not at the tool layer, so that *no code path* to Trino exists without passing it. Offline mode's `OfflinePlanSource` is also wired here because both modes share `PlanSource`/`StatsSource`/`CatalogSource` ports.
- *Delivers:* `adapters/trino/` with client, auth (none/basic/JWT), live + offline plan sources, live stats source, live catalog source, Iceberg metadata reader, SQL classifier, query logger. Trino version probe + capability matrix. Cancel/timeout propagation. Iceberg REST capability probe.
- *Uses:* `trino-python-client`, `anyio`, `httpx`, `sqlglot` (classifier only).
- *Implements architecture components:* `ports/*`, `adapters/trino/*`, `adapters/offline/*`, `adapters/iceberg/*`, `safety/*`, `observability/*`.
- *Avoids pitfalls:* 2 (two plan types at fetch time), 5 (stats freshness via metadata tables), 9 (AST gate), 11 (thread wrapper), 12 (cancellation), 14 (capability probe), 19 (version probe).
- *Research flag:* **Needs targeted research** on: exact `trino-python-client` cancellation mechanics (`DELETE /v1/query/{queryId}` via the sync client), Lakekeeper `/v1/config` endpoint shape, JWT refresh hooks. Recommend `/gsd-research-phase` before implementation.

**Phase 3 — Plan Parser & Normalizer**
- *Rationale:* Rules are dead code without a typed plan. Tolerant tree + two distinct plan classes + multi-version fixture corpus must be in place before any rule is written.
- *Delivers:* `plan/parser.py`, `plan/normalizer.py`, `plan/metrics.py`, `plan/iceberg_ops.py`; `EstimatedPlan` and `ExecutedPlan` types; `schema_drift_warnings` surface; fixture corpus from at least 3 Trino versions.
- *Uses:* `pydantic`, `orjson`, `syrupy` (for snapshot tests).
- *Avoids pitfalls:* 1 (tolerant typed tree), 2 (two plan types), 3 (plan normalization before rules see them).
- *Research flag:* **Needs research** — the undocumented EXPLAIN JSON shape is the biggest unknown in the project. Capture fixtures from Trino 429, an LTS (e.g., 458), and 480+ against the compose stack. Recommend `/gsd-research-phase` + a fixture-capture spike before implementation.

**Phase 4 — Rule Engine + 10+ Rules**
- *Rationale:* The deterministic core of the product. Every table-stakes rule (R1–R9, I1–I3, I6, I8) lands here, fixture-tested in isolation.
- *Delivers:* `rules/base.py`, `rules/registry.py`, `rules/engine.py` (multi-pass with prefetch + isolated failures), all minimum rules with synthetic + realistic + negative fixtures, capability gating via the matrix from Phase 2.
- *Uses:* `pydantic`, `syrupy`.
- *Implements features:* T6, T7, T8, T9, T10, T11 (table stakes); D4, D9, D11 (differentiators).
- *Avoids pitfalls:* 3 (three fixture classes + evidence contract + data-driven thresholds), 5 (staleness rule using metadata tables, not just SHOW STATS), 6 (partition pruning diagnosis via input_rows vs total, not predicate text), 19 (capability gating).
- *Research flag:* **Needs targeted research** on partition-transform semantics per Trino version (Trino issue #19266) and Iceberg delete-file metrics workaround (Trino issue #28910). Recommend `/gsd-research-phase`.

**Phase 5 — Recommendation Engine**
- *Rationale:* Findings are raw observations; recommendations are the actionable layer. Priority scoring and conflict resolution both live here.
- *Delivers:* `recommend/scorer.py`, `recommend/prioritizer.py`, `recommend/builder.py`, conflict-resolution stage, audited rule-ID-keyed templates.
- *Implements features:* T12, T13; D2 (session properties), D5 (table health summary), D8 (operator-level narrative).
- *Avoids pitfalls:* 8 (templated recommendations), 17 (conflict resolution).
- *Research flag:* No deeper research needed — straightforward Python once Phase 4 is solid.

**Phase 6 — Safe SQL Rewrite Engine**
- *Rationale:* The highest-correctness-risk module. Must follow Phase 4 so rules can drive rewrites (e.g., R2 → partition-aligned predicate rewrite).
- *Delivers:* `rewrite/engine.py`, `rewrite/sql_parser.py`, `rewrite/diff.py`, and one sub-module per whitelisted transform (projection pruning, partition-aligned predicate, function-unwrap, early aggregation hint, EXISTS↔JOIN with NOT NULL gate). Each transform ships with preconditions check, diff, justification, "not verified" disclaimer. `dangerous_rewrites: false` default.
- *Uses:* `sqlglot` (Trino dialect), `rich` (diff rendering).
- *Implements features:* D1 (partition-transform-aware rewrite), D6 (proof + diff view).
- *Avoids pitfalls:* 4 — the entire pitfall catalogue of "safe" rewrites that aren't.
- *Research flag:* **Needs research** on `sqlglot` Trino dialect's expression-walking API, and on property-based test patterns for rewrite equivalence (hypothesis). Recommend `/gsd-research-phase`.

**Phase 7 — Comparison Engine**
- *Rationale:* Closes the feedback loop. Must follow Phase 3 (plan parser) and Phase 6 (rewrites to compare). Independently implementable after that.
- *Delivers:* `compare/engine.py`, paired-alternation runner, snapshot pinning, CPU-time primary metric, correctness-delta check (output rows), HIGH/MEDIUM/LOW confidence classifier.
- *Implements features:* D3.
- *Avoids pitfalls:* 10 (benchmarks that lie) — the whole raison d'être of this phase's methodology.
- *Research flag:* No further research; methodology is already specified in PITFALLS §10.

**Phase 8 — MCP Surface (Tools + Resources + Prompts + Services)**
- *Rationale:* All 8 tools, 4+ resources, 3+ prompts wired onto `FastMCP` via the service layer. Services compose Phases 2–7 into the tool handlers.
- *Delivers:* `services/analysis.py`, `services/rewrite.py`, `services/compare.py`, `services/metadata.py`; `mcp/tools/*.py` (8 thin handlers); `mcp/resources/content/*.md` (4 curated markdown files); `mcp/prompts/content/*.jinja` (3 templates); `mcp/server.py` registering everything on `FastMCP`; `app.py` shared by both transports.
- *Uses:* `FastMCP`, `jinja2`, `importlib.resources`.
- *Implements features:* T1, T15, T16, T17–T20; D12 (Claude Code UX).
- *Avoids pitfalls:* 8 (static tool descriptions; untrusted envelope enforced here), 12 (long-running job pattern for `analyze_trino_query`), 13 (strict schemas).
- *Research flag:* No deeper research needed; the FastMCP patterns are well-documented.

**Phase 9 — Docker-Compose Integration Stack + CI**
- *Rationale:* This is the validation phase. Trino + Lakekeeper + Postgres + MinIO + mc, plus the realistic-fixture capture pass, plus the adversarial corpus, plus CI.
- *Delivers:* `docker-compose.yml`, `.env.example` with random defaults, `testcontainers`-driven integration tests, realistic plan fixtures captured for Phase 4 rules, prompt-injection adversarial corpus, `{3.11,3.12,3.13} × {linux,mac,win}` install matrix, gitleaks in CI.
- *Uses:* `testcontainers[trino,minio]`, `pytest`, `DockerCompose`, Lakekeeper, MinIO, PostgreSQL 16, Trino 480.
- *Avoids pitfalls:* 14 (catalog drift awareness), 15 (compose credential hygiene), 19 (version matrix in CI).
- *Research flag:* **Needs research** on Lakekeeper compose configuration, MinIO bucket/policy bootstrap, and `testcontainers` `DockerCompose` wait strategies. Recommend `/gsd-research-phase`.

### 7.2 Phases that need `/gsd-research-phase` before planning

Listed here for the roadmapper:

| Phase | Research need | Why |
|---|---|---|
| 2 | Trino client cancellation, JWT refresh, Lakekeeper config API | Exact API shapes beyond official docs |
| 3 | Multi-version EXPLAIN JSON fixture capture | Undocumented contract — the highest single risk in the project |
| 4 | Partition-transform semantics, Iceberg delete-file workarounds | Known Trino issues, version-sensitive |
| 6 | `sqlglot` expression API + property-based equivalence testing | High-correctness-risk module |
| 9 | Lakekeeper compose, MinIO bootstrap, testcontainers wait strategies | Operational detail not covered in existing sources |

Phases **1, 5, 7, 8** can proceed without additional research — the patterns are well-established and the existing research files are sufficient.

---

## 8. Open Questions (Resolve Before or Early in Roadmap)

None of the four research files resolved the following. Each should be explicitly addressed during roadmap creation or deferred with a note.

1. **Minimum supported Trino version.** PITFALLS suggests "Trino 429+ (early 2024)". STACK points at "400–480+". Pick one number and enforce it at startup. Recommendation: **429** (gives 15+ months back-compat, matches PITFALLS).
2. **`EXPLAIN ANALYZE` cost budget default.** PITFALLS says "use a pre-flight EXPLAIN cost estimate to gate ANALYZE" but does not specify the default budget. Need a number (e.g., `cpuCost` < 1e12, `outputBytes` < 10GB) that ships by default.
3. **Long-running job pattern cutover.** PITFALLS 12 recommends `start_analyze_job` / `poll_analyze_job` / `get_analyze_result` when budgets exceed MCP client timeout. Open: do we ship this in v1 or ship partial-results-on-timeout first? Recommendation: **v1 ships partial-results + cancel; job pattern is v1.1 feature**.
4. **Streamable HTTP auth.** STACK/ARCHITECTURE say "bearer token required, default-closed CORS, bind 127.0.0.1". Open: is the bearer token a static config value, or do we want JWT verification? Recommendation: **static config token for v1**; document as "put a reverse proxy in front for real deployments".
5. **Max concurrent Trino queries per MCP process.** PITFALLS says "semaphore-bounded, default 4". Confirm as the default.
6. **Lakekeeper vs Polaris default.** STACK picks Lakekeeper, notes it as MEDIUM confidence and reversible. Decision stands, but worth flagging to the user that Polaris is the Apache-incubating "official" answer.
7. **Rewrite engine: which transforms ship in Phase 6 v1 vs v1.1?** FEATURES lists 6 high-leverage safe rewrites; PITFALLS stresses "tightest possible whitelist initially". Recommendation: **ship projection pruning + function-wrapped predicate unwrap in Phase 6**; defer partition-aligned rewrite (needs D1 integration), EXISTS↔JOIN (needs schema introspection for NOT NULL), and DISTINCT removal to a follow-up.
8. **Prompt-injection corpus source.** Phase 9 assumes one exists. Open: do we curate it ourselves or start from an existing catalogue (OWASP LLM Top 10, promptfoo tests)?
9. **`mcp_selftest` tool scope.** Mentioned in PITFALLS 7 as a stdio-cleanliness probe. Open: is this a persistent tool we ship, or test-only tooling? Recommendation: **ship persistent, return version + transport + capabilities + round-trip payload echo; it's the first tool to prove protocol health**.
10. **Iceberg metadata reference resource.** FEATURES §Resources recommends adding `iceberg_metadata_tables_reference` and `trino_explain_format_reference` beyond the four PROJECT.md resources. Open: include in v1 or defer?

---

## 9. Confidence Assessment

| Area | Confidence | Notes |
|---|---|---|
| Stack | **HIGH** | Versions verified against PyPI on research date; all ecosystem choices backed by first-party sources. Single MEDIUM item: Lakekeeper-over-Polaris (reversible). |
| Features | **HIGH** | Rules grounded in Trino/Iceberg docs and well-documented community pain points. Differentiators grounded in the PROJECT.md goals and cross-referenced to specific Trino/Iceberg mechanisms. |
| Architecture | **HIGH** on structure and ports/adapters; **MEDIUM** on rule engine internals (multi-pass orchestration, evidence contract) which are project-specific inventions that will be validated in Phase 4 implementation. |
| Pitfalls | **HIGH** on Trino/Iceberg pitfalls (backed by specific Trino issues, Iceberg docs, community posts) and Python/asyncio/packaging traps. **MEDIUM** on MCP-specific safety (rapidly evolving spec; current as of 2025-03-26 revision). |

**Overall confidence: HIGH.** The project's unknowns are concentrated in two places: (a) the undocumented EXPLAIN JSON contract (mitigated by the multi-version fixture strategy in Phase 3) and (b) rewrite-engine correctness (mitigated by the tight whitelist + preconditions + property tests in Phase 6). Both are called out as research-needed phases in §7.2.

### 9.1 Gaps identified (carry into planning)

- **EXPLAIN JSON schema drift across Trino versions** is assumed to be tractable but not yet proven. Phase 3 research should produce the fixture corpus as a concrete deliverable before Phase 4 starts.
- **Lakekeeper compose stability** has not been independently verified for the specific `trinodb/trino:480` + Lakekeeper combination. Phase 9 research must validate before CI depends on it.
- **Property-based testing for rewrites** is recommended but the specific tooling (hypothesis? custom fixtures?) is not decided. Phase 6 research should produce a decision.
- **MCP prompt-injection adversarial corpus**: we have the threat model but no curated test corpus yet. Phase 9 must source or author one.
- **Trino cancellation semantics via `trino-python-client`** — the client is sync, cancellation is by sending `DELETE /v1/query/{queryId}`, but the exact reliable way to obtain the query ID under concurrency has not been verified. Phase 2 research should confirm.

---

## 10. Reader's Roadmap — Which File to Open for Which Question

| If you need to decide… | Open |
|---|---|
| Which library, which version, which packaging path | **STACK.md** (Recommended Stack table, Alternatives Considered, pyproject skeleton) |
| Which features are table stakes vs differentiators vs anti-features | **FEATURES.md** §Feature Landscape (T1–T22, D1–D15, A1–A14) |
| Which optimization rules must ship in Phase 4 | **FEATURES.md** §The Optimization Rules That Actually Matter (R1–R16, I1–I11) |
| Which rewrites are safe vs advisory-only | **FEATURES.md** §Safe Rewrites table + **PITFALLS.md** §Pitfall 4 table |
| What the output of the recommendation engine must contain | **FEATURES.md** §Recommendation Output |
| What the comparison engine must measure and how | **FEATURES.md** §Before/After Comparison + **PITFALLS.md** §Pitfall 10 |
| How the codebase is sliced (packages, modules, files) | **ARCHITECTURE.md** §3 Concrete directory layout |
| What the domain types look like | **ARCHITECTURE.md** §4 Data Model |
| How rules are registered, ordered, and executed | **ARCHITECTURE.md** §5 Rule Engine Design |
| How live mode and offline mode share one pipeline | **ARCHITECTURE.md** §6 Dual-Mode Execution |
| How stdio and Streamable HTTP share one `FastMCP` app | **ARCHITECTURE.md** §9 + **STACK.md** §Transport Architecture |
| Where the read-only SQL gate lives and how it's enforced | **ARCHITECTURE.md** §10 Safety Enforcement + **PITFALLS.md** §Pitfall 9 |
| What must NOT go in stdout, why, and how to prevent it | **PITFALLS.md** §Pitfall 7 |
| Why "safe rewrites" isn't a free lunch | **PITFALLS.md** §Pitfall 4 (entire section) |
| Why rules that work on fixtures miss real problems | **PITFALLS.md** §Pitfall 3 |
| Why `EXPLAIN` and `EXPLAIN ANALYZE` need distinct plan types | **PITFALLS.md** §Pitfall 2 |
| Why partition pruning "working" can still be wrong | **PITFALLS.md** §Pitfall 6 |
| How to defend against prompt injection via SQL and plan content | **PITFALLS.md** §Pitfall 8 |
| What to log, what never to log, and how to correlate requests | **PITFALLS.md** §Pitfall 18 + §Pitfall 15 |
| Which install paths to test in CI | **PITFALLS.md** §Pitfall 16 |
| Which Trino versions to support and how to probe capability | **PITFALLS.md** §Pitfall 19 + **ARCHITECTURE.md** §12 |
| The recommended topological build order (within a phase) | **ARCHITECTURE.md** §13 |

---

## 11. Sources (Aggregated from Research Files)

### Primary (HIGH confidence, official)
- `modelcontextprotocol/python-sdk` on GitHub — FastMCP patterns, transports
- MCP Transports Spec 2025-03-26 — Streamable HTTP / SSE deprecation
- `mcp` on PyPI — v1.27.0 (2026-04-02)
- `trino-python-client` on GitHub + `trino` on PyPI — v0.337.0
- `sqlglot` docs — Trino dialect
- Trino 480 docs — Iceberg connector, JWT auth, EXPLAIN family
- Apache Iceberg spec + Trino metadata-table reference
- Lakekeeper on GitHub
- `pydantic-settings`, `ruff`, `testcontainers`, `syrupy` on PyPI
- Trino issues cited in PITFALLS: #19266 (partition pruning transforms), #28910 (`$partitions` delete metrics), #12323 (partition spec evolution), trino-python-client #185 (asyncio)

### Secondary (MEDIUM confidence, analysis)
- Microsoft DevBlog: Protecting against indirect prompt injection in MCP
- Snyk Labs: Prompt injection in MCP
- Trino blog: Just the right time date predicates with Iceberg
- Jian Liao: Debug MCP stdio transport
- fka.dev: Why MCP deprecated SSE
- e6data: Iceberg Catalogs 2025
- pydevtools: mypy vs pyright vs ty

### Internal (this repo)
- `/Users/allen/repo/mcp-trino-optimizer/.planning/PROJECT.md`
- `/Users/allen/repo/mcp-trino-optimizer/.planning/research/STACK.md`
- `/Users/allen/repo/mcp-trino-optimizer/.planning/research/FEATURES.md`
- `/Users/allen/repo/mcp-trino-optimizer/.planning/research/ARCHITECTURE.md`
- `/Users/allen/repo/mcp-trino-optimizer/.planning/research/PITFALLS.md`
