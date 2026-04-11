"""PLAT-12: README contains copy-pasteable mcpServers JSON for stdio,
Streamable HTTP, and Docker. CLAUDE.md and CONTRIBUTING.md exist at repo root.

`test_claude_md_exists` is a REGRESSION GUARD: CLAUDE.md exists today and
must keep existing. After plan 01-05 shipped the full README, every test
in this file is a real regression guard (xfail markers removed).
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).parents[2]


def test_claude_md_exists() -> None:
    """Regression guard — CLAUDE.md exists today and must keep existing."""
    assert (ROOT / "CLAUDE.md").exists()


def test_contributing_md_exists() -> None:
    """Regression guard — CONTRIBUTING.md shipped in plan 01-05."""
    assert (ROOT / "CONTRIBUTING.md").exists()


def _find_json_code_blocks(markdown: str) -> list[dict]:
    """Extract every ```json fenced code block from a markdown string and
    return only those that parse as JSON objects."""
    blocks: list[dict] = []
    for match in re.finditer(r"```json\s*\n(.*?)\n```", markdown, flags=re.DOTALL):
        body = match.group(1)
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            blocks.append(parsed)
    return blocks


def _find_code_blocks(markdown: str, lang: str | None = None) -> list[str]:
    """Return every fenced code block body matching the optional language tag."""
    pattern = r"```" + (lang if lang else r"\w*") + r"\s*\n(.*?)\n```"
    return [m.group(1) for m in re.finditer(pattern, markdown, flags=re.DOTALL)]


def test_readme_contains_stdio_mcp_servers_block() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    blocks = _find_json_code_blocks(readme)
    # Expect an mcpServers block whose server entry invokes mcp-trino-optimizer
    # with --transport stdio.
    found = False
    for block in blocks:
        servers = block.get("mcpServers") or {}
        for entry in servers.values():
            command = entry.get("command", "")
            args = entry.get("args", [])
            if "mcp-trino-optimizer" in command and "stdio" in " ".join(map(str, args)):
                found = True
                break
        if found:
            break
    assert found, "no stdio mcpServers block found in README"


def test_readme_contains_streamable_http_block() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    blocks = _find_json_code_blocks(readme)
    # Look for any mcpServers block whose server entry either declares
    # transport=http OR carries an explicit url with the /mcp suffix.
    # The current README documents HTTP via url+headers (not args), so
    # the args-based check used by earlier plans is no longer adequate.
    found = False
    for block in blocks:
        servers = block.get("mcpServers") or {}
        for entry in servers.values():
            if entry.get("transport") == "http":
                found = True
                break
            url = entry.get("url", "")
            if "/mcp" in url and url.startswith("http"):
                found = True
                break
        if found:
            break
    assert found, "no Streamable HTTP mcpServers block found in README"


def test_readme_contains_docker_block() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # Look for a `docker run` command block (bash or plain)
    blocks = _find_code_blocks(readme)
    found = any("docker run" in b for b in blocks)
    assert found, "no docker run block found in README"
