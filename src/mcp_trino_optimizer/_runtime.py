"""Runtime info — package version, python version, git sha, transport, started_at.

Consumed by the mcp_selftest tool (plan 01-04) and the logging pipeline
(this plan) to populate the static fields every log line carries.

CRITICAL: _resolve_git_sha() must NEVER raise — see CONTEXT.md Claude's
Discretion and RESEARCH.md §11.2. Three-tier fallback:
  1. MCPTO_GIT_SHA env var (CI / Docker build arg)
  2. Baked _git_sha.txt file in the installed package (release builds)
  3. ``git rev-parse HEAD`` subprocess with 1s timeout (dev installs)
  4. Fallback: "unknown"
"""

from __future__ import annotations

import datetime as dt
import importlib.metadata
import importlib.resources
import os
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeInfo:
    package_version: str
    python_version: str
    git_sha: str
    log_level: str
    started_at: str
    transport: str


_started_at: str = dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
_transport: str = "unknown"


def set_transport(t: str) -> None:
    """Called by transports.run_stdio / run_streamable_http at startup."""
    global _transport
    _transport = t


def _resolve_git_sha() -> str:
    """Return the first git SHA we can find without raising.

    Three-tier fallback — always returns a string.
    """
    # Tier 1: env var
    sha = os.environ.get("MCPTO_GIT_SHA")
    if sha:
        return sha.strip()[:12]

    # Tier 2: baked file in package resources
    try:
        files = importlib.resources.files("mcp_trino_optimizer")
        sha_file = files.joinpath("_git_sha.txt")
        if sha_file.is_file():
            return sha_file.read_text(encoding="utf-8").strip()[:12]
    except (FileNotFoundError, ModuleNotFoundError, AttributeError, OSError):
        pass

    # Tier 3: runtime git rev-parse (dev installs)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()[:12]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # Tier 4: final fallback
    return "unknown"


def runtime_info(log_level: str = "INFO") -> RuntimeInfo:
    try:
        pv = importlib.metadata.version("mcp-trino-optimizer")
    except importlib.metadata.PackageNotFoundError:
        pv = "0.0.0-dev"
    return RuntimeInfo(
        package_version=pv,
        python_version=sys.version.split()[0],
        git_sha=_resolve_git_sha(),
        log_level=log_level,
        started_at=_started_at,
        transport=_transport,
    )


__all__ = ["RuntimeInfo", "runtime_info", "set_transport"]
