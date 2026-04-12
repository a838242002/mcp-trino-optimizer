---
phase: 02-trino-adapter-read-only-gate
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/mcp_trino_optimizer/adapters/__init__.py
  - src/mcp_trino_optimizer/adapters/trino/__init__.py
  - src/mcp_trino_optimizer/adapters/trino/classifier.py
  - src/mcp_trino_optimizer/adapters/trino/errors.py
  - src/mcp_trino_optimizer/adapters/trino/auth.py
  - src/mcp_trino_optimizer/settings.py
  - src/mcp_trino_optimizer/safety/schema_lint.py
  - pyproject.toml
  - tests/safety/test_sql_classifier.py
  - tests/adapters/__init__.py
  - tests/adapters/test_auth.py
autonomous: true
requirements:
  - TRN-03
  - TRN-04
  - TRN-05
  - TRN-14

must_haves:
  truths:
    - "SqlClassifier accepts SELECT, WITH/CTE, EXPLAIN, EXPLAIN ANALYZE, SHOW variants, DESCRIBE, USE, VALUES"
    - "SqlClassifier rejects INSERT, UPDATE, DELETE, MERGE, CREATE, DROP, ALTER, TRUNCATE, CALL, GRANT, REVOKE, REFRESH, EXECUTE, SET SESSION AUTHORIZATION"
    - "SqlClassifier rejects multi-statement blocks, comment-wrapped DDL, Unicode escape tricks"
    - "SqlClassifier recursively validates EXPLAIN ANALYZE inner statement"
    - "Settings model accepts trino_auth_mode and fails fast on invalid auth config"
    - "Auth builder produces correct trino.auth objects for none/basic/jwt modes"
  artifacts:
    - path: "src/mcp_trino_optimizer/adapters/trino/classifier.py"
      provides: "SqlClassifier with assert_read_only(sql)"
      exports: ["SqlClassifier", "TrinoClassifierRejected"]
    - path: "src/mcp_trino_optimizer/adapters/trino/errors.py"
      provides: "Exception taxonomy for all adapter errors"
      exports: ["TrinoAdapterError", "TrinoAuthError", "TrinoVersionUnsupported", "TrinoPoolBusyError", "TrinoTimeoutError", "TrinoClassifierRejected", "TrinoConnectionError"]
    - path: "src/mcp_trino_optimizer/adapters/trino/auth.py"
      provides: "Auth mode builder with per-call JWT"
      exports: ["build_authentication", "PerCallJWTAuthentication"]
    - path: "tests/safety/test_sql_classifier.py"
      provides: "Locked classifier test corpus per D-17"
      min_lines: 100
  key_links:
    - from: "src/mcp_trino_optimizer/adapters/trino/classifier.py"
      to: "sqlglot"
      via: "sqlglot.parse(sql, dialect='trino')"
      pattern: "sqlglot\\.parse"
    - from: "src/mcp_trino_optimizer/settings.py"
      to: "adapters/trino/auth.py"
      via: "auth_mode field drives build_authentication()"
      pattern: "trino_auth_mode"
---

<objective>
Deliver the SqlClassifier read-only gate, the adapter error taxonomy, Trino auth builder, and extended Settings — the foundation modules that every other Phase 2 plan depends on.

Purpose: The classifier is the safety spine of the entire adapter layer (K-Decision #6). Every subsequent plan that touches Trino will call `assert_read_only(sql)` as its first line. The error taxonomy and auth builder must exist before the TrinoClient can be constructed.

Output: `classifier.py`, `errors.py`, `auth.py` under `adapters/trino/`, extended `settings.py` with Trino fields, extended `schema_lint.py` with `MAX_PLAN_JSON_LEN`, `pyproject.toml` with `trino` + `sqlglot` deps, locked classifier test corpus.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/02-trino-adapter-read-only-gate/02-CONTEXT.md
@.planning/phases/02-trino-adapter-read-only-gate/02-RESEARCH.md

<interfaces>
<!-- Key types and contracts the executor needs from Phase 1 -->

From src/mcp_trino_optimizer/settings.py:
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MCPTO_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
    )
    transport: Literal["stdio", "http"] = Field(default="stdio")
    http_host: str = Field(default="127.0.0.1")
    http_port: int = Field(default=8080, ge=1, le=65535)
    http_bearer_token: SecretStr | None = Field(default=None)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    @model_validator(mode="after")
    def _require_bearer_for_http(self) -> Settings: ...

