"""Embedded Trino session property data module (D-09).

Provides a curated set of session properties relevant to the rules in
the recommendation engine, along with a builder that produces ``SET SESSION``
statements gated on Trino version availability.

Property names come exclusively from this module -- never from user input
or evidence dicts (T-05-04).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel

if TYPE_CHECKING:
    pass


class _HasTrinoVersionMajor(Protocol):
    """Protocol for objects that expose trino_version_major."""

    @property
    def trino_version_major(self) -> int: ...


class SessionProperty(BaseModel):
    """A Trino session property with metadata for recommendation generation."""

    name: str
    """Property name as used in SET SESSION statements."""

    description: str
    """Human-readable description of what this property controls."""

    default: str
    """Default value in Trino."""

    valid_range: str | None = None
    """Human-readable description of valid values."""

    min_trino_version: int = 429
    """Minimum Trino version that supports this property."""

    category: str
    """Functional category (join, execution, optimizer)."""

    set_session_template: str
    """The exact SET SESSION statement to emit when this property is recommended."""


SESSION_PROPERTIES: dict[str, SessionProperty] = {
    "join_distribution_type": SessionProperty(
        name="join_distribution_type",
        description="Controls how joins distribute data across workers.",
        default="AUTOMATIC",
        valid_range="AUTOMATIC, BROADCAST, PARTITIONED",
        min_trino_version=429,
        category="join",
        set_session_template="SET SESSION join_distribution_type = 'PARTITIONED'",
    ),
    "join_max_broadcast_table_size": SessionProperty(
        name="join_max_broadcast_table_size",
        description="Maximum size of tables eligible for broadcast join.",
        default="100MB",
        valid_range="data size string (e.g. '100MB', '1GB')",
        min_trino_version=429,
        category="join",
        set_session_template="SET SESSION join_max_broadcast_table_size = '200MB'",
    ),
    "enable_dynamic_filtering": SessionProperty(
        name="enable_dynamic_filtering",
        description="Enable dynamic filtering for join operators.",
        default="true",
        valid_range="true, false",
        min_trino_version=429,
        category="join",
        set_session_template="SET SESSION enable_dynamic_filtering = true",
    ),
    "task_concurrency": SessionProperty(
        name="task_concurrency",
        description="Number of local parallel hash build partitions per worker.",
        default="16",
        valid_range="1-64",
        min_trino_version=429,
        category="execution",
        set_session_template="SET SESSION task_concurrency = 8",
    ),
    "join_reordering_strategy": SessionProperty(
        name="join_reordering_strategy",
        description="Strategy for join reordering optimization.",
        default="AUTOMATIC",
        valid_range="NONE, ELIMINATE_CROSS_JOINS, AUTOMATIC",
        min_trino_version=429,
        category="optimizer",
        set_session_template="SET SESSION join_reordering_strategy = 'AUTOMATIC'",
    ),
}
"""Curated set of session properties relevant to optimization rules."""


RULE_SESSION_PROPERTIES: dict[str, list[str]] = {
    "R4": ["enable_dynamic_filtering"],
    "R5": ["join_distribution_type", "join_max_broadcast_table_size"],
    "R6": ["join_reordering_strategy"],
    "R7": ["task_concurrency"],
    "R8": ["join_distribution_type"],
}
"""Maps rule_id to the session property names that rule may recommend changing."""


def build_set_session_statements(
    rule_id: str,
    capability_matrix: Any | None,
) -> list[str]:
    """Build SET SESSION statements for a rule, gated on Trino version.

    Args:
        rule_id: The rule whose session properties to look up.
        capability_matrix: An object with ``trino_version_major`` attribute,
            or ``None`` for offline mode.

    Returns:
        List of SET SESSION statements. Empty if the rule has no session
        properties. Advisory strings (prefixed with ``-- Advisory:``) are
        returned when capability_matrix is None or Trino version is too old.
    """
    prop_names = RULE_SESSION_PROPERTIES.get(rule_id)
    if not prop_names:
        return []

    statements: list[str] = []
    for name in prop_names:
        prop = SESSION_PROPERTIES.get(name)
        if prop is None:
            continue

        if capability_matrix is None:
            statements.append(
                f"-- Advisory: {prop.set_session_template} "
                f"(cannot verify property availability without live Trino connection)"
            )
        elif capability_matrix.trino_version_major < prop.min_trino_version:
            statements.append(
                f"-- Advisory: {prop.set_session_template} "
                f"(requires Trino >= {prop.min_trino_version}, "
                f"connected to {capability_matrix.trino_version_major})"
            )
        else:
            statements.append(prop.set_session_template)

    return statements


__all__ = [
    "RULE_SESSION_PROPERTIES",
    "SESSION_PROPERTIES",
    "SessionProperty",
    "build_set_session_statements",
]
