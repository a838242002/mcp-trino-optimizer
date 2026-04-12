"""Tests for impact extractor registry and per-rule extractors."""

from __future__ import annotations

import pytest

from mcp_trino_optimizer.recommender.impact import DEFAULT_IMPACT, get_impact


class TestDefaultBehavior:
    """get_impact returns DEFAULT_IMPACT for unknown or missing rules."""

    def test_unknown_rule_returns_default(self) -> None:
        assert get_impact("UNKNOWN_RULE", {}) == DEFAULT_IMPACT

    def test_default_impact_value(self) -> None:
        assert DEFAULT_IMPACT == 0.5


class TestR1MissingStats:
    """R1: binary impact, always returns DEFAULT_IMPACT."""

    def test_empty_evidence(self) -> None:
        assert get_impact("R1", {}) == DEFAULT_IMPACT

    def test_with_evidence(self) -> None:
        assert get_impact("R1", {"estimated_row_count": 1000}) == DEFAULT_IMPACT


class TestR2PartitionPruning:
    """R2: no bytes evidence available from rule, returns DEFAULT_IMPACT."""

    def test_empty_evidence(self) -> None:
        # R2 evidence doesn't include bytes, so defaults to 0.5
        assert get_impact("R2", {}) == DEFAULT_IMPACT

    def test_with_evidence(self) -> None:
        assert get_impact("R2", {"filter_predicate": "x > 1"}) == DEFAULT_IMPACT


class TestR3PredicatePushdown:
    """R3: binary impact, always returns DEFAULT_IMPACT."""

    def test_empty_evidence(self) -> None:
        assert get_impact("R3", {}) == DEFAULT_IMPACT


class TestR4DynamicFiltering:
    """R4: fixed high impact (0.7)."""

    def test_empty_evidence(self) -> None:
        assert get_impact("R4", {}) == pytest.approx(0.7)


class TestR5BroadcastTooBig:
    """R5: build_side_estimated_bytes / threshold_bytes, capped at 1.0."""

    def test_double_threshold(self) -> None:
        result = get_impact(
            "R5",
            {"build_side_estimated_bytes": 200_000_000, "threshold_bytes": 100_000_000},
        )
        assert result == pytest.approx(1.0)

    def test_at_threshold(self) -> None:
        result = get_impact(
            "R5",
            {"build_side_estimated_bytes": 100_000_000, "threshold_bytes": 100_000_000},
        )
        assert result == pytest.approx(1.0)

    def test_half_threshold(self) -> None:
        result = get_impact(
            "R5",
            {"build_side_estimated_bytes": 50_000_000, "threshold_bytes": 100_000_000},
        )
        assert result == pytest.approx(0.5)

    def test_missing_keys(self) -> None:
        assert get_impact("R5", {}) == DEFAULT_IMPACT

    def test_zero_threshold(self) -> None:
        assert get_impact("R5", {"build_side_estimated_bytes": 100, "threshold_bytes": 0}) == DEFAULT_IMPACT


class TestR6JoinOrder:
    """R6: binary impact, always returns DEFAULT_IMPACT."""

    def test_empty_evidence(self) -> None:
        assert get_impact("R6", {}) == DEFAULT_IMPACT


class TestR7CpuSkew:
    """R7: (skew_ratio - 5.0) / 15.0, clamped [0, 1]."""

    def test_at_threshold(self) -> None:
        result = get_impact("R7", {"skew_ratio": 5.0})
        assert result == pytest.approx(0.0)

    def test_extreme(self) -> None:
        result = get_impact("R7", {"skew_ratio": 20.0})
        assert result == pytest.approx(1.0)

    def test_midpoint(self) -> None:
        result = get_impact("R7", {"skew_ratio": 12.5})
        assert result == pytest.approx(0.5)

    def test_missing_key(self) -> None:
        assert get_impact("R7", {}) == DEFAULT_IMPACT


class TestR8ExchangeVolume:
    """R8: (ratio - 1.0) / 9.0, clamped [0, 1]."""

    def test_no_waste(self) -> None:
        result = get_impact("R8", {"ratio": 1.0})
        assert result == pytest.approx(0.0)

    def test_extreme_waste(self) -> None:
        result = get_impact("R8", {"ratio": 10.0})
        assert result == pytest.approx(1.0)

    def test_midpoint(self) -> None:
        result = get_impact("R8", {"ratio": 5.5})
        assert result == pytest.approx(0.5)

    def test_missing_key(self) -> None:
        assert get_impact("R8", {}) == DEFAULT_IMPACT


class TestR9LowSelectivity:
    """R9: 1.0 - selectivity_ratio."""

    def test_low_selectivity(self) -> None:
        result = get_impact("R9", {"selectivity_ratio": 0.01})
        assert result == pytest.approx(0.99)

    def test_high_selectivity(self) -> None:
        result = get_impact("R9", {"selectivity_ratio": 0.9})
        assert result == pytest.approx(0.1)

    def test_missing_key(self) -> None:
        assert get_impact("R9", {}) == DEFAULT_IMPACT


