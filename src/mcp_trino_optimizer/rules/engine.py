"""RuleEngine — async execution loop for all registered rules (D-05).

The engine:
1. Accepts StatsSource | None and CatalogSource | None (offline mode = None).
2. Prefetches evidence exactly once before running rules.
3. Skips rules whose evidence source is unavailable.
4. Isolates crashing rules: one exception -> RuleError, others continue.
5. Returns list[EngineResult] in rule registration order.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement
from mcp_trino_optimizer.rules.findings import EngineResult, RuleError, RuleSkipped
from mcp_trino_optimizer.rules.registry import RuleRegistry
from mcp_trino_optimizer.rules.registry import registry as _default_registry
from mcp_trino_optimizer.rules.thresholds import RuleThresholds

if TYPE_CHECKING:
    from mcp_trino_optimizer.parser.models import BasePlan
    from mcp_trino_optimizer.ports.catalog_source import CatalogSource
    from mcp_trino_optimizer.ports.stats_source import StatsSource

# Maximum character length for table_str before regex parsing (T-04-03 mitigation)
_TABLE_STR_MAX_LEN = 1000


class RuleEngine:
    """Async rule execution engine.

    Instantiate once per analysis; call run() with the plan and optional
    table reference to get all findings, errors, and skips.

    Args:
        stats_source: StatsSource implementation or None for offline mode.
        catalog_source: CatalogSource implementation or None for offline mode.
        thresholds: RuleThresholds config; defaults to env-driven instance.
        registry: RuleRegistry to use; defaults to the module-level singleton.
    """

    def __init__(
        self,
        stats_source: StatsSource | None,
        catalog_source: CatalogSource | None,
        thresholds: RuleThresholds | None = None,
        registry: RuleRegistry | None = None,
    ) -> None:
        self._stats_source = stats_source
        self._catalog_source = catalog_source
        self._thresholds = thresholds or RuleThresholds()
        self._registry = registry or _default_registry

    async def run(self, plan: BasePlan, table: str | None = None) -> list[EngineResult]:
        """Run all registered rules against the plan.

        Prefetches evidence once, then iterates all rules in registration order.
        Rules requiring unavailable evidence emit RuleSkipped. Crashing rules
        emit RuleError and execution continues.

        Args:
            plan: The plan tree to analyze (EstimatedPlan or ExecutedPlan).
            table: Optional explicit table reference 'catalog:schema.table'.
                   If None, the engine attempts to extract from the first scan node.

        Returns:
            list[EngineResult] — findings, errors, and skips in rule order.
        """
        evidence = await self._prefetch_evidence(plan, table)
        results: list[EngineResult] = []

        for rule_cls in self._registry.all_rules():
            rule = rule_cls()
            req = rule.evidence_requirement

            # Skip if required evidence source is unavailable
            if req == EvidenceRequirement.TABLE_STATS and self._stats_source is None:
                results.append(
                    RuleSkipped(
                        rule_id=rule.rule_id,
                        reason="offline_mode_no_stats_source",
                    )
                )
                continue

            if req == EvidenceRequirement.ICEBERG_METADATA and self._catalog_source is None:
                results.append(
                    RuleSkipped(
                        rule_id=rule.rule_id,
                        reason="offline_mode_no_catalog_source",
                    )
                )
                continue

            # Skip if rule needs execution metrics but plan is estimated-only
            if req == EvidenceRequirement.PLAN_WITH_METRICS and not _is_executed(plan):
                results.append(
                    RuleSkipped(
                        rule_id=rule.rule_id,
                        reason="requires_executed_plan_estimated_provided",
                    )
                )
                continue

            # Run the rule with full crash isolation
            try:
                findings = rule.check(plan, evidence)
                results.extend(findings)
            except Exception as exc:
                results.append(
                    RuleError(
                        rule_id=rule.rule_id,
                        error_type=type(exc).__name__,
                        message=str(exc),
                    )
                )

        return results

    async def _prefetch_evidence(self, plan: BasePlan, table: str | None) -> EvidenceBundle:
        """Fetch all required evidence exactly once.

        Collects the union of evidence requirements from registered rules,
        then fetches only what is needed and available.
        """
        bundle = EvidenceBundle(plan=plan)

        # Collect all evidence requirements from registered rules
        requirements = {rule_cls.evidence_requirement for rule_cls in self._registry.all_rules()}

        # Resolve table reference
        resolved_table = table or self._extract_table_from_plan(plan)

        # Prefetch table stats (once, even if multiple rules need it)
        if (
            EvidenceRequirement.TABLE_STATS in requirements
            and self._stats_source is not None
            and resolved_table is not None
        ):
            catalog, schema, tbl = self._parse_table_ref(resolved_table)
            if catalog and schema and tbl:
                bundle.table_stats = await self._stats_source.fetch_table_stats(catalog, schema, tbl)

        # Prefetch Iceberg metadata (once, even if multiple rules need it)
        if (
            EvidenceRequirement.ICEBERG_METADATA in requirements
            and self._catalog_source is not None
            and resolved_table is not None
        ):
            catalog, schema, tbl = self._parse_table_ref(resolved_table)
            if catalog and schema and tbl:
                raw_files = await self._catalog_source.fetch_iceberg_metadata(catalog, schema, tbl, "files")
                # Cap rows to prevent OOM on wide tables (Pitfall 7 / T-04-03)
                bundle.iceberg_files = raw_files[: self._thresholds.max_metadata_rows]
                bundle.iceberg_snapshots = await self._catalog_source.fetch_iceberg_metadata(
                    catalog, schema, tbl, "snapshots"
                )

        return bundle

    def _extract_table_from_plan(self, plan: BasePlan) -> str | None:
        """Extract the first scan node's table reference from plan descriptors."""
        for node in plan.walk():
            if node.operator_type in ("TableScan", "ScanFilter", "ScanFilterProject"):
                table_str = node.descriptor.get("table", "")
                if table_str:
                    return table_str
        return None

    def _parse_table_ref(self, table_str: str) -> tuple[str | None, str | None, str | None]:
        """Parse a Trino table descriptor string into (catalog, schema, table).

        Handles formats like:
          'iceberg:analytics.orders'
          'iceberg:analytics.orders$data@12345'
          'iceberg:analytics.orders constraint on [col]'

        T-04-03 mitigations:
          - Cap input at 1000 chars before regex to prevent catastrophic backtracking.
          - Use re.match() with anchored patterns (no unbounded backtracking).
          - Strip known variable-length suffixes before matching.

        Returns:
            (catalog, schema, table) or (None, None, None) on parse failure.
        """
        # T-04-03: cap before regex
        table_str = table_str[:_TABLE_STR_MAX_LEN]

        # Strip constraint suffix (variable length, must go first)
        table_str = re.sub(r"\s+constraint on \[.*", "", table_str, flags=re.DOTALL).strip()

        # Strip $<suffix>@<snapshotId> suffix
        table_str = re.sub(r"\$[^@\s]+@\S+", "", table_str).strip()

        # Parse catalog:schema.table
        match = re.match(r"^([^:]+):([^.]+)\.(.+)$", table_str)
        if match:
            return match.group(1), match.group(2), match.group(3)

        return None, None, None


def _is_executed(plan: BasePlan) -> bool:
    """Return True if plan is an ExecutedPlan (has runtime metrics)."""
    # Import here to avoid circular import; TYPE_CHECKING guard above handles mypy
    from mcp_trino_optimizer.parser.models import ExecutedPlan

    return isinstance(plan, ExecutedPlan)


__all__ = ["RuleEngine"]
