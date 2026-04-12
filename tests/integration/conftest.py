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
import time
from collections.abc import Generator
from typing import TYPE_CHECKING

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
def compose_stack() -> Generator[DockerCompose, None, None]:
    """Boot docker-compose stack, wait for Trino healthcheck, yield, teardown."""
    try:
        from testcontainers.compose import DockerCompose
    except ImportError:
        pytest.skip("testcontainers not installed — run: uv pip install -e '.[dev]'")
        return  # unreachable but satisfies type checker

    compose = DockerCompose(
        context=_get_testing_dir(),
        compose_file_name="docker-compose.yml",
    )
    compose.start()
    # Wait for Trino to respond (up to 120 seconds)
    compose.wait_for("http://localhost:8080/v1/info")
    # wait_for only checks HTTP 200; Trino still returns 200 while "starting": true.
    # Poll until starting=false or 120 s timeout.
    import urllib.request

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://localhost:8080/v1/info", timeout=5) as resp:
                import json as _json

                info = _json.loads(resp.read())
                if not info.get("starting", True):
                    break
        except Exception:
            pass
        time.sleep(2)
    else:
        pytest.fail("Trino did not finish initializing within 120 seconds")
    yield compose
    compose.stop()


@pytest.fixture(scope="session")
def trino_host(compose_stack: DockerCompose) -> tuple[str, int]:
    """Return (host, port) for the Trino service in the compose stack."""
    host = compose_stack.get_service_host("trino", 8080)
    port = compose_stack.get_service_port("trino", 8080)
    return host, int(port)


@pytest.fixture(scope="session")
def seeded_stack(trino_host: tuple[str, int]) -> tuple[str, int]:
    """Seed the Iceberg table once for the whole session; yield trino_host."""
    from tests.integration.fixtures import seed_iceberg_table

    host, port = trino_host
    seed_iceberg_table(host=host, port=port)
    return host, port


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
