"""LiveCatalogSource — implements CatalogSource via live TrinoClient (TRN-10, T-02-13).

Thin wrapper that delegates Iceberg metadata table queries and SHOW commands
to ``TrinoClient``.  On ``TimeoutResult``, returns partial data (best-effort).

Security: Table identifier components (catalog, schema, table, suffix) are
quoted with double quotes in the SQL passed to ``TrinoClient``.  The suffix
is also allowlisted to prevent injection via arbitrary suffix values.  All
constructed SQL goes through ``SqlClassifier.assert_read_only()`` inside
``TrinoClient`` before execution (T-02-13 mitigation).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp_trino_optimizer.adapters.trino.handle import TimeoutResult

if TYPE_CHECKING:
    from mcp_trino_optimizer.adapters.trino.client import TrinoClient

__all__ = ["LiveCatalogSource"]

# Allowlist of Iceberg metadata table suffixes (T-02-13 mitigation).
_ALLOWED_SUFFIXES: frozenset[str] = frozenset({"snapshots", "files", "manifests", "partitions", "history", "refs"})


class LiveCatalogSource:
    """CatalogSource via a live TrinoClient. Thin delegation wrapper.

    Args:
        client: Configured ``TrinoClient`` instance.
    """

    def __init__(self, client: TrinoClient) -> None:
        self._client = client

    async def fetch_iceberg_metadata(
        self,
        catalog: str,
        schema: str,
        table: str,
        suffix: str,
    ) -> list[dict[str, Any]]:
        """Fetch rows from an Iceberg metadata table.

        The ``suffix`` must be one of: ``snapshots``, ``files``, ``manifests``,
        ``partitions``, ``history``, ``refs``.  Providing an unknown suffix
        raises ``ValueError`` before any network call (T-02-13 mitigation).

        Args:
            catalog: Trino catalog name.
            schema: Schema name.
            table: Base table name (without the ``$`` suffix).
            suffix: Iceberg metadata table suffix.

        Returns:
            A list of row dicts.  May be partial on timeout.

        Raises:
            ValueError: If ``suffix`` is not in the allowlist.
        """
        if suffix not in _ALLOWED_SUFFIXES:
            raise ValueError(
                f"Unknown Iceberg metadata suffix {suffix!r}. Allowed suffixes: {sorted(_ALLOWED_SUFFIXES)}"
            )
        result = await self._client.fetch_iceberg_metadata(catalog, schema, table, suffix)
        if isinstance(result, TimeoutResult):
            return result.partial
        return result

    async def fetch_catalogs(self) -> list[str]:
        """Return all catalog names visible to the Trino connection.

        Issues ``SHOW CATALOGS`` via ``TrinoClient.fetch_system_runtime``.

        Returns:
            A list of catalog name strings.  Empty list on timeout.
        """
        result = await self._client.fetch_system_runtime("SHOW CATALOGS")
        rows = result.partial if isinstance(result, TimeoutResult) else result
        return [str(r.get("Catalog", r.get("catalog", ""))) for r in rows if isinstance(r, dict)]

    async def fetch_schemas(self, catalog: str) -> list[str]:
        """Return all schema names in the given catalog.

        Issues ``SHOW SCHEMAS IN "<catalog>"`` via ``TrinoClient.fetch_system_runtime``.
        The catalog name is double-quoted to prevent identifier injection.

        Args:
            catalog: Trino catalog name.

        Returns:
            A list of schema name strings.  Empty list on timeout.
        """
        result = await self._client.fetch_system_runtime(f'SHOW SCHEMAS IN "{catalog}"')
        rows = result.partial if isinstance(result, TimeoutResult) else result
        return [str(r.get("Schema", r.get("schema", ""))) for r in rows if isinstance(r, dict)]
