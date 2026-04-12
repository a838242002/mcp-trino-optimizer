"""Tests for recommender scoring module."""

from __future__ import annotations

import pytest


class TestSeverityWeights:
    """SEVERITY_WEIGHTS maps critical=4, high=3, medium=2, low=1."""

    def test_weights(self) -> None:
        from mcp_trino_optimizer.recommender.scoring import SEVERITY_WEIGHTS

        assert SEVERITY_WEIGHTS["critical"] == 4
        assert SEVERITY_WEIGHTS["high"] == 3
        assert SEVERITY_WEIGHTS["medium"] == 2
        assert SEVERITY_WEIGHTS["low"] == 1


class TestComputePriority:
    """compute_priority(severity, impact, confidence) = severity_weight * impact * confidence."""

    def test_critical_high_impact(self) -> None:
        from mcp_trino_optimizer.recommender.scoring import compute_priority

        result = compute_priority("critical", 0.8, 0.9)
        assert result == pytest.approx(4 * 0.8 * 0.9)
        assert result == pytest.approx(2.88)

    def test_low_medium_impact(self) -> None:
        from mcp_trino_optimizer.recommender.scoring import compute_priority

        result = compute_priority("low", 0.5, 0.5)
        assert result == pytest.approx(1 * 0.5 * 0.5)
        assert result == pytest.approx(0.25)

    def test_maximum_score(self) -> None:
        from mcp_trino_optimizer.recommender.scoring import compute_priority

        result = compute_priority("critical", 1.0, 1.0)
        assert result == pytest.approx(4.0)

    def test_minimum_score(self) -> None:
        from mcp_trino_optimizer.recommender.scoring import compute_priority

        result = compute_priority("low", 0.0, 0.0)
        assert result == pytest.approx(0.0)

    def test_medium_severity(self) -> None:
        from mcp_trino_optimizer.recommender.scoring import compute_priority

        result = compute_priority("medium", 0.6, 0.7)
        assert result == pytest.approx(2 * 0.6 * 0.7)

    def test_high_severity(self) -> None:
        from mcp_trino_optimizer.recommender.scoring import compute_priority

        result = compute_priority("high", 1.0, 0.5)
        assert result == pytest.approx(3 * 1.0 * 0.5)


class TestAssignTier:
    """assign_tier returns P1-P4 based on configurable thresholds."""

    def test_p1_at_threshold(self) -> None:
        from mcp_trino_optimizer.recommender.scoring import assign_tier

        assert assign_tier(2.4) == "P1"

    def test_p1_above_threshold(self) -> None:
        from mcp_trino_optimizer.recommender.scoring import assign_tier

        assert assign_tier(3.5) == "P1"

    def test_p2_at_threshold(self) -> None:
        from mcp_trino_optimizer.recommender.scoring import assign_tier

        assert assign_tier(1.2) == "P2"

    def test_p2_between(self) -> None:
        from mcp_trino_optimizer.recommender.scoring import assign_tier

        assert assign_tier(2.0) == "P2"

    def test_p3_at_threshold(self) -> None:
        from mcp_trino_optimizer.recommender.scoring import assign_tier

        assert assign_tier(0.5) == "P3"

    def test_p3_between(self) -> None:
        from mcp_trino_optimizer.recommender.scoring import assign_tier

        assert assign_tier(0.8) == "P3"

    def test_p4_below_threshold(self) -> None:
        from mcp_trino_optimizer.recommender.scoring import assign_tier

        assert assign_tier(0.49) == "P4"

    def test_p4_zero(self) -> None:
        from mcp_trino_optimizer.recommender.scoring import assign_tier

        assert assign_tier(0.0) == "P4"

    def test_custom_thresholds(self) -> None:
        from mcp_trino_optimizer.recommender.scoring import assign_tier

        # Custom thresholds: P1>=3.0, P2>=2.0, P3>=1.0
        assert assign_tier(3.0, thresholds=(3.0, 2.0, 1.0)) == "P1"
        assert assign_tier(2.5, thresholds=(3.0, 2.0, 1.0)) == "P2"
        assert assign_tier(1.5, thresholds=(3.0, 2.0, 1.0)) == "P3"
        assert assign_tier(0.5, thresholds=(3.0, 2.0, 1.0)) == "P4"


class TestSettingsRecommenderFields:
    """Settings accepts recommender fields."""

    def test_default_tier_thresholds(self) -> None:
        from mcp_trino_optimizer.settings import Settings

        s = Settings()
        assert s.recommender_tier_p1 == 2.4
        assert s.recommender_tier_p2 == 1.2
        assert s.recommender_tier_p3 == 0.5

    def test_default_top_n(self) -> None:
        from mcp_trino_optimizer.settings import Settings

        s = Settings()
        assert s.recommender_top_n_bottleneck == 5

    def test_custom_tier_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from mcp_trino_optimizer.settings import Settings

        monkeypatch.setenv("MCPTO_RECOMMENDER_TIER_P1", "3.0")
        monkeypatch.setenv("MCPTO_RECOMMENDER_TIER_P2", "2.0")
        monkeypatch.setenv("MCPTO_RECOMMENDER_TIER_P3", "1.0")
        monkeypatch.setenv("MCPTO_RECOMMENDER_TOP_N_BOTTLENECK", "10")
        s = Settings()
        assert s.recommender_tier_p1 == 3.0
        assert s.recommender_tier_p2 == 2.0
        assert s.recommender_tier_p3 == 1.0
        assert s.recommender_top_n_bottleneck == 10
