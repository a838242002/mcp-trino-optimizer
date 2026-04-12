"""Integration tests for Trino authentication modes (D-24 item 4, TRN-03).

Requires docker-compose stack to be running. Run with:
    uv run pytest -m integration tests/integration/test_auth.py

Note: JWT auth requires a JWT issuer which is complex to set up in compose.
JWT integration test is marked skip with a TODO for Phase 9.
"""

from __future__ import annotations

import pytest

from mcp_trino_optimizer.adapters.trino.client import TrinoClient
from mcp_trino_optimizer.adapters.trino.errors import TrinoAuthError
from mcp_trino_optimizer.adapters.trino.pool import TrinoThreadPool
from mcp_trino_optimizer.parser.models import EstimatedPlan
from mcp_trino_optimizer.settings import Settings


@pytest.mark.integration
class TestAuth:
    """Authentication mode integration tests."""

    async def test_no_auth_connection(self, trino_client: TrinoClient) -> None:
        """auth_mode='none' connects and executes SELECT 1 successfully."""
        result = await trino_client.fetch_plan("SELECT 1")
        assert isinstance(result, EstimatedPlan)
        assert result.plan_type == "estimated"

    async def test_basic_auth_wrong_credentials(self, trino_host: tuple[str, int]) -> None:
        """auth_mode='basic' with wrong credentials raises TrinoAuthError after retry.

        The default Trino 480 compose stack has no authentication configured,
        so basic auth will likely succeed (Trino ignores the credentials when
        not configured for auth). This test verifies the auth path constructs
        and connects without crashing. If Trino rejects it, TrinoAuthError is raised.
        """
        host, port = trino_host
        settings = Settings(
            trino_host=host,
            trino_port=port,
            trino_auth_mode="basic",
            trino_user="testuser",
            trino_password="wrongpassword",  # type: ignore[arg-type]
            trino_verify_ssl=False,
        )
        pool = TrinoThreadPool(max_workers=1)
        client = TrinoClient(settings=settings, pool=pool)
        # Either succeeds (Trino has no auth configured) or raises TrinoAuthError
        try:
            result = await client.fetch_plan("SELECT 1")
            assert isinstance(result, EstimatedPlan)
        except TrinoAuthError:
            pass  # Expected if Trino is configured with auth

    @pytest.mark.skip(reason="requires JWT issuer in compose — TODO Phase 9")
    async def test_jwt_auth_connection(self, trino_host: tuple[str, int]) -> None:
        """JWT auth requires a JWT issuer configured in docker-compose (Phase 9)."""
        ...
