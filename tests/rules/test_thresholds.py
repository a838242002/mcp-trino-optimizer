"""Parameterized threshold data-driven tests for RuleThresholds."""

import pytest

from mcp_trino_optimizer.rules.thresholds import RuleThresholds


def test_default_values_load_without_env() -> None:
    """RuleThresholds() loads all defaults without any env vars set."""
    t = RuleThresholds()
    assert t.skew_ratio == pytest.approx(5.0)
    assert t.broadcast_max_bytes == 100 * 1024 * 1024
    assert t.stats_divergence_factor == pytest.approx(5.0)
    assert t.scan_selectivity_threshold == pytest.approx(0.10)
    assert t.small_file_bytes == 16 * 1024 * 1024
    assert t.small_file_split_count_threshold == 10_000
    assert t.delete_file_count_threshold == 100
    assert t.delete_ratio_threshold == pytest.approx(0.10)
    assert t.max_snapshot_count == 50
    assert t.snapshot_retention_days == 30
    assert t.max_metadata_rows == 10_000


def test_env_override_skew_ratio(monkeypatch: pytest.MonkeyPatch) -> None:
    """TRINO_RULE_SKEW_RATIO env var overrides skew_ratio to 10.0."""
    monkeypatch.setenv("TRINO_RULE_SKEW_RATIO", "10.0")
    t = RuleThresholds()
    assert t.skew_ratio == pytest.approx(10.0)


def test_env_override_broadcast_max_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """TRINO_RULE_BROADCAST_MAX_BYTES env var overrides broadcast_max_bytes."""
    monkeypatch.setenv("TRINO_RULE_BROADCAST_MAX_BYTES", "52428800")  # 50MB
    t = RuleThresholds()
    assert t.broadcast_max_bytes == 52_428_800


def test_env_override_max_metadata_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """TRINO_RULE_MAX_METADATA_ROWS env var overrides max_metadata_rows."""
    monkeypatch.setenv("TRINO_RULE_MAX_METADATA_ROWS", "500")
    t = RuleThresholds()
    assert t.max_metadata_rows == 500


@pytest.mark.parametrize(
    "field_name, expected_default, citation_keyword",
    [
        # spot-check 3 thresholds against their documented citation values
        ("skew_ratio", 5.0, "empirical"),
        ("scan_selectivity_threshold", 0.10, "0.10"),
        ("delete_ratio_threshold", 0.10, "0.10"),
    ],
)
def test_threshold_defaults_match_citations(
    field_name: str, expected_default: float, citation_keyword: str
) -> None:
    """Spot-check that default values match their documented citation defaults."""
    t = RuleThresholds()
    actual = getattr(t, field_name)
    assert actual == pytest.approx(expected_default), (
        f"{field_name}: expected {expected_default}, got {actual}"
    )
