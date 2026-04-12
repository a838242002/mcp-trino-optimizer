"""CatalogSource port — the hexagonal boundary for Iceberg catalog metadata retrieval.

This module is a pure Protocol definition. It MUST NOT import anything from
``mcp_trino_optimizer.adapters``. Rules that inspect Iceberg metadata (snapshot
count, file counts, partition stats) consume this port without coupling to a
specific catalog implementation.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CatalogSource(Protocol):
    """Port contract for querying Iceberg catalog and metadata tables.

    Implementations:
    - ``adapters.trino.live_catalog_source.LiveCatalogSource`` — issues
      read-only queries against Iceberg metadata tables
      (``$snapshots``, ``$files``, ``$partitions``, ``$manifests``) and
      Trino ``SHOW`` commands on a live cluster.

    All methods are ``async`` because live implementations bridge the sync
    trino-python-client via ``anyio.to_thread``.
    """

    async def fetch_iceberg_metadata(
        self,
        catalog: str,
        schema: str,
        table: str,
        suffix: str,
    ) -> list[dict[str, Any]]:
        """Fetch rows from an Iceberg metadata table.

        Queries ``SELECT * FROM <catalog>.<schema>."<table>$<suffix>"``
        where ``suffix`` is one of ``snapshots``, ``files``, ``partitions``,
        or ``manifests``.

        Args:
            catalog: Trino catalog name.
            schema: Schema name.
            table: Base table name (without the ``$`` suffix).
            suffix: Metadata table suffix (``snapshots``, ``files``,
                ``partitions``, or ``manifests``).

        Returns:
            A list of row dicts, each keyed by column name.
        """
        ...

    async def fetch_catalogs(self) -> list[str]:
        """Return all catalog names visible to the Trino connection.

        Issues ``SHOW CATALOGS`` and returns the catalog name column as a list.

        Returns:
            A list of catalog name strings.
        """
        ...

    async def fetch_schemas(self, catalog: str) -> list[str]:
        """Return all schema names in the given catalog.

        Issues ``SHOW SCHEMAS IN <catalog>`` and returns the schema name column
        as a list.

        Args:
            catalog: Trino catalog name.

        Returns:
            A list of schema name strings.
        """
        ...
