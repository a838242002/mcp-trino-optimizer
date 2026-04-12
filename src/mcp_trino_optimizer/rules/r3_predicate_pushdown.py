"""R3 PredicatePushdown — fires when a filter predicate wraps a column in a function,
preventing Trino from pushing the predicate into the storage layer.

When a filter like `date(ts) = '2025-01-15'` or `year(ts) = 2025` is present, Trino
cannot use the Iceberg partition spec or bloom filters to skip data — it must read all
files and evaluate the function row-by-row. Rewriting to a range predicate
(`ts >= ... AND ts < ...`) restores partition pruning and predicate pushdown.

Detection logic:
  - Find nodes with operator_type in (ScanFilter, ScanFilterProject, Filter).
  - Read descriptor.get("filterPredicate", "").
  - Primary: parse with sqlglot and walk AST for function-wrapped column references
    (exp.TsOrDsToDate / exp.Anonymous / exp.Cast / exp.Year / exp.Month / exp.Hour /
    exp.DateTrunc / exp.Trunc wrapping an exp.Column).
  - Fallback: regex pattern matching function names before '(' on the predicate string.
  - Confidence: 0.85 when sqlglot AST confirms; 0.6 for regex-only.
  - Threat T-04-06: always wrap sqlglot.parse_one in try/except; fall back to regex.

Evidence: PLAN_ONLY.
"""

from __future__ import annotations

import re

import sqlglot
import sqlglot.errors
from sqlglot import exp

from mcp_trino_optimizer.parser.models import BasePlan
from mcp_trino_optimizer.rules.base import Rule
from mcp_trino_optimizer.rules.evidence import EvidenceBundle, EvidenceRequirement
from mcp_trino_optimizer.rules.findings import RuleFinding
from mcp_trino_optimizer.rules.registry import registry

_FILTER_NODE_TYPES = frozenset({"ScanFilter", "ScanFilterProject", "Filter"})

# Function types whose presence wrapping a column indicates non-pushable predicate
_FUNCTION_EXPRESSION_TYPES = (
    exp.Date,  # date() function in Trino — sqlglot parses "date"(col) as exp.Date
    exp.TsOrDsToDate,  # alternative date conversion form
    exp.Anonymous,  # unknown/custom functions
    exp.Cast,
    exp.Year,
    exp.Month,
    exp.Hour,
    exp.DateTrunc,
    exp.Trunc,
    exp.Substring,
)

# Regex fallback — match common function names at word boundary before '('
_FUNCTION_REGEX = re.compile(
    r"\b(date|year|month|hour|cast|trunc|date_trunc|substring)\s*\(",
    re.IGNORECASE,
)


def _find_function_wrapped_columns_ast(
    predicate_str: str,
) -> list[str]:
    """Return function names that wrap column references in the predicate AST.

    Returns an empty list if parsing fails or no wrapped columns are found.
    """
    try:
        parsed = sqlglot.parse_one(predicate_str, dialect="trino", error_level=sqlglot.ErrorLevel.RAISE)
    except (sqlglot.errors.ParseError, Exception):
        return []

    found: list[str] = []
    for node in parsed.walk():
        if isinstance(node, _FUNCTION_EXPRESSION_TYPES):
            # Check if any direct or indirect argument is a Column
            has_column = any(
                isinstance(arg, exp.Column) for arg in node.args.values() if isinstance(arg, exp.Expression)
            )
            if not has_column:
                # Also check args as lists
                for arg in node.args.values():
                    if isinstance(arg, list):
                        for item in arg:
                            if isinstance(item, exp.Column):
                                has_column = True
                                break
            if has_column:
                func_name = node.sql_name() if hasattr(node, "sql_name") else type(node).__name__.lower()
                found.append(func_name)

    return found


def _find_function_wrapped_columns_regex(predicate_str: str) -> list[str]:
    """Return function names detected via regex fallback."""
    return [m.group(1).lower() for m in _FUNCTION_REGEX.finditer(predicate_str)]


class R3PredicatePushdown(Rule):
    """R3: Filter predicate contains function-wrapped columns that block pushdown.

    Fires when a filterPredicate in a scan node wraps a column in a function like
    date(), year(), cast(), or trunc(). These prevent Trino from using partition
    specs or bloom filters and force a full file scan.
    """

    rule_id = "R3"
    evidence_requirement = EvidenceRequirement.PLAN_ONLY

    def check(self, plan: BasePlan, evidence: EvidenceBundle) -> list[RuleFinding]:
        """Detect filter predicates with function-wrapped columns."""
        findings: list[RuleFinding] = []

        for node in plan.walk():
            if node.operator_type not in _FILTER_NODE_TYPES:
                continue

            predicate_str = node.descriptor.get("filterPredicate", "")
            if not predicate_str:
                continue

            # Primary: AST analysis
            ast_functions = _find_function_wrapped_columns_ast(predicate_str)

            if ast_functions:
                detected_functions = ast_functions
                confidence: float = 0.85
            else:
                # Fallback: regex
                regex_functions = _find_function_wrapped_columns_regex(predicate_str)
                if not regex_functions:
                    continue
                detected_functions = regex_functions
                confidence = 0.6

            findings.append(
                RuleFinding(
                    rule_id="R3",
                    severity="high",
                    confidence=confidence,
                    message=(
                        f"Filter predicate contains function-wrapped column(s) "
                        f"{detected_functions} which prevent predicate pushdown "
                        "and partition pruning."
                    ),
                    evidence={
                        "filter_predicate": predicate_str,
                        "detected_functions": detected_functions,
                        "operator_type": node.operator_type,
                    },
                    operator_ids=[node.id],
                )
            )

        return findings


registry.register(R3PredicatePushdown)
