"""Fixture capture script for multi-version Trino EXPLAIN corpus.

Connects to a running Trino instance, creates test tables, and captures
EXPLAIN (FORMAT JSON) and EXPLAIN ANALYZE output for a set of reference queries.

Usage:
    python scripts/capture_fixtures.py [--host HOST] [--port PORT] [--version VERSION]

Security note (T-03-07): This script connects to a local Trino instance with no
authentication. It does NOT store any credentials in the captured fixture files.
All fixtures are read-only EXPLAIN outputs — no data is exported.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import trino

# ── Query corpus ─────────────────────────────────────────────────────────────

SETUP_STATEMENTS = [
    "CREATE SCHEMA IF NOT EXISTS iceberg.test_fixtures",
    """CREATE TABLE IF NOT EXISTS iceberg.test_fixtures.orders (
        id BIGINT,
        name VARCHAR,
        amount DECIMAL(10,2),
        ts TIMESTAMP(6) WITH TIME ZONE,
        status VARCHAR
    ) WITH (partitioning = ARRAY['day(ts)'])""",
]

# Insert sample rows in batches across multiple days/partitions
INSERT_ROWS_TEMPLATE = """INSERT INTO iceberg.test_fixtures.orders VALUES
    (1, 'Alice', 150.00, TIMESTAMP '2025-01-10 08:00:00 UTC', 'open'),
    (2, 'Bob', 75.50, TIMESTAMP '2025-01-10 09:00:00 UTC', 'closed'),
    (3, 'Carol', 220.00, TIMESTAMP '2025-01-11 10:00:00 UTC', 'open'),
    (4, 'Dave', 45.00, TIMESTAMP '2025-01-11 11:00:00 UTC', 'pending'),
    (5, 'Eve', 310.25, TIMESTAMP '2025-01-12 12:00:00 UTC', 'open'),
    (6, 'Frank', 88.00, TIMESTAMP '2025-01-12 13:00:00 UTC', 'closed'),
    (7, 'Grace', 195.50, TIMESTAMP '2025-01-13 14:00:00 UTC', 'open'),
    (8, 'Hank', 62.75, TIMESTAMP '2025-01-13 15:00:00 UTC', 'pending'),
    (9, 'Iris', 400.00, TIMESTAMP '2025-01-14 16:00:00 UTC', 'open'),
    (10, 'Jack', 29.99, TIMESTAMP '2025-01-14 17:00:00 UTC', 'closed'),
    (11, 'Kate', 175.00, TIMESTAMP '2025-01-15 08:00:00 UTC', 'open'),
    (12, 'Leo', 55.00, TIMESTAMP '2025-01-15 09:00:00 UTC', 'closed'),
    (13, 'Mia', 285.50, TIMESTAMP '2025-01-15 10:00:00 UTC', 'open'),
    (14, 'Ned', 120.00, TIMESTAMP '2025-01-15 11:00:00 UTC', 'pending'),
    (15, 'Ora', 350.00, TIMESTAMP '2025-01-15 12:00:00 UTC', 'open'),
    (16, 'Pat', 95.25, TIMESTAMP '2025-01-15 13:00:00 UTC', 'closed'),
    (17, 'Quinn', 210.00, TIMESTAMP '2025-01-15 14:00:00 UTC', 'open'),
    (18, 'Ray', 38.50, TIMESTAMP '2025-01-15 15:00:00 UTC', 'pending'),
    (19, 'Sue', 445.75, TIMESTAMP '2025-01-15 16:00:00 UTC', 'open'),
    (20, 'Tom', 15.00, TIMESTAMP '2025-01-15 17:00:00 UTC', 'closed')
