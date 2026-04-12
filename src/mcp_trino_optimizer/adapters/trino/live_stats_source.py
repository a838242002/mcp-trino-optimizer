"""LiveStatsSource — implements StatsSource via live TrinoClient (TRN-09).

Thin wrapper that delegates SHOW STATS and system.runtime queries to
``TrinoClient``.  On ``TimeoutResult``, returns partial data (best-effort)
because callers can make useful decisions from incomplete stats.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp_trino_optimizer.adapters.trino.handle import TimeoutResult

if TYPE_CHECKING:
    from mcp_trino_optimizer.adapters.trino.client import TrinoClient

__all__ = ["LiveStatsSource"]


class LiveStatsSource:
    """StatsSource via a live TrinoClient. Thin delegation wrapper.

    Args:
        client: Configured ``TrinoClient`` instance.
    """

    def __init__(self, client: TrinoClient) -> None:
        self._client = client

    async def fetch_table_stats(
        self,
        catalog: str,
        schema: str,
        table: str,
    ) -> dict[str, Any]:
        """Fetch column-level statistics for a table via ``SHOW STATS FOR``.

        Args:
            catalog: Trino catalog name.
            schema: Schema/database name.
            table: Table name.

        Returns:
            A dict with keys ``"columns"`` (per-column stats dict) and
            ``"row_count"`` (float or None).  Returns partial data on timeout.
        """
        result = await self._client.fetch_stats(catalog, schema, table)
        rows: list[dict[str, Any]]
        rows = result.partial if isinstance(result, TimeoutResult) else result
        return _parse_show_stats(rows)

    async def fetch_system_runtime(self, query: str) -> list[dict[str, Any]]:
        """Run a read-only query and return rows as a list of dicts.

        Best-effort on timeout — returns partial rows collected so far.

        Args:
            query: A read-only SQL SELECT (typically against ``system.runtime.*``).

        Returns:
            A list of row dicts.  May be empty or partial on timeout.
        """
        result = await self._client.fetch_system_runtime(query)
        if isinstance(result, TimeoutResult):
            return result.partial
        return result


def _parse_show_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert SHOW STATS FOR rows into the StatsSource return shape.

    SHOW STATS returns one row per column plus a summary row (column_name=NULL).
    Column names from Trino: column_name, data_size, distinct_values_count,
    nulls_fractions, row_count, low_value, high_value.
    """
    columns: dict[str, dict[str, Any]] = {}
    row_count: float | None = None

    for row in rows:
        col_name = row.get("column_name")
        if col_name is None:
            # Summary row — has row_count
            raw_rc = row.get("row_count")
            row_count = float(raw_rc) if raw_rc is not None else None
        else:
            columns[str(col_name)] = {
                "null_fraction": _to_float(row.get("nulls_fractions")),
                "distinct_values_count": _to_float(row.get("distinct_values_count")),
                "low_value": row.get("low_value"),
                "high_value": row.get("high_value"),
                "data_size": _to_float(row.get("data_size")),
            }

    return {"columns": columns, "row_count": row_count}


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
