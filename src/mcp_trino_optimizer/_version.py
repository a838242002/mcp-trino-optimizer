"""Static version for hatchling version plugin.

Rationale: CONTEXT.md Claude's Discretion requires git_sha fallback to
'unknown' outside a git checkout. A static version file is the simplest
wheel-install-clean guarantee (RESEARCH.md §8).
"""

__version__ = "0.1.0"
