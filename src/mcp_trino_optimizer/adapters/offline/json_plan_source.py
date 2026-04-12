"""OfflinePlanSource — PlanSource implementation from raw EXPLAIN text.

This adapter is read-only-gate-exempt (D-15): it accepts a pre-materialized
EXPLAIN text string, not a SQL statement. There is no SQL to gate and no
network call is made. The live-adapter read-only gate is not applicable here.

Security note (T-02-05, T-03-01): enforces a 1MB size cap on raw input before
parsing to prevent memory exhaustion from adversarial payloads.

Phase 3: Updated to return EstimatedPlan/ExecutedPlan (typed domain objects)
instead of the old ExplainPlan placeholder. Parsing is delegated to the
parser subpackage.
"""

from __future__ import annotations

from mcp_trino_optimizer.parser import parse_estimated_plan, parse_executed_plan
from mcp_trino_optimizer.parser.models import EstimatedPlan, ExecutedPlan

# Maximum allowed size for raw plan input (1MB).
# Enforced before parsing to prevent memory exhaustion.
MAX_PLAN_BYTES = 1_000_000


class OfflinePlanSource:
    """PlanSource from raw text — no Trino connection needed.

    Satisfies the ``PlanSource`` Protocol (verified via runtime_checkable
    isinstance check in tests/adapters/test_port_conformance.py).

    Usage::

        source = OfflinePlanSource()
        plan = await source.fetch_plan(raw_json_text)
        analyzed = await source.fetch_analyze_plan(explain_analyze_text)
    """

    async def fetch_plan(self, sql: str) -> EstimatedPlan:
        """Parse ``sql`` as raw EXPLAIN (FORMAT JSON) text and return an EstimatedPlan.

        The ``sql`` parameter name follows the PlanSource Protocol signature,
        but for this adapter the value is the raw JSON text of an EXPLAIN plan,
        not a SQL statement.

        Args:
            sql: Raw JSON text from ``EXPLAIN (FORMAT JSON)`` output.

        Returns:
            EstimatedPlan with a typed PlanNode tree.
            ``source_trino_version=None`` (no cluster involved).

        Raises:
            ValueError: If the input exceeds 1MB or is empty.
            ParseError: If the JSON is invalid or wrong top-level structure.
        """
        self._validate_size(sql)
        return parse_estimated_plan(sql)

    async def fetch_analyze_plan(self, sql: str) -> ExecutedPlan:
        """Parse ``sql`` as raw EXPLAIN ANALYZE text and return an ExecutedPlan.

        EXPLAIN ANALYZE does NOT support FORMAT JSON (Trino grammar limitation).
        The ``sql`` parameter is the raw text output of EXPLAIN ANALYZE.

        Args:
            sql: Raw text from ``EXPLAIN ANALYZE`` output.

        Returns:
            ExecutedPlan with per-operator runtime metrics.
            ``source_trino_version=None`` (no cluster involved).

        Raises:
            ValueError: If the input exceeds 1MB.
        """
        self._validate_size(sql)
        return parse_executed_plan(sql)

    async def fetch_distributed_plan(self, sql: str) -> EstimatedPlan:
        """Parse ``sql`` as raw EXPLAIN (TYPE DISTRIBUTED, FORMAT JSON) text.

        Distributed plans are JSON format; parsed as EstimatedPlan.

        Args:
            sql: Raw JSON text from ``EXPLAIN (TYPE DISTRIBUTED, FORMAT JSON)``
                output.

        Returns:
            EstimatedPlan with stage/fragment distribution information.
            ``source_trino_version=None`` (no cluster involved).

        Raises:
            ValueError: If the input exceeds 1MB or is empty.
            ParseError: If the JSON is invalid or wrong top-level structure.
        """
        self._validate_size(sql)
        return parse_estimated_plan(sql)

    # ── Private helpers ───────────────────────────────────────────────────

    def _validate_size(self, text: str) -> None:
        """Raise ValueError if the input is empty or exceeds MAX_PLAN_BYTES.

        Encoding to UTF-8 before measuring ensures multi-byte characters are
        counted correctly.

        Args:
            text: The raw input text to measure.

        Raises:
            ValueError: If text is empty, or ``len(text.encode('utf-8')) > MAX_PLAN_BYTES``.
        """
        if not text.strip():
            raise ValueError("Invalid JSON: input is empty")
        byte_len = len(text.encode("utf-8"))
        if byte_len > MAX_PLAN_BYTES:
            raise ValueError(
                f"Plan JSON exceeds maximum size of {MAX_PLAN_BYTES} bytes "
                f"(got {byte_len} bytes). "
                "Paste a smaller plan or use live mode to fetch it directly."
            )
