"""StatsSource port — the hexagonal boundary for Trino statistics retrieval.

This module is a pure Protocol definition. It MUST NOT import anything from
``mcp_trino_optimizer.adapters``. The rule engine and recommender consume this
port without knowing whether stats come from a live cluster or a fixture file.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StatsSource(Protocol):
    """Port contract for retrieving Trino table and runtime statistics.

    Implementations:
    - ``adapters.trino.live_stats_source.LiveStatsSource`` — queries
      ``system.runtime.*`` and ``system.metadata.*`` on a live Trino cluster.

    All methods are ``async`` because live implementations bridge the sync
    trino-python-client via ``anyio.to_thread``.
    """

    async def fetch_table_stats(
        self,
        catalog: str,
        schema: str,
        table: str,
    ) -> dict[str, Any]:
        """Fetch column-level statistics for a table.

        Queries ``SHOW STATS FOR <catalog>.<schema>.<table>`` and returns the
        result as a dict keyed by column name, with nested stats dicts.

        Args:
            catalog: Trino catalog name (e.g. ``iceberg``).
            schema: Schema/database name.
            table: Table name.

        Returns:
            A dict of the form::

                {
                    "columns": {
                        "<col_name>": {
                            "null_fraction": float | None,
                            "distinct_values_count": float | None,
                            "low_value": str | None,
                            "high_value": str | None,
                            "data_size": float | None,
                        },
                        ...
                    },
                    "row_count": float | None,
                }
        """
        ...

    async def fetch_system_runtime(self, query: str) -> list[dict[str, Any]]:
        """Run a read-only query against ``system.runtime`` tables and return rows.

        The ``query`` must be a SELECT against ``system.runtime.*``. The live
        adapter calls ``SqlClassifier.assert_read_only(query)`` before
        executing.

        Args:
            query: A read-only SQL SELECT against ``system.runtime.*``.

        Returns:
            A list of row dicts, each keyed by column name.
        """
        ...
