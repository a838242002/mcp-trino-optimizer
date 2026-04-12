"""DDL bypass helper — uses raw trino-python-client DBAPI directly (D-25).

This helper is test-only, lives outside src/, and uses trino.dbapi.connect
rather than the production adapter. This is intentional: test table seeding
requires DDL statements (CREATE TABLE, INSERT) that the production adapter's
SqlClassifier gate would reject. The raw DBAPI cursor bypasses the gate for
test setup only.

See CONTRIBUTING.md "Safe-execution boundaries" for the full invariant.
"""

from __future__ import annotations

import trino.dbapi


def seed_iceberg_table(
    host: str,
    port: int,
    catalog: str = "iceberg",
) -> None:
    """Create a test Iceberg table and insert sample data.

    Uses raw trino-python-client DBAPI directly (see D-25).
    DDL must bypass the SqlClassifier read-only gate for test seeding.
    """
    conn = trino.dbapi.connect(  # type: ignore[no-untyped-call]
        host=host,
        port=port,
        user="test",
        catalog=catalog,
    )
    cursor = conn.cursor()
    try:
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {catalog}.test_schema")
        cursor.fetchall()
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {catalog}.test_schema.test_table (
                id INTEGER,
                name VARCHAR,
                ts TIMESTAMP(6) WITH TIME ZONE
            ) WITH (partitioning = ARRAY['day(ts)'])
            """
        )
        cursor.fetchall()
        cursor.execute(
            f"""
            INSERT INTO {catalog}.test_schema.test_table
            VALUES
                (1, 'alice',   TIMESTAMP '2025-01-15 10:00:00 UTC'),
                (2, 'bob',     TIMESTAMP '2025-01-16 11:00:00 UTC'),
                (3, 'charlie', TIMESTAMP '2025-01-17 12:00:00 UTC')
            """
        )
        cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def cleanup_iceberg_table(
    host: str,
    port: int,
    catalog: str = "iceberg",
) -> None:
    """Drop the test table and schema created by seed_iceberg_table.

    Uses raw trino-python-client DBAPI directly (see D-25).
    """
    conn = trino.dbapi.connect(  # type: ignore[no-untyped-call]
        host=host,
        port=port,
        user="test",
        catalog=catalog,
    )
    cursor = conn.cursor()
    try:
        cursor.execute(f"DROP TABLE IF EXISTS {catalog}.test_schema.test_table")
        cursor.fetchall()
        cursor.execute(f"DROP SCHEMA IF EXISTS {catalog}.test_schema")
        cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