def load_settings_or_die(**overrides: Any) -> Settings: ...
```

From src/mcp_trino_optimizer/safety/schema_lint.py:
```python
MAX_STRING_LEN = 100_000
MAX_PROSE_LEN = 4_096
MAX_ARRAY_LEN = 1_000
```

From src/mcp_trino_optimizer/logging_setup.py:
```python
REDACTION_DENYLIST: frozenset[str]  # already covers authorization, bearer, token, password, secret, etc.
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: SqlClassifier + error taxonomy + locked test corpus</name>
  <files>
    src/mcp_trino_optimizer/adapters/__init__.py
    src/mcp_trino_optimizer/adapters/trino/__init__.py
    src/mcp_trino_optimizer/adapters/trino/classifier.py
    src/mcp_trino_optimizer/adapters/trino/errors.py
    tests/safety/test_sql_classifier.py
  </files>
  <read_first>
    src/mcp_trino_optimizer/settings.py
    src/mcp_trino_optimizer/safety/schema_lint.py
    src/mcp_trino_optimizer/safety/envelope.py
    .planning/phases/02-trino-adapter-read-only-gate/02-RESEARCH.md
    .planning/phases/02-trino-adapter-read-only-gate/02-CONTEXT.md
    pyproject.toml
  </read_first>
  <behavior>
    - Test: SqlClassifier.assert_read_only("SELECT 1") does NOT raise
    - Test: SqlClassifier.assert_read_only("SELECT * FROM t WHERE x = 1") does NOT raise
    - Test: SqlClassifier.assert_read_only("WITH cte AS (SELECT 1) SELECT * FROM cte") does NOT raise
    - Test: SqlClassifier.assert_read_only("EXPLAIN (FORMAT JSON) SELECT 1") does NOT raise
    - Test: SqlClassifier.assert_read_only("EXPLAIN ANALYZE SELECT 1") does NOT raise
    - Test: SqlClassifier.assert_read_only("EXPLAIN (TYPE DISTRIBUTED) SELECT 1") does NOT raise
    - Test: SqlClassifier.assert_read_only("SHOW CATALOGS") does NOT raise
    - Test: SqlClassifier.assert_read_only("SHOW SCHEMAS") does NOT raise
    - Test: SqlClassifier.assert_read_only("SHOW TABLES") does NOT raise
    - Test: SqlClassifier.assert_read_only("SHOW COLUMNS FROM t") does NOT raise
    - Test: SqlClassifier.assert_read_only("SHOW CREATE TABLE t") does NOT raise
    - Test: SqlClassifier.assert_read_only("SHOW SESSION") does NOT raise
    - Test: SqlClassifier.assert_read_only("DESCRIBE t") does NOT raise
    - Test: SqlClassifier.assert_read_only("USE iceberg") does NOT raise
    - Test: SqlClassifier.assert_read_only("VALUES (1, 'a')") does NOT raise
    - Test: SqlClassifier.assert_read_only("INSERT INTO t VALUES (1)") RAISES TrinoClassifierRejected
    - Test: SqlClassifier.assert_read_only("UPDATE t SET x = 1") RAISES TrinoClassifierRejected
    - Test: SqlClassifier.assert_read_only("DELETE FROM t WHERE x = 1") RAISES TrinoClassifierRejected
    - Test: SqlClassifier.assert_read_only("MERGE INTO t USING s ON ...") RAISES TrinoClassifierRejected
    - Test: SqlClassifier.assert_read_only("CREATE TABLE t (x INT)") RAISES TrinoClassifierRejected
    - Test: SqlClassifier.assert_read_only("DROP TABLE t") RAISES TrinoClassifierRejected
    - Test: SqlClassifier.assert_read_only("ALTER TABLE t ADD COLUMN y INT") RAISES TrinoClassifierRejected
    - Test: SqlClassifier.assert_read_only("TRUNCATE TABLE t") RAISES TrinoClassifierRejected
    - Test: SqlClassifier.assert_read_only("CALL system.sync_partition_metadata(...)") RAISES TrinoClassifierRejected
    - Test: SqlClassifier.assert_read_only("GRANT SELECT ON t TO u") RAISES TrinoClassifierRejected
    - Test: SqlClassifier.assert_read_only("REVOKE SELECT ON t FROM u") RAISES TrinoClassifierRejected
    - Test: SqlClassifier.assert_read_only("SELECT 1; DROP TABLE t") RAISES (multi-statement)
    - Test: SqlClassifier.assert_read_only("/* DROP TABLE t */ SELECT 1") does NOT raise (comment stripped)
    - Test: SqlClassifier.assert_read_only("EXPLAIN ANALYZE INSERT INTO t VALUES (1)") RAISES (inner is write)
    - Test: SqlClassifier.assert_read_only("EXPLAIN ANALYZE DELETE FROM t") RAISES (inner is write)
    - Test: SqlClassifier.assert_read_only("") RAISES (empty)
    - Test: SqlClassifier.assert_read_only("   ") RAISES (whitespace only)
    - Test: SqlClassifier.assert_read_only("SET SESSION AUTHORIZATION admin") RAISES TrinoClassifierRejected
  </behavior>
  <action>
    **First**, add `sqlglot>=30.4.2` and `trino>=0.337.0` to `pyproject.toml` `[project] dependencies`. Add `testcontainers[trino,minio]>=4.14.2` to `[project.optional-dependencies] dev`.

    **Create directory structure**: `src/mcp_trino_optimizer/adapters/__init__.py` and `src/mcp_trino_optimizer/adapters/trino/__init__.py` (empty `__init__.py` files).

    **Create `errors.py`** at `src/mcp_trino_optimizer/adapters/trino/errors.py` per D-26:
    ```python
    class TrinoAdapterError(Exception):
        def __init__(self, message: str, *, request_id: str = "", query_id: str = "") -> None:
            self.request_id = request_id
            self.query_id = query_id
            super().__init__(message)

    class TrinoAuthError(TrinoAdapterError): ...
    class TrinoVersionUnsupported(TrinoAdapterError): ...
    class TrinoPoolBusyError(TrinoAdapterError): ...
    class TrinoTimeoutError(TrinoAdapterError): ...
    class TrinoClassifierRejected(TrinoAdapterError): ...
    class TrinoConnectionError(TrinoAdapterError): ...
    ```

    **Create `classifier.py`** at `src/mcp_trino_optimizer/adapters/trino/classifier.py` per D-16 and RESEARCH.md Pattern 1:
    - Class `SqlClassifier` with method `assert_read_only(sql: str) -> None` that raises `TrinoClassifierRejected` on rejection.
    - Uses `sqlglot.parse(sql, dialect="trino")` — NEVER regex.
    - Typed allowlist: `(exp.Select, exp.Describe, exp.Use, exp.Values)` for direct AST nodes.
    - Command keyword allowlist: `frozenset({"EXPLAIN", "SHOW", "DESCRIBE"})` for `exp.Command` fallback nodes.
    - Reject if `parse()` returns 0 or >1 non-None statements (empty/multi-statement).
    - For EXPLAIN/EXPLAIN ANALYZE: strip "ANALYZE " prefix and parenthesized options like "(FORMAT JSON)", "(TYPE DISTRIBUTED)" from `cmd.args["expression"]`, re-parse inner SQL, recursively classify. Inner must be on the allowlist (no writes inside EXPLAIN).
    - All other AST node types (Insert, Update, Delete, Merge, Create, Drop, Alter, TruncateTable, Grant, etc.) are rejected.
    - Comment-wrapped DDL: `sqlglot.parse` strips comments before building the AST, so `/* DROP TABLE t */ SELECT 1` parses as a plain SELECT — safe by construction.
    - Unicode tricks: sqlglot normalizes Unicode during tokenization, so the classifier sees the AST, not raw text.

    **Create `tests/safety/test_sql_classifier.py`** with parameterized test cases for every behavior listed above. Use `@pytest.mark.parametrize` with two groups: `test_classifier_allows` for valid read-only SQL and `test_classifier_rejects` for invalid/write SQL. Each rejected case asserts `TrinoClassifierRejected` is raised with a descriptive message containing the statement type.

    **Create `tests/adapters/__init__.py`** (empty).
  </action>
  <verify>
    <automated>uv run pytest tests/safety/test_sql_classifier.py -v -x</automated>
  </verify>
  <acceptance_criteria>
    - `src/mcp_trino_optimizer/adapters/trino/classifier.py` contains `class SqlClassifier` and `def assert_read_only`
    - `src/mcp_trino_optimizer/adapters/trino/classifier.py` contains `sqlglot.parse(` (not regex)
    - `src/mcp_trino_optimizer/adapters/trino/classifier.py` contains `exp.Select` and `exp.Command`
    - `src/mcp_trino_optimizer/adapters/trino/errors.py` contains all 6 exception classes: `TrinoAdapterError`, `TrinoAuthError`, `TrinoVersionUnsupported`, `TrinoPoolBusyError`, `TrinoTimeoutError`, `TrinoClassifierRejected`, `TrinoConnectionError`
    - `tests/safety/test_sql_classifier.py` has at least 30 parameterized test cases
    - `uv run pytest tests/safety/test_sql_classifier.py -v -x` exits 0
    - `pyproject.toml` dependencies list contains `trino>=0.337.0` and `sqlglot>=30.4.2`
  </acceptance_criteria>
  <done>SqlClassifier rejects all write/DDL/DML statements, accepts all read-only statements, handles multi-statement, empty, comments, Unicode, and recursive EXPLAIN inner validation. Error taxonomy defines all 6 exception classes. All classifier tests pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Settings extension + auth builder + auth unit tests</name>
  <files>
    src/mcp_trino_optimizer/settings.py
    src/mcp_trino_optimizer/adapters/trino/auth.py
    src/mcp_trino_optimizer/safety/schema_lint.py
    tests/adapters/test_auth.py
  </files>
  <read_first>
    src/mcp_trino_optimizer/settings.py
    src/mcp_trino_optimizer/safety/schema_lint.py
    src/mcp_trino_optimizer/adapters/trino/errors.py
    .planning/phases/02-trino-adapter-read-only-gate/02-CONTEXT.md
    .planning/phases/02-trino-adapter-read-only-gate/02-RESEARCH.md
  </read_first>
  <behavior>
    - Test: Settings(trino_host="localhost") with auth_mode="none" succeeds
    - Test: Settings with auth_mode="basic" but no user/password raises ValidationError
    - Test: Settings with auth_mode="basic", trino_user="u", trino_password=SecretStr("p") succeeds
    - Test: Settings with auth_mode="jwt" but no jwt raises ValidationError
    - Test: Settings with auth_mode="jwt", trino_jwt=SecretStr("tok") succeeds
    - Test: build_authentication(settings) returns None for auth_mode="none"
    - Test: build_authentication(settings) returns BasicAuthentication for auth_mode="basic"
    - Test: build_authentication(settings) returns PerCallJWTAuthentication for auth_mode="jwt"
    - Test: PerCallJWTAuthentication re-reads os.environ on each set_http_session call
  </behavior>
  <action>
    **Extend `settings.py`** with Phase 2 Trino fields per D-11:
    ```python
    trino_host: str | None = Field(default=None, description="Trino coordinator hostname. Required for live mode.")
    trino_port: int = Field(default=8080, ge=1, le=65535, description="Trino coordinator port.")
    trino_catalog: str = Field(default="iceberg", description="Default Trino catalog.")
    trino_schema: str | None = Field(default=None, description="Default Trino schema.")
    trino_auth_mode: Literal["none", "basic", "jwt"] = Field(default="none", description="Trino authentication mode.")
    trino_user: str | None = Field(default=None, description="Trino user for basic auth.")
    trino_password: SecretStr | None = Field(default=None, description="Trino password for basic auth.")
    trino_jwt: SecretStr | None = Field(default=None, description="Trino JWT token for jwt auth.")
    trino_verify_ssl: bool = Field(default=True, description="Verify SSL certificates for Trino connections.")
    trino_ca_bundle: str | None = Field(default=None, description="Path to CA bundle for Trino TLS.")
    trino_query_timeout_sec: int = Field(default=60, ge=1, le=1800, description="Wall-clock timeout per Trino query in seconds.")
    max_concurrent_queries: int = Field(default=4, ge=1, le=32, description="Max concurrent Trino queries per MCP process.")
    ```

    Add a new `@model_validator(mode='after')` method `_require_trino_auth_fields` that:
    - If `trino_auth_mode == "basic"` and (`trino_user` is None or `trino_password` is None): raise ValueError
    - If `trino_auth_mode == "jwt"` and `trino_jwt` is None: raise ValueError

    **Add `MAX_PLAN_JSON_LEN = 1_000_000`** to `safety/schema_lint.py` and export it in `__all__`.

    **Create `auth.py`** at `src/mcp_trino_optimizer/adapters/trino/auth.py` per D-12, D-13, D-14 and RESEARCH.md Pattern 3:
    - `class PerCallJWTAuthentication(Authentication)`: overrides `set_http_session(self, http_session)` to read `os.environ.get(self._env_var, "")` on every call and set `Authorization: Bearer {token}`. The `__init__` takes `env_var: str = "MCPTO_TRINO_JWT"`.
    - `def build_authentication(settings: Settings) -> Authentication | None`: returns `None` for `none`, `BasicAuthentication(user, password.get_secret_value())` for `basic`, `PerCallJWTAuthentication()` for `jwt`.

    **Create `tests/adapters/test_auth.py`** with unit tests for:
    - Settings validation (auth_mode fail-fast on missing fields)
    - `build_authentication()` returns correct type per mode
    - `PerCallJWTAuthentication` re-reads from `os.environ` (use `monkeypatch.setenv`)
  </action>
  <verify>
    <automated>uv run pytest tests/adapters/test_auth.py -v -x && uv run pytest tests/ -m "not integration" -x --tb=short -q</automated>
  </verify>
  <acceptance_criteria>
    - `src/mcp_trino_optimizer/settings.py` contains `trino_host`, `trino_port`, `trino_auth_mode`, `trino_user`, `trino_password`, `trino_jwt`, `trino_verify_ssl`, `trino_ca_bundle`, `trino_query_timeout_sec`, `max_concurrent_queries`
    - `src/mcp_trino_optimizer/settings.py` contains `def _require_trino_auth_fields`
    - `src/mcp_trino_optimizer/adapters/trino/auth.py` contains `class PerCallJWTAuthentication` and `def build_authentication`
    - `src/mcp_trino_optimizer/safety/schema_lint.py` contains `MAX_PLAN_JSON_LEN = 1_000_000`
    - `tests/adapters/test_auth.py` exits 0
    - Full non-integration test suite passes: `uv run pytest -m "not integration" -x` exits 0
  </acceptance_criteria>
  <done>Settings model extended with all Trino fields and auth-mode validators. Auth builder produces correct trino.auth objects for none/basic/jwt modes. PerCallJWTAuthentication re-reads env var on every call. MAX_PLAN_JSON_LEN constant added. All tests pass.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| User SQL -> SqlClassifier | Untrusted SQL string from MCP tool input crosses into the adapter layer |
