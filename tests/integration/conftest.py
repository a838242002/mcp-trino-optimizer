"""Session-scoped integration test fixtures (D-22).

The compose_stack fixture boots the docker-compose stack in .testing/ and
waits for Trino to be healthy before yielding. The stack is torn down once
per pytest session.

All integration tests are marked with @pytest.mark.integration and are
skipped unless run with `pytest -m integration`.

testcontainers is imported lazily so that non-integration test runs (which
do not install all dev extras) do not fail at collection time.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Generator

import pytest

from mcp_trino_optimizer.adapters.trino.client import TrinoClient
from mcp_trino_optimizer.adapters.trino.pool import TrinoThreadPool
from mcp_trino_optimizer.settings import Settings

if TYPE_CHECKING:
    from testcontainers.compose import DockerCompose


def _get_testing_dir() -> str:
    testing_dir = os.path.join(os.path.dirname(__file__), "..", "..", ".testing")
    return os.path.abspath(testing_dir)


@pytest.fixture(scope="session")
def compose_stack() -> Generator["DockerCompose", None, None]:
    """Boot docker-compose stack, wait for Trino healthcheck, yield, teardown."""
    try:
        from testcontainers.compose import DockerCompose
    except ImportError:
        pytest.skip("testcontainers not installed — run: uv pip install -e '.[dev]'")
        return  # unreachable but satisfies type checker

    compose = DockerCompose(
        filepath=_get_testing_dir(),
        compose_file_name="docker-compose.yml",
    )
    compose.start()
    # Wait for Trino to be healthy (up to 120 seconds)
    compose.wait_for("http://localhost:8080/v1/info")
    yield compose
    compose.stop()


@pytest.fixture(scope="session")
def trino_host(compose_stack: "DockerCompose") -> tuple[str, int]:
    """Return (host, port) for the Trino service in the compose stack."""
    host = compose_stack.get_service_host("trino", 8080)
    port = compose_stack.get_service_port("trino", 8080)
    return host, int(port)


@pytest.fixture(scope="session")
def seeded_stack(trino_host: tuple[str, int]) -> Generator[tuple[str, int], None, None]:
    """Seed the Iceberg table once for the whole session; yield trino_host."""
    from tests.integration.fixtures import seed_iceberg_table

    host, port = trino_host
    seed_iceberg_table(host=host, port=port)
    yield host, port


@pytest.fixture
def trino_client(trino_host: tuple[str, int]) -> TrinoClient:
    """Create a TrinoClient pointing at the compose stack."""
    host, port = trino_host
    settings = Settings(
        trino_host=host,
        trino_port=port,
        trino_catalog="iceberg",
        trino_auth_mode="none",
        trino_verify_ssl=False,
    )
    pool = TrinoThreadPool(max_workers=settings.max_concurrent_queries)
    return TrinoClient(settings=settings, pool=pool)
