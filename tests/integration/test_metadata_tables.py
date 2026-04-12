"""Integration tests for Iceberg metadata table access (D-24 item 6, TRN-10).

Requires docker-compose stack to be running and test table seeded.
Run with:
    uv run pytest -m integration tests/integration/test_metadata_tables.py
"""

from __future__ import annotations

import pytest

from mcp_trino_optimizer.adapters.trino.client import TrinoClient
from mcp_trino_optimizer.adapters.trino.handle import TimeoutResult


@pytest.mark.integration
class TestMetadataTables:
    """Iceberg metadata table reads via TrinoClient.fetch_iceberg_metadata."""

    async def test_read_snapshots(
        self, trino_client: TrinoClient, seeded_stack: tuple[str, int]
    ) -> None:
        """$snapshots metadata table returns at least 1 entry after insert."""
        result = await trino_client.fetch_iceberg_metadata(
            "iceberg", "test_schema", "test_table", "snapshots"
        )
        assert not isinstance(result, TimeoutResult), "fetch_iceberg_metadata timed out"
        assert isinstance(result, list)
        assert len(result) >= 1, "Expected at least 1 snapshot after seeding"

    async def test_read_files(
        self, trino_client: TrinoClient, seeded_stack: tuple[str, int]
    ) -> None:
        """$files metadata table returns a list."""
        result = await trino_client.fetch_iceberg_metadata(
            "iceberg", "test_schema", "test_table", "files"
        )
        assert not isinstance(result, TimeoutResult), "fetch_iceberg_metadata timed out"
        assert isinstance(result, list)

    async def test_read_manifests(
        self, trino_client: TrinoClient, seeded_stack: tuple[str, int]
    ) -> None:
        """$manifests metadata table returns a list."""
        result = await trino_client.fetch_iceberg_metadata(
            "iceberg", "test_schema", "test_table", "manifests"
        )
        assert not isinstance(result, TimeoutResult), "fetch_iceberg_metadata timed out"
        assert isinstance(result, list)

    async def test_read_partitions(
        self, trino_client: TrinoClient, seeded_stack: tuple[str, int]
    ) -> None:
        """$partitions metadata table returns a list."""
        result = await trino_client.fetch_iceberg_metadata(
            "iceberg", "test_schema", "test_table", "partitions"
        )
        assert not isinstance(result, TimeoutResult), "fetch_iceberg_metadata timed out"
        assert isinstance(result, list)

    async def test_read_history(
        self, trino_client: TrinoClient, seeded_stack: tuple[str, int]
    ) -> None:
        """$history metadata table returns a list."""
        result = await trino_client.fetch_iceberg_metadata(
            "iceberg", "test_schema", "test_table", "history"
        )
        assert not isinstance(result, TimeoutResult), "fetch_iceberg_metadata timed out"
        assert isinstance(result, list)

    async def test_read_refs(
        self, trino_client: TrinoClient, seeded_stack: tuple[str, int]
    ) -> None:
        """$refs metadata table returns a list."""
        result = await trino_client.fetch_iceberg_metadata(
            "iceberg", "test_schema", "test_table", "refs"
        )
        assert not isinstance(result, TimeoutResult), "fetch_iceberg_metadata timed out"
        assert isinstance(result, list)

    async def test_read_system_runtime_queries(self, trino_client: TrinoClient) -> None:
        """system.runtime.queries is readable and returns a list."""
        result = await trino_client.fetch_system_runtime(
            "SELECT * FROM system.runtime.queries LIMIT 1"
        )
        assert not isinstance(result, TimeoutResult), "fetch_system_runtime timed out"
        assert isinstance(result, list)