| Settings env vars -> Auth builder | Secrets (JWT, password) flow from env to HTTP headers |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-02-01 | Tampering | SqlClassifier | mitigate | AST-based allowlist via sqlglot.parse; reject multi-statement, Command nodes not in allowlist, recursive EXPLAIN inner validation |
| T-02-02 | Tampering | SqlClassifier | mitigate | Comment-wrapped DDL safe by construction: sqlglot strips comments before AST. Unicode tricks safe: sqlglot normalizes during tokenization |
| T-02-03 | Information Disclosure | auth.py | mitigate | JWT stored as SecretStr, rendered as [REDACTED] via structlog denylist. PerCallJWTAuthentication reads from os.environ, never logs the value |
| T-02-04 | Elevation of Privilege | Settings | mitigate | model_validator(mode='after') fails fast on invalid auth config combinations before any network call |
</threat_model>

<verification>
```bash
# All classifier tests pass
uv run pytest tests/safety/test_sql_classifier.py -v -x
# All auth tests pass
uv run pytest tests/adapters/test_auth.py -v -x
# Full non-integration suite still green
uv run pytest -m "not integration" -x --tb=short -q
# Type check passes
uv run mypy src/mcp_trino_optimizer/adapters/ --strict
```
</verification>

<success_criteria>
- SqlClassifier accepts all 15+ read-only SQL forms and rejects all 15+ write/DDL/DML forms
- Recursive EXPLAIN ANALYZE inner validation catches write statements
- Multi-statement, empty, whitespace-only inputs are rejected
- Settings auth-mode validation fails fast on missing required fields
- PerCallJWTAuthentication re-reads JWT from env on each invocation
- Error taxonomy has all 6 exception classes inheriting from TrinoAdapterError
- Full non-integration test suite passes
</success_criteria>

<output>
After completion, create `.planning/phases/02-trino-adapter-read-only-gate/02-01-SUMMARY.md`
</output>
