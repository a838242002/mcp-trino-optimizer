"""Locked classifier test corpus — D-17.

Tests the SqlClassifier.assert_read_only() safety gate.

All tests are parameterized and fall into two groups:
  - test_classifier_allows: read-only SQL that must NOT raise
  - test_classifier_rejects: write/DDL/DML/empty SQL that MUST raise TrinoClassifierRejected
"""

from __future__ import annotations

import pytest

from mcp_trino_optimizer.adapters.trino.classifier import SqlClassifier
from mcp_trino_optimizer.adapters.trino.errors import TrinoClassifierRejected

_classifier = SqlClassifier()

# ---------------------------------------------------------------------------
# Allowed statements (read-only)
# ---------------------------------------------------------------------------

ALLOWED_CASES = [
    # Basic SELECT
    ("select_1", "SELECT 1"),
    ("select_with_filter", "SELECT * FROM t WHERE x = 1"),
    ("select_multi_col", "SELECT a, b, c FROM my_table WHERE dt = '2024-01-01'"),
    # CTEs / WITH
    ("with_cte", "WITH cte AS (SELECT 1) SELECT * FROM cte"),
    ("with_multi_cte", "WITH a AS (SELECT 1), b AS (SELECT 2) SELECT * FROM a JOIN b ON TRUE"),
    # EXPLAIN variants
    ("explain_format_json", "EXPLAIN (FORMAT JSON) SELECT 1"),
    ("explain_analyze", "EXPLAIN ANALYZE SELECT 1"),
    ("explain_type_distributed", "EXPLAIN (TYPE DISTRIBUTED) SELECT 1"),
    ("explain_plain", "EXPLAIN SELECT * FROM t"),
    ("explain_analyze_with_cte", "EXPLAIN ANALYZE WITH cte AS (SELECT 1) SELECT * FROM cte"),
    # SHOW variants
    ("show_catalogs", "SHOW CATALOGS"),
    ("show_schemas", "SHOW SCHEMAS"),
    ("show_tables", "SHOW TABLES"),
    ("show_columns", "SHOW COLUMNS FROM t"),
    ("show_create_table", "SHOW CREATE TABLE t"),
    ("show_session", "SHOW SESSION"),
    ("show_functions", "SHOW FUNCTIONS"),
    # DESCRIBE
    ("describe", "DESCRIBE t"),
    # USE
    ("use_catalog", "USE iceberg"),
    ("use_schema", "USE iceberg.prod"),
    # VALUES
    ("values", "VALUES (1, 'a')"),
    ("values_multi", "VALUES (1, 'a'), (2, 'b')"),
    # Comment-wrapped DDL: sqlglot strips comments before AST → parses as SELECT
    ("comment_wrapped_ddl", "/* DROP TABLE t */ SELECT 1"),
    ("inline_comment", "-- just a comment\nSELECT 1"),
    # Complex read-only queries
    ("join_query", "SELECT a.id, b.name FROM a JOIN b ON a.id = b.id"),
    ("subquery", "SELECT * FROM (SELECT 1 AS x) sub"),
    ("window_function", "SELECT id, ROW_NUMBER() OVER (PARTITION BY category ORDER BY ts) FROM t"),
]

ALLOWED_IDS = [c[0] for c in ALLOWED_CASES]
ALLOWED_SQL = [c[1] for c in ALLOWED_CASES]


@pytest.mark.parametrize("sql", ALLOWED_SQL, ids=ALLOWED_IDS)
def test_classifier_allows(sql: str) -> None:
    """assert_read_only() must NOT raise for read-only SQL."""
    _classifier.assert_read_only(sql)  # should not raise


# ---------------------------------------------------------------------------
# Rejected statements (write / DDL / DML / invalid)
# ---------------------------------------------------------------------------

REJECTED_CASES = [
    # DML
    ("insert_into", "INSERT INTO t VALUES (1)"),
    ("update_set", "UPDATE t SET x = 1"),
    ("delete_from", "DELETE FROM t WHERE x = 1"),
    ("merge_into", "MERGE INTO target USING source ON target.id = source.id WHEN MATCHED THEN UPDATE SET x = source.x"),
    # DDL
    ("create_table", "CREATE TABLE t (x INT)"),
    ("drop_table", "DROP TABLE t"),
    ("alter_table_add_column", "ALTER TABLE t ADD COLUMN y INT"),
    ("truncate_table", "TRUNCATE TABLE t"),
    # Permission / session manipulation
    ("grant", "GRANT SELECT ON t TO u"),
    ("revoke", "REVOKE SELECT ON t FROM u"),
    ("set_session_authorization", "SET SESSION AUTHORIZATION admin"),
    # Procedure / system calls
    ("call_system", "CALL system.sync_partition_metadata('iceberg', 'prod', 'events')"),
    # Multi-statement (separator check)
    ("multi_statement", "SELECT 1; DROP TABLE t"),
    # Recursive EXPLAIN inner validation: write inside EXPLAIN must be rejected
    ("explain_analyze_insert", "EXPLAIN ANALYZE INSERT INTO t VALUES (1)"),
    ("explain_analyze_delete", "EXPLAIN ANALYZE DELETE FROM t"),
    ("explain_format_json_drop", "EXPLAIN (FORMAT JSON) DROP TABLE t"),
    # Empty / whitespace
    ("empty_string", ""),
    ("whitespace_only", "   "),
    ("newlines_only", "\n\n\n"),
]

REJECTED_IDS = [c[0] for c in REJECTED_CASES]
REJECTED_SQL = [c[1] for c in REJECTED_CASES]


@pytest.mark.parametrize("sql", REJECTED_SQL, ids=REJECTED_IDS)
def test_classifier_rejects(sql: str) -> None:
    """assert_read_only() MUST raise TrinoClassifierRejected for write/DDL/DML."""
    with pytest.raises(TrinoClassifierRejected):
        _classifier.assert_read_only(sql)


# ---------------------------------------------------------------------------
# Error message quality tests
# ---------------------------------------------------------------------------


def test_rejected_message_contains_statement_type() -> None:
    """TrinoClassifierRejected message must contain context about rejection."""
    with pytest.raises(TrinoClassifierRejected, match=r"(?i)(insert|write|read.only|rejected|not allowed)"):
        _classifier.assert_read_only("INSERT INTO t VALUES (1)")


def test_rejected_empty_message_contains_context() -> None:
    """Rejection of empty SQL must mention empty/blank in the error."""
    with pytest.raises(TrinoClassifierRejected, match=r"(?i)(empty|blank|whitespace|statement)"):
        _classifier.assert_read_only("")


def test_rejected_multi_statement_message_contains_context() -> None:
    """Rejection of multi-statement SQL must mention multi/multiple in the error."""
    with pytest.raises(TrinoClassifierRejected, match=r"(?i)(multi|multiple|semicolon|statement)"):
        _classifier.assert_read_only("SELECT 1; DROP TABLE t")


def test_error_is_trino_adapter_error() -> None:
    """TrinoClassifierRejected must be a subclass of TrinoAdapterError."""
    from mcp_trino_optimizer.adapters.trino.errors import TrinoAdapterError

    with pytest.raises(TrinoAdapterError):
        _classifier.assert_read_only("DELETE FROM t")
