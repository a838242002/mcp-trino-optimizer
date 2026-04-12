"""Integration tests for Trino capability probing (D-24 item 5, TRN-07, TRN-08, TRN-14).

Requires docker-compose stack to be running. Run with:
    uv run pytest -m integration tests/integration/test_capabilities.py
"""

from __future__ import annotations

import pytest

from mcp_trino_optimizer.adapters.trino.capabilities import (
    CapabilityMatrix,
    probe_capabilities,
)
from mcp_trino_optimizer.adapters.trino.client import TrinoClient


@pytest.mark.integration
class TestCapabilities:
    """Capability matrix probing against real Trino 480 + Lakekeeper stack."""

    async def test_probe_capabilities_trino_480(self, trino_client: TrinoClient) -> None:
        """probe_capabilities detects Trino 480 and the iceberg catalog."""
        from mcp_trino_optimizer.settings import Settings

        settings = trino_client._settings
        matrix = await probe_capabilities(trino_client, settings)

        assert isinstance(matrix, CapabilityMatrix)
        assert matrix.trino_version_major == 480, (
            f"Expected Trino 480, got {matrix.trino_version_major} "
            f"(version_str={matrix.trino_version!r})"
        )
        assert "iceberg" in matrix.catalogs, (
            f"Expected 'iceberg' in catalogs, got {matrix.catalogs!r}"
        )
        assert matrix.iceberg_catalog_name == "iceberg", (
            f"Expected iceberg_catalog_name='iceberg', got {matrix.iceberg_catalog_name!r}"
        )

    async def test_iceberg_metadata_tables_available(
        self, trino_client: TrinoClient, seeded_stack: tuple[str, int]
    ) -> None:
        """Iceberg metadata tables are available after the test table is seeded."""
        settings = trino_client._settings
        matrix = await probe_capabilities(trino_client, settings)

        assert matrix.iceberg_metadata_tables_available is True, (
            "Expected iceberg_metadata_tables_available=True after seeding test table"
        )

    async def test_capability_matrix_is_immutable(self, trino_client: TrinoClient) -> None:
        """CapabilityMatrix is a frozen dataclass — attribute assignment raises FrozenInstanceError."""
        import dataclasses

        settings = trino_client._settings
        matrix = await probe_capabilities(trino_client, settings)

        with pytest.raises(dataclasses.FrozenInstanceError):
            matrix.trino_version = "999"  # type: ignore[misc]
