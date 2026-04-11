"""Verify the stdio transport writes ONLY valid JSON-RPC to stdout.

Covers PLAT-02 (stdio transport answers initialize) and PLAT-05 (stdout
discipline — only JSON-RPC frames). Runs on all 9 CI matrix cells
(Linux/macOS/Windows x 3.11/3.12/3.13).

Must use bytes mode (text=False) to avoid Windows encoding surprises.

Skipped in Wave 0 until plan 01-04 lands the CLI module; flips green
automatically once `mcp_trino_optimizer.cli` is importable.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest

try:
    import mcp_trino_optimizer.cli  # noqa: F401  # landed in plan 01-04
except ImportError:
    _cli_missing = True
else:
    _cli_missing = False

pytestmark = pytest.mark.skipif(_cli_missing, reason="mcp_trino_optimizer.cli not yet implemented")

INITIALIZE_FRAME = (
    json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "smoke-test", "version": "0.0.0"},
            },
        }
    )
    + "\n"
).encode("utf-8")


def test_stdio_initialize_produces_only_json_rpc_on_stdout():
    # Use the CLI entry point — this validates pyproject.toml [project.scripts]
    # AND the full startup path.
    env = os.environ.copy()
    env["MCPTO_LOG_LEVEL"] = "INFO"
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("MCPTO_GIT_SHA", "test0000")

    proc = subprocess.Popen(
        ["mcp-trino-optimizer", "serve", "--transport", "stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,  # unbuffered bytes mode
        env=env,
        # text=False implicit → bytes mode
    )
    try:
        assert proc.stdin is not None
        proc.stdin.write(INITIALIZE_FRAME)
        proc.stdin.flush()

        # Read until we get the response, with a 5s timeout
        out_bytes, err_bytes = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        out_bytes, err_bytes = proc.communicate()
    finally:
        if proc.poll() is None:
            proc.kill()

    # stdout MUST be composed entirely of JSON-RPC frames (one per line)
    assert out_bytes, f"no stdout produced; stderr was: {err_bytes.decode('utf-8', errors='replace')}"
    lines = out_bytes.decode("utf-8").splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as e:
            raise AssertionError(
                f"Non-JSON on stdout line {i}: {line!r}\nstderr: {err_bytes.decode('utf-8', errors='replace')}"
            ) from e
        assert parsed.get("jsonrpc") == "2.0", f"line {i} missing jsonrpc=2.0: {parsed}"

    # At least one response must be the initialize result
    responses = [json.loads(line) for line in lines if line.strip()]
    init_responses = [r for r in responses if r.get("id") == 1]
    assert init_responses, f"no response with id=1 found; responses: {responses}"
    assert "result" in init_responses[0], f"initialize response has no result: {init_responses[0]}"