"""

QUERIES: dict[str, str] = {
    "simple_select": (
        "SELECT id, name FROM iceberg.test_fixtures.orders WHERE id > 10"
    ),
    "full_scan": (
        "SELECT * FROM iceberg.test_fixtures.orders"
    ),
    "aggregate": (
        "SELECT status, COUNT(*), SUM(amount) "
        "FROM iceberg.test_fixtures.orders GROUP BY status"
    ),
    "join": (
        "SELECT a.id, a.name, b.status "
        "FROM iceberg.test_fixtures.orders a "
        "JOIN iceberg.test_fixtures.orders b ON a.id = b.id "
        "WHERE a.amount > 100"
    ),
    "iceberg_partition_filter": (
        "SELECT * FROM iceberg.test_fixtures.orders "
        "WHERE ts >= TIMESTAMP '2025-01-15 00:00:00 UTC' "
        "AND ts < TIMESTAMP '2025-01-16 00:00:00 UTC'"
    ),
}

# Only capture these queries for older versions (more complex queries may fail
# if the version has Iceberg/Lakekeeper compatibility issues)
MINIMAL_QUERIES = ["simple_select", "aggregate"]


def _connect(host: str, port: int) -> trino.dbapi.Connection:
    """Create a Trino connection (no auth — local dev stack only)."""
    return trino.dbapi.connect(
        host=host,
        port=port,
        user="trino",
        # No auth: local dev stack (T-03-07 compliance — no credentials stored)
    )


def _execute_query(conn: trino.dbapi.Connection, sql: str) -> list[list]:
    """Execute a SQL statement and return all rows."""
    cursor = conn.cursor()
    cursor.execute(sql)
    return cursor.fetchall()


def _detect_version(conn: trino.dbapi.Connection) -> str:
    """Auto-detect Trino version from system.runtime.nodes."""
    try:
        rows = _execute_query(conn, "SELECT node_version FROM system.runtime.nodes LIMIT 1")
        if rows and rows[0]:
            return str(rows[0][0])
    except Exception as e:
        print(f"  Warning: could not auto-detect version: {e}", file=sys.stderr)
    return "unknown"


def _setup_test_table(conn: trino.dbapi.Connection) -> bool:
    """Create schema and table, insert sample rows. Returns True on success."""
    try:
        for stmt in SETUP_STATEMENTS:
            print(f"  Executing: {stmt[:80]}...", file=sys.stderr)
            _execute_query(conn, stmt)

        # Check if table has data; insert if not
        rows = _execute_query(conn, "SELECT COUNT(*) FROM iceberg.test_fixtures.orders")
        count = rows[0][0] if rows else 0
        if count == 0:
            print("  Inserting sample rows...", file=sys.stderr)
            _execute_query(conn, INSERT_ROWS_TEMPLATE)
            _execute_query(conn, "ANALYZE iceberg.test_fixtures.orders")

        print(f"  Table ready with {count or '20+'} rows.", file=sys.stderr)
        return True
    except Exception as e:
        print(f"  Setup failed: {e}", file=sys.stderr)
        return False


def _capture_explain_json(conn: trino.dbapi.Connection, sql: str) -> str | None:
    """Run EXPLAIN (FORMAT JSON) and return the JSON string."""
    try:
        rows = _execute_query(conn, f"EXPLAIN (FORMAT JSON) {sql}")
        if rows and rows[0]:
            return str(rows[0][0])
    except Exception as e:
        print(f"    EXPLAIN JSON failed: {e}", file=sys.stderr)
    return None


def _capture_explain_analyze(conn: trino.dbapi.Connection, sql: str) -> str | None:
    """Run EXPLAIN ANALYZE and return the text output."""
    try:
        rows = _execute_query(conn, f"EXPLAIN ANALYZE {sql}")
        if rows and rows[0]:
            return str(rows[0][0])
    except Exception as e:
        print(f"    EXPLAIN ANALYZE failed: {e}", file=sys.stderr)
    return None


def _write_fixture(path: Path, content: str) -> None:
    """Write fixture content to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  Wrote: {path}", file=sys.stderr)


def capture_version(
    host: str,
    port: int,
    version: str,
    fixture_dir: Path,
    queries: dict[str, str],
    skip_setup: bool = False,
) -> int:
    """Capture fixtures for a specific Trino version.

    Returns the number of fixture pairs successfully captured.
    """
    print(f"\n=== Capturing fixtures for Trino {version} ===", file=sys.stderr)
    print(f"    host={host}, port={port}", file=sys.stderr)

    try:
        conn = _connect(host, port)
        # Test connectivity
        detected = _detect_version(conn)
        if version == "auto":
            version = detected
        print(f"  Connected. Detected version: {detected}", file=sys.stderr)
    except Exception as e:
        print(f"  Connection failed: {e}", file=sys.stderr)
        return 0

    if not skip_setup:
        if not _setup_test_table(conn):
            print("  Skipping fixture capture (table setup failed).", file=sys.stderr)
            return 0

    captured = 0
    for query_name, sql in queries.items():
        print(f"\n  Query: {query_name}", file=sys.stderr)

        # EXPLAIN (FORMAT JSON)
        json_path = fixture_dir / version / f"{query_name}.json"
        explain_json = _capture_explain_json(conn, sql)
        if explain_json:
            # Pretty-print the JSON for readability (but keep it valid JSON)
            try:
                parsed = json.loads(explain_json)
                pretty = json.dumps(parsed, indent=2)
                _write_fixture(json_path, pretty)
            except json.JSONDecodeError:
                _write_fixture(json_path, explain_json)

        # EXPLAIN ANALYZE
        txt_path = fixture_dir / version / f"{query_name}_analyze.txt"
        explain_analyze = _capture_explain_analyze(conn, sql)
        if explain_analyze:
            _write_fixture(txt_path, explain_analyze)

        if explain_json and explain_analyze:
            captured += 1
        else:
            print(f"    Warning: partial capture for {query_name}", file=sys.stderr)

    print(f"\n  Captured {captured}/{len(queries)} query pairs for version {version}.", file=sys.stderr)
    return captured


def main() -> None:
    """Entry point for the fixture capture script."""
    parser = argparse.ArgumentParser(
        description="Capture Trino EXPLAIN fixture corpus for multi-version testing."
    )
    parser.add_argument("--host", default="localhost", help="Trino host (default: localhost)")
    parser.add_argument("--port", type=int, default=8080, help="Trino port (default: 8080)")
    parser.add_argument(
        "--version",
        default="auto",
        help="Trino version string (default: auto-detect from system.runtime.nodes)",
    )
    parser.add_argument(
        "--minimal",
        action="store_true",
        help="Capture only simple_select and aggregate queries (for older versions)",
    )
    parser.add_argument(
        "--skip-setup",
        action="store_true",
        help="Skip schema/table creation (assumes table already exists)",
    )
    parser.add_argument(
        "--output-dir",
        default="tests/fixtures/explain",
        help="Output directory for fixture files (default: tests/fixtures/explain)",
    )
    args = parser.parse_args()

    fixture_dir = Path(args.output_dir)
    queries = {k: v for k, v in QUERIES.items() if not args.minimal or k in MINIMAL_QUERIES}

    captured = capture_version(
        host=args.host,
        port=args.port,
        version=args.version,
        fixture_dir=fixture_dir,
        queries=queries,
        skip_setup=args.skip_setup,
    )

    if captured == 0:
        print("\nERROR: No fixtures captured.", file=sys.stderr)
        sys.exit(1)

    print(f"\nDone. {captured} fixture pairs written to {fixture_dir}/", file=sys.stderr)


if __name__ == "__main__":
    main()
