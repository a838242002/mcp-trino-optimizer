"""MCP tool auto-registration (D-04).

tools/__init__.py.discover_and_register(mcp) walks every sibling module
under tools/ and calls each module's register(mcp) entry point. Adding
a new tool in a later phase = new file in tools/; nothing else changes.

Why a register() entry point instead of module-level @mcp.tool() decorators:
module-level decorators fire at import time and would require `mcp` to be
imported at the top of every tool module, creating a circular-import
hazard with app.py (see RESEARCH.md §3.1). The register() indirection
breaks the cycle by deferring mcp binding until runtime.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def discover_and_register(mcp: FastMCP) -> int:
    """Auto-discover every tool module in tools/ and call its register(mcp).

    Returns the number of tool modules successfully registered.

    Skips:
      - dunder modules (__init__, __main__)
      - private modules whose name starts with '_' (e.g. _middleware)

    A tool module is expected to expose a top-level ``register(mcp)``
    callable. Modules without one are silently ignored (helper modules).
    """
    registered = 0
    for _finder, name, _ispkg in pkgutil.iter_modules(__path__):
        if name.startswith("_"):
            continue
        module = importlib.import_module(f".{name}", package=__name__)
        register_fn = getattr(module, "register", None)
        if callable(register_fn):
            register_fn(mcp)
            registered += 1
    return registered


__all__ = ["discover_and_register"]
