"""SQL read-only gate — D-16, D-17, K-Decision #6.

SqlClassifier.assert_read_only(sql) is the security spine of the adapter
layer. Every call that touches Trino MUST call this first.

Design:
  - Uses sqlglot.parse(sql, dialect="trino") — NEVER regex.
  - AST allowlist covers: SELECT, CTEs (exp.Select with WITH clause),
    EXPLAIN/SHOW/DESCRIBE (exp.Command), USE, VALUES.
  - EXPLAIN inner SQL is re-parsed recursively; inner write statements
    are rejected even when wrapped in EXPLAIN ANALYZE.
  - Empty/whitespace input is rejected.
  - Multi-statement input (semicolon-separated) is rejected.
  - Comment-wrapped DDL is safe by construction: sqlglot strips comments
    before building the AST, so /* DROP TABLE t */ SELECT 1 is a SELECT.
  - Unicode tricks are neutralised during sqlglot tokenization.
"""

from __future__ import annotations

import re

import sqlglot
import sqlglot.expressions as exp

from mcp_trino_optimizer.adapters.trino.errors import TrinoClassifierRejected

__all__ = ["SqlClassifier", "TrinoClassifierRejected"]

# Node types that are unconditionally allowed at the top level.
_ALLOWED_NODE_TYPES: tuple[type[exp.Expression], ...] = (
    exp.Select,   # SELECT … (includes WITH/CTE prefix)
    exp.Describe, # DESCRIBE t
    exp.Use,      # USE catalog
    exp.Values,   # VALUES (…)
)

# Command keyword prefixes (case-insensitive) that are allowed.
# sqlglot parses EXPLAIN, SHOW, DESCRIBE (when not recognized), etc. as
# exp.Command nodes — we guard with an allowlist.
_ALLOWED_COMMAND_PREFIXES: frozenset[str] = frozenset(
    {"EXPLAIN", "SHOW", "DESCRIBE"}
)

# Regex to strip leading ANALYZE and parenthesised option groups from the
# expression part of an EXPLAIN command so we can re-parse the inner SQL.
# Examples handled:
#   "ANALYZE SELECT 1"                    → "SELECT 1"
#   "(FORMAT JSON) SELECT 1"             → "SELECT 1"
#   "(TYPE DISTRIBUTED) SELECT 1"        → "SELECT 1"
#   "ANALYZE (VERBOSE) SELECT 1"         → "SELECT 1"
_EXPLAIN_STRIP_RE = re.compile(
    r"""
    ^
    (?:ANALYZE\s+)?          # optional ANALYZE keyword
    (?:\([^)]*\)\s*)?        # optional parenthesised options e.g. (FORMAT JSON)
    """,
    re.IGNORECASE | re.VERBOSE,
)


class SqlClassifier:
    """Stateless read-only SQL classifier for the Trino adapter."""

    def assert_read_only(self, sql: str) -> None:
        """Raise TrinoClassifierRejected if *sql* is not a safe read-only statement.

        Safe statements: SELECT (including WITH/CTEs), EXPLAIN variants,
        SHOW variants, DESCRIBE, USE, VALUES.

        Args:
            sql: Raw SQL string from untrusted MCP tool input.

        Raises:
            TrinoClassifierRejected: Always, if the statement is not allowed.
        """
        stripped = sql.strip()
        if not stripped:
            raise TrinoClassifierRejected(
                "SQL statement is empty or whitespace-only. "
                "Only read-only statements are allowed."
            )

        try:
            statements = sqlglot.parse(stripped, dialect="trino")
        except Exception as exc:  # noqa: BLE001
            raise TrinoClassifierRejected(
                f"SQL could not be parsed: {exc}. Only valid read-only statements are allowed."
            ) from exc

        # Filter out None entries (sqlglot may emit None for blank tokens)
        non_none = [s for s in statements if s is not None]

        if len(non_none) == 0:
            raise TrinoClassifierRejected(
                "SQL statement is empty or produced no parse output. "
                "Only read-only statements are allowed."
            )

        if len(non_none) > 1:
            raise TrinoClassifierRejected(
                f"Multiple statements detected ({len(non_none)} statements separated by semicolons). "
                "Only a single read-only statement is allowed per call."
            )

        self._assert_node_allowed(non_none[0])

    def _assert_node_allowed(self, node: exp.Expr) -> None:
        """Assert a single parsed AST node is read-only."""
        if isinstance(node, _ALLOWED_NODE_TYPES):
            return

        if isinstance(node, exp.Command):
            self._assert_command_allowed(node)
            return

        # Everything else is a write/DDL/DML node → reject.
        node_type = type(node).__name__
        raise TrinoClassifierRejected(
            f"Statement type '{node_type}' is not allowed. "
            "Only read-only statements (SELECT, EXPLAIN, SHOW, DESCRIBE, USE, VALUES) are permitted."
        )

    def _assert_command_allowed(self, node: exp.Command) -> None:
        """Assert an exp.Command node is an allowed command (EXPLAIN/SHOW/DESCRIBE)."""
        cmd_name: str = (node.args.get("this") or "").upper().strip()

        if cmd_name not in _ALLOWED_COMMAND_PREFIXES:
            raise TrinoClassifierRejected(
                f"Command '{cmd_name}' is not allowed. "
                "Only EXPLAIN, SHOW, and DESCRIBE commands are permitted."
            )

        # For EXPLAIN commands, recursively validate the inner statement.
        if cmd_name == "EXPLAIN":
            self._assert_explain_inner_allowed(node)

    def _assert_explain_inner_allowed(self, node: exp.Command) -> None:
        """Extract and recursively validate the inner SQL of an EXPLAIN command."""
        raw = node.args.get("expression")
        if raw is None:
            expression = ""
        elif isinstance(raw, str):
            expression = raw.strip()
        elif isinstance(raw, exp.Literal):
            # sqlglot Command fallback stores the text in the Literal's `this` field
            expression = str(raw.args.get("this") or "").strip()
        else:
            # Other AST node — convert back to SQL text for re-parsing
            expression = raw.sql(dialect="trino").strip()

        # Strip "ANALYZE" and parenthesised option groups to get the raw inner SQL.
        inner_sql = _EXPLAIN_STRIP_RE.sub("", expression).strip()

        if not inner_sql:
            # EXPLAIN with no inner statement — allow (it will fail at Trino anyway)
            return

        # Re-parse the inner SQL and recursively classify.
        try:
            inner_statements = sqlglot.parse(inner_sql, dialect="trino")
        except Exception as exc:  # noqa: BLE001
            raise TrinoClassifierRejected(
                f"EXPLAIN inner SQL could not be parsed: {exc}"
            ) from exc

        inner_non_none = [s for s in inner_statements if s is not None]
        if not inner_non_none:
            return  # Empty inner → allow

        if len(inner_non_none) > 1:
            raise TrinoClassifierRejected(
                "EXPLAIN contains multiple inner statements. "
                "Only a single read-only statement is allowed."
            )

        # Recursively assert the inner node is read-only.
        self._assert_node_allowed(inner_non_none[0])
