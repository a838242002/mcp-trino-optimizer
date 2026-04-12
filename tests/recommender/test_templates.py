"""Tests for recommender narrative templates (REC-03, T-05-03)."""

from __future__ import annotations

from typing import Any

import pytest

from mcp_trino_optimizer.recommender.templates import (
    TEMPLATES,
    render_recommendation,
)

ALL_RULE_IDS = [
    "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9",
    "I1", "I3", "I6", "I8", "D11",
]


class TestTemplatesDict:
    """TEMPLATES should have entries for all 14 rule_ids."""

    @pytest.mark.parametrize("rule_id", ALL_RULE_IDS)
    def test_template_exists(self, rule_id: str) -> None:
        assert rule_id in TEMPLATES
        template = TEMPLATES[rule_id]
        assert "reasoning" in template
        assert "expected_impact" in template
        assert "validation_steps" in template
        assert "risk_level" in template


class TestRenderRecommendation:
    """render_recommendation produces valid output for all rules."""

    def test_r1_basic_render(self) -> None:
        result = render_recommendation(
            "R1", {"operator_id": "0", "table_name": "orders"}
        )
        assert result["reasoning"]
        assert result["expected_impact"]
        assert result["validation_steps"]
        assert result["risk_level"]

    @pytest.mark.parametrize("rule_id", ALL_RULE_IDS)
    def test_all_rules_render_without_error(self, rule_id: str) -> None:
        """Every rule template renders without KeyError even with empty evidence."""
        result = render_recommendation(rule_id, {})
        assert isinstance(result, dict)
        assert "reasoning" in result
        assert "expected_impact" in result
        assert "validation_steps" in result
        assert "risk_level" in result

    def test_missing_evidence_keys_produce_na(self) -> None:
        """Missing evidence keys should produce 'N/A' fallback."""
        result = render_recommendation("R1", {})
        # Should contain N/A for missing placeholders
        assert "N/A" in result["reasoning"] or "N/A" in result["expected_impact"]

    def test_unknown_rule_id_returns_generic(self) -> None:
        """Unknown rule_id returns a generic fallback."""
        result = render_recommendation("UNKNOWN", {})
        assert result["reasoning"]
        assert result["risk_level"]


class TestPromptInjectionDefense:
    """T-05-03: Evidence values must not leak into narrative as executable text."""

    def test_no_injection(self) -> None:
        """SQL injection string in evidence must NOT appear in any rendered field."""
        malicious = "'; DROP TABLE users; --"
        evidence: dict[str, Any] = {
            "operator_id": malicious,
            "table_name": malicious,
            "partition_predicate": malicious,
            "function_name": malicious,
            "column_name": malicious,
        }
        result = render_recommendation("R1", evidence)
        for key in ("reasoning", "expected_impact", "validation_steps"):
            assert "DROP TABLE" not in result[key]
            assert "'" not in result[key] or "DROP" not in result[key]

    def test_no_injection_all_rules(self) -> None:
        """SQL injection attempt across all rules -- no rule leaks the string."""
        malicious = "'; DROP TABLE users; --"
        evidence: dict[str, Any] = {
            "operator_id": malicious,
            "table_name": malicious,
            "data_file_count": malicious,
            "median_file_size_bytes": malicious,
            "delete_file_count": malicious,
            "snapshot_count": malicious,
            "constraint_column": malicious,
            "divergence_factor": malicious,
            "distribution": malicious,
            "build_side_estimated_bytes": malicious,
            "p99_p50_ratio": malicious,
            "stage_id": malicious,
            "ratio": malicious,
            "selectivity": malicious,
            "function_name": malicious,
            "column_name": malicious,
            "partition_predicate": malicious,
        }
        for rule_id in ALL_RULE_IDS:
            result = render_recommendation(rule_id, evidence)
            for key in ("reasoning", "expected_impact", "validation_steps"):
                assert "DROP TABLE" not in result[key], (
                    f"Injection leaked in {rule_id}.{key}"
                )
