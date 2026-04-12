"""OfflinePlanSource — PlanSource implementation from raw EXPLAIN JSON text.

This adapter is read-only-gate-exempt (D-15): it accepts a pre-materialized
EXPLAIN JSON string, not a SQL statement. There is no SQL to gate and no
network call is made. The live-adapter read-only gate is not applicable here.

Security note (T-02-05): enforces a 1MB size cap on raw JSON input before
parsing to prevent memory exhaustion from adversarial payloads.
"""
from __future__ import annotations

from typing import Any, Literal

import orjson

from mcp_trino_optimizer.ports.plan_source import ExplainPlan

# Maximum allowed size for raw plan JSON input (1MB).
# Enforced before orjson.loads() to prevent memory exhaustion.
MAX_PLAN_BYTES = 1_000_000

# Runtime metric keys that indicate an EXPLAIN ANALYZE (executed) plan.
# If any of these keys appear in the top-level plan dict, the plan was
# produced by EXPLAIN ANALYZE rather than plain EXPLAIN.
_EXECUTED_PLAN_KEYS = frozenset(
    {
        "cpuTimeMillis",
        "wallTimeMillis",
        "processedRows",
        "processedBytes",
        "physicalWrittenBytes",
        "peakMemoryBytes",
    }
)


class OfflinePlanSource:
    """PlanSource from raw JSON text — no Trino connection needed.

    Satisfies the ``PlanSource`` Protocol (verified via runtime_checkable
    isinstance check in tests/adapters/test_port_conformance.py).

    Usage::

        source = OfflinePlanSource()
        plan = await source.fetch_plan(raw_json_text)
    """

    async def fetch_plan(self, sql: str) -> ExplainPlan:
        """Parse ``sql`` as raw EXPLAIN (FORMAT JSON) text and return an ExplainPlan.

        The ``sql`` parameter name follows the PlanSource Protocol signature,
        but for this adapter the value is the raw JSON text of an EXPLAIN plan,
        not a SQL statement.

        Args:
            sql: Raw JSON text from ``EXPLAIN (FORMAT JSON)`` output.

        Returns:
            ExplainPlan with ``plan_type`` auto-detected from the JSON content
            and ``source_trino_version=None`` (no cluster involved).

        Raises:
            ValueError: If the input exceeds 1MB, is empty, or is not valid JSON.
        """
        self._validate_size(sql)
        plan_dict = self._parse_json(sql)
        return ExplainPlan(
            plan_json=plan_dict,
            plan_type=self._detect_plan_type(plan_dict),
            source_trino_version=None,
            raw_text=sql,
        )

    async def fetch_analyze_plan(self, sql: str) -> ExplainPlan:
        """Parse ``sql`` as raw EXPLAIN ANALYZE (FORMAT JSON) text.

        Always returns ``plan_type="executed"`` regardless of JSON content,
        because the caller has indicated this is an EXPLAIN ANALYZE output.

        Args:
            sql: Raw JSON text from ``EXPLAIN ANALYZE (FORMAT JSON)`` output.

        Returns:
            ExplainPlan with ``plan_type="executed"`` and
            ``source_trino_version=None``.

        Raises:
            ValueError: If the input exceeds 1MB, is empty, or is not valid JSON.
        """
        self._validate_size(sql)
        plan_dict = self._parse_json(sql)
        return ExplainPlan(
            plan_json=plan_dict,
            plan_type="executed",
            source_trino_version=None,
            raw_text=sql,
        )

    async def fetch_distributed_plan(self, sql: str) -> ExplainPlan:
        """Parse ``sql`` as raw EXPLAIN (TYPE DISTRIBUTED, FORMAT JSON) text.

        Always returns ``plan_type="distributed"`` regardless of JSON content.

        Args:
            sql: Raw JSON text from ``EXPLAIN (TYPE DISTRIBUTED, FORMAT JSON)``
                output.

        Returns:
            ExplainPlan with ``plan_type="distributed"`` and
            ``source_trino_version=None``.

        Raises:
            ValueError: If the input exceeds 1MB, is empty, or is not valid JSON.
        """
        self._validate_size(sql)
        plan_dict = self._parse_json(sql)
        return ExplainPlan(
            plan_json=plan_dict,
            plan_type="distributed",
            source_trino_version=None,
            raw_text=sql,
        )

    # ── Private helpers ───────────────────────────────────────────────────

    def _validate_size(self, text: str) -> None:
        """Raise ValueError if the encoded byte length exceeds MAX_PLAN_BYTES.

        Encoding to UTF-8 before measuring ensures multi-byte characters are
        counted correctly.

        Args:
            text: The raw input text to measure.

        Raises:
            ValueError: If ``len(text.encode('utf-8')) > MAX_PLAN_BYTES``.
        """
        byte_len = len(text.encode("utf-8"))
        if byte_len > MAX_PLAN_BYTES:
            raise ValueError(
                f"Plan JSON exceeds maximum size of {MAX_PLAN_BYTES} bytes "
                f"(got {byte_len} bytes). "
                "Paste a smaller plan or use live mode to fetch it directly."
            )

    def _parse_json(self, text: str) -> dict[str, Any]:
        """Parse the raw JSON text using orjson.

        Args:
            text: JSON text to parse.

        Returns:
            Parsed dict.

        Raises:
            ValueError: If the text is not valid JSON or does not decode to a dict.
        """
        if not text.strip():
            raise ValueError("Invalid JSON: input is empty")
        try:
            result = orjson.loads(text)
        except orjson.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc
        if not isinstance(result, dict):
            raise ValueError(
                f"Invalid JSON: expected a JSON object (dict), got {type(result).__name__}"
            )
        return result

    def _detect_plan_type(
        self, plan_dict: dict[str, Any]
    ) -> Literal["estimated", "executed"]:
        """Heuristically detect whether a plan is estimated or executed.

        Checks the top-level JSON object for runtime metric keys that are
        only present in EXPLAIN ANALYZE output. If any of the known runtime
        keys appear, returns "executed"; otherwise "estimated".

        "distributed" plans are only returned via fetch_distributed_plan(),
        never by this heuristic.

        Args:
            plan_dict: The parsed plan JSON dict.

        Returns:
            ``"executed"`` if runtime metrics are detected, otherwise
            ``"estimated"``.
        """
        if _EXECUTED_PLAN_KEYS.intersection(plan_dict.keys()):
            return "executed"
        return "estimated"
