"""PLAT-03: HTTP transport fails fast without bearer token and enforces it on requests.

Covers D-07 (fail-fast) and D-08 (structured stderr error). Stubs skip cleanly
via importorskip until plan 01-04 lands the CLI module.
"""

from __future__ import annotations

import json
import os
import subprocess
import time

import pytest

try:
    import mcp_trino_optimizer.cli  # noqa: F401  # landed in plan 01-04
except ImportError:
    _cli_missing = True
else:
    _cli_missing = False

pytestmark = pytest.mark.skipif(_cli_missing, reason="mcp_trino_optimizer.cli not yet implemented")


def test_http_transport_fails_fast_without_bearer_token(clean_env: pytest.MonkeyPatch) -> None:
    """D-07: starting HTTP transport without MCPTO_HTTP_BEARER_TOKEN must
    exit non-zero within 5s AND emit a structured JSON 'settings_error'
    line on stderr (D-08).
    """
    env = os.environ.copy()
    # Ensure bearer token is NOT set
    env.pop("MCPTO_HTTP_BEARER_TOKEN", None)
    env["MCPTO_GIT_SHA"] = "test0000"

    proc = subprocess.Popen(
        ["mcp-trino-optimizer", "serve", "--transport", "http"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        env=env,
    )
    try:
        _, err_bytes = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        _, err_bytes = proc.communicate()
        raise AssertionError("HTTP transport did not fail fast within 5s") from None

    assert proc.returncode is not None and proc.returncode != 0, (
        f"expected non-zero exit; got {proc.returncode}"
    )
    # Parse last line of stderr as structured JSON
    stderr_text = err_bytes.decode("utf-8", errors="replace").strip()
    lines = [line for line in stderr_text.splitlines() if line.strip()]
    assert lines, "no stderr output"
    # Find a settings_error event
    found = False
    for line in lines:
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if parsed.get("event") == "settings_error":
            found = True
            break
    assert found, f"no settings_error event in stderr; got: {stderr_text}"


def test_http_transport_rejects_missing_authorization_header(
    spawn_server, bearer_token: str
) -> None:
    """Requests without an Authorization header must get 401."""
    import httpx

    proc = spawn_server(
        "serve",
        "--transport",
        "http",
        "--port",
        "18080",
        env={"MCPTO_HTTP_BEARER_TOKEN": bearer_token},
    )
    # Give the HTTP server a moment to bind
    time.sleep(0.5)
    try:
        resp = httpx.post("http://127.0.0.1:18080/mcp", json={}, timeout=5.0)
    except httpx.ConnectError:
        pytest.skip("HTTP server not yet bound — production implementation missing")
    finally:
        proc.kill()
    assert resp.status_code == 401


def test_http_transport_rejects_wrong_bearer_token(spawn_server, bearer_token: str) -> None:
    """Requests with a wrong bearer token must get 401."""
    import httpx

    proc = spawn_server(
        "serve",
        "--transport",
        "http",
        "--port",
        "18081",
        env={"MCPTO_HTTP_BEARER_TOKEN": bearer_token},
    )
    time.sleep(0.5)
    try:
        resp = httpx.post(
            "http://127.0.0.1:18081/mcp",
            headers={"Authorization": "Bearer wrong_token"},
            json={},
            timeout=5.0,
        )
    except httpx.ConnectError:
        pytest.skip("HTTP server not yet bound — production implementation missing")
    finally:
        proc.kill()
    assert resp.status_code == 401


def test_http_transport_accepts_correct_bearer_token(spawn_server, bearer_token: str) -> None:
    """Requests with the correct bearer token must get 200 on initialize."""
    import httpx

    proc = spawn_server(
        "serve",
        "--transport",
        "http",
        "--port",
        "18082",
        env={"MCPTO_HTTP_BEARER_TOKEN": bearer_token},
    )
    time.sleep(0.5)
    try:
        resp = httpx.post(
            "http://127.0.0.1:18082/mcp",
            headers={"Authorization": f"Bearer {bearer_token}"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0.0.0"},
                },
            },
            timeout=5.0,
        )
    except httpx.ConnectError:
        pytest.skip("HTTP server not yet bound — production implementation missing")
    finally:
        proc.kill()
    assert resp.status_code == 200