class TestI1SmallFiles:
    """I1: 1.0 - min(1.0, median_file_size_bytes / threshold_bytes)."""

    def test_very_small_files(self) -> None:
        result = get_impact(
            "I1",
            {"median_file_size_bytes": 1_000_000, "threshold_bytes": 16_000_000},
        )
        # 1.0 - (1M / 16M) = 1.0 - 0.0625 = 0.9375
        assert result == pytest.approx(0.9375)

    def test_at_threshold(self) -> None:
        result = get_impact(
            "I1",
            {"median_file_size_bytes": 16_000_000, "threshold_bytes": 16_000_000},
        )
        assert result == pytest.approx(0.0)

    def test_above_threshold(self) -> None:
        result = get_impact(
            "I1",
            {"median_file_size_bytes": 32_000_000, "threshold_bytes": 16_000_000},
        )
        assert result == pytest.approx(0.0)

    def test_missing_keys(self) -> None:
        assert get_impact("I1", {}) == DEFAULT_IMPACT

    def test_zero_threshold(self) -> None:
        assert get_impact("I1", {"median_file_size_bytes": 100, "threshold_bytes": 0}) == DEFAULT_IMPACT


class TestI3DeleteFiles:
    """I3: min(1.0, delete_ratio / 0.5)."""

    def test_high_ratio(self) -> None:
        result = get_impact("I3", {"delete_ratio": 0.5})
        assert result == pytest.approx(1.0)

    def test_low_ratio(self) -> None:
        result = get_impact("I3", {"delete_ratio": 0.1})
        assert result == pytest.approx(0.2)

    def test_extreme_ratio(self) -> None:
        result = get_impact("I3", {"delete_ratio": 1.0})
        assert result == pytest.approx(1.0)

    def test_missing_key(self) -> None:
        assert get_impact("I3", {}) == DEFAULT_IMPACT


class TestI6StaleSnapshots:
    """I6: min(1.0, snapshot_count / (threshold_count * 5))."""

    def test_at_5x_threshold(self) -> None:
        result = get_impact("I6", {"snapshot_count": 500, "threshold_count": 100})
        assert result == pytest.approx(1.0)

    def test_at_threshold(self) -> None:
        result = get_impact("I6", {"snapshot_count": 100, "threshold_count": 100})
        assert result == pytest.approx(0.2)

    def test_extreme(self) -> None:
        result = get_impact("I6", {"snapshot_count": 1000, "threshold_count": 100})
        assert result == pytest.approx(1.0)

    def test_missing_keys(self) -> None:
        assert get_impact("I6", {}) == DEFAULT_IMPACT

    def test_zero_threshold(self) -> None:
        assert get_impact("I6", {"snapshot_count": 100, "threshold_count": 0}) == DEFAULT_IMPACT


class TestI8PartitionTransform:
    """I8: binary impact (confidence already low at 0.6)."""

    def test_empty_evidence(self) -> None:
        assert get_impact("I8", {}) == DEFAULT_IMPACT


class TestD11CostVsActual:
    """D11: (divergence_factor - 5.0) / 45.0, clamped [0, 1]."""

    def test_extreme_divergence(self) -> None:
        result = get_impact("D11", {"divergence_factor": 50.0})
        assert result == pytest.approx(1.0)

    def test_at_threshold(self) -> None:
        result = get_impact("D11", {"divergence_factor": 5.0})
        assert result == pytest.approx(0.0)

    def test_midpoint(self) -> None:
        result = get_impact("D11", {"divergence_factor": 27.5})
        assert result == pytest.approx(0.5)

    def test_missing_key(self) -> None:
        assert get_impact("D11", {}) == DEFAULT_IMPACT


class TestEdgeCases:
    """Edge cases: None values, NaN, zero denominators."""

    def test_none_value_in_evidence(self) -> None:
        """None denominator values should not cause division by zero."""
        assert get_impact("R5", {"build_side_estimated_bytes": None, "threshold_bytes": 100}) == DEFAULT_IMPACT

    def test_nan_value_in_evidence(self) -> None:
        assert get_impact("R7", {"skew_ratio": float("nan")}) == DEFAULT_IMPACT

    def test_result_clamped_to_zero(self) -> None:
        """Negative intermediate results should be clamped to 0.0."""
        result = get_impact("R7", {"skew_ratio": 1.0})
        assert result == 0.0

    def test_result_clamped_to_one(self) -> None:
        """Values above 1.0 should be clamped to 1.0."""
        result = get_impact("R7", {"skew_ratio": 100.0})
        assert result == 1.0


class TestRegistryCompleteness:
    """All 14 rules have registered extractors."""

    def test_all_14_rules_registered(self) -> None:
        from mcp_trino_optimizer.recommender.impact import _IMPACT_EXTRACTORS

        expected_rules = {
            "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9",
            "I1", "I3", "I6", "I8", "D11",
        }
        assert set(_IMPACT_EXTRACTORS.keys()) == expected_rules
