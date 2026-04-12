"""Tests for CapabilityMatrix, parse_trino_version, and probe_capabilities — TRN-07, D-18, D-19."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_trino_optimizer.adapters.trino.capabilities import (
    MINIMUM_TRINO_VERSION,
    CapabilityMatrix,
    parse_trino_version,
    probe_capabilities,
)
from mcp_trino_optimizer.adapters.trino.errors import TrinoVersionUnsupported

# ---------------------------------------------------------------------------
# parse_trino_version
# ---------------------------------------------------------------------------


def test_parse_trino_version_numeric() -> None:
    assert parse_trino_version("480") == 480


def test_parse_trino_version_with_suffix() -> None:
    assert parse_trino_version("480-e") == 480


def test_parse_trino_version_minimum() -> None:
    assert parse_trino_version("429") == 429


def test_parse_trino_version_non_numeric_raises() -> None:
    with pytest.raises(ValueError, match="Cannot parse Trino version"):
        parse_trino_version("abc")


def test_parse_trino_version_empty_raises() -> None:
    with pytest.raises(ValueError, match="Cannot parse Trino version"):
        parse_trino_version("")


# ---------------------------------------------------------------------------
# MINIMUM_TRINO_VERSION constant
# ---------------------------------------------------------------------------


def test_minimum_trino_version_value() -> None:
    assert MINIMUM_TRINO_VERSION == 429


# ---------------------------------------------------------------------------
# CapabilityMatrix dataclass
# ---------------------------------------------------------------------------


def test_capability_matrix_creation() -> None:
    now = datetime.now(UTC)
    matrix = CapabilityMatrix(
        trino_version="480",
        trino_version_major=480,
        catalogs=frozenset({"iceberg", "memory"}),
        iceberg_catalog_name="iceberg",
        iceberg_metadata_tables_available=True,
        probed_at=now,
    )
    assert matrix.trino_version == "480"
    assert matrix.trino_version_major == 480
    assert "iceberg" in matrix.catalogs
    assert matrix.iceberg_catalog_name == "iceberg"
    assert matrix.iceberg_metadata_tables_available is True
    assert matrix.probed_at == now


def test_capability_matrix_is_frozen() -> None:
    now = datetime.now(UTC)
    matrix = CapabilityMatrix(
        trino_version="429",
        trino_version_major=429,
        catalogs=frozenset({"memory"}),
        iceberg_catalog_name=None,
        iceberg_metadata_tables_available=False,
        probed_at=now,
    )
    with pytest.raises((AttributeError, TypeError)):
        matrix.trino_version = "999"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# probe_capabilities — mock-based tests
# ---------------------------------------------------------------------------


def _make_client(
    *,
    version_rows: list[dict],
    catalog_rows: list[dict],
    schema_rows: list[dict] | None = None,
    metadata_rows: list[dict] | None = None,
) -> MagicMock:
    """Build a minimal mock TrinoClient."""
    client = MagicMock()
    # fetch_system_runtime is called multiple times with different SQL.
    # We use side_effect to return appropriate data per call.
    call_responses: list[list[dict]] = [version_rows, catalog_rows]
    if schema_rows is not None:
        call_responses.append(schema_rows)
    if metadata_rows is not None:
        call_responses.append(metadata_rows)

    client.fetch_system_runtime = AsyncMock(side_effect=call_responses)
    return client


def _make_settings(*, trino_catalog: str = "iceberg") -> MagicMock:
    settings = MagicMock()
    settings.trino_catalog = trino_catalog
    return settings


@pytest.mark.asyncio
async def test_probe_raises_for_unsupported_version() -> None:
    client = _make_client(
        version_rows=[{"node_version": "428"}],
        catalog_rows=[],
    )
    settings = _make_settings()
    with pytest.raises(TrinoVersionUnsupported, match="428"):
        await probe_capabilities(client, settings)


@pytest.mark.asyncio
async def test_probe_succeeds_for_version_429() -> None:
    client = _make_client(
        version_rows=[{"node_version": "429"}],
        catalog_rows=[{"Catalog": "iceberg"}, {"Catalog": "memory"}],
        schema_rows=[{"Schema": "default"}],
        metadata_rows=[{"snapshot_id": 1}],
    )
    settings = _make_settings(trino_catalog="iceberg")
    matrix = await probe_capabilities(client, settings)
    assert matrix.trino_version_major == 429
    assert "iceberg" in matrix.catalogs


@pytest.mark.asyncio
async def test_probe_succeeds_for_version_480() -> None:
    client = _make_client(
        version_rows=[{"node_version": "480-e"}],
        catalog_rows=[{"Catalog": "iceberg"}, {"Catalog": "memory"}],
        schema_rows=[{"Schema": "default"}],
        metadata_rows=[{"snapshot_id": 1}],
    )
    settings = _make_settings(trino_catalog="iceberg")
    matrix = await probe_capabilities(client, settings)
    assert matrix.trino_version == "480-e"
    assert matrix.trino_version_major == 480
    assert matrix.iceberg_catalog_name == "iceberg"
    assert matrix.iceberg_metadata_tables_available is True


@pytest.mark.asyncio
async def test_probe_missing_iceberg_catalog_returns_none() -> None:
    client = _make_client(
        version_rows=[{"node_version": "480"}],
        catalog_rows=[{"Catalog": "memory"}, {"Catalog": "tpch"}],
    )
    settings = _make_settings(trino_catalog="iceberg")
    matrix = await probe_capabilities(client, settings)
    assert matrix.iceberg_catalog_name is None
    assert matrix.iceberg_metadata_tables_available is False
