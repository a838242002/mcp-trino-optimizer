"""Tests for recommender session property data module (D-09)."""

from __future__ import annotations

from dataclasses import dataclass

from mcp_trino_optimizer.recommender.session_properties import (
    RULE_SESSION_PROPERTIES,
    SESSION_PROPERTIES,
    SessionProperty,
    build_set_session_statements,
)


@dataclass(frozen=True)
class _FakeCapabilityMatrix:
    """Minimal stub matching CapabilityMatrix.trino_version_major."""

    trino_version_major: int


class TestSessionPropertyModel:
    """SessionProperty validates name, description, default, etc."""

    def test_session_property_fields(self) -> None:
        prop = SessionProperty(
            name="test_prop",
            description="A test property",
            default="42",
            valid_range="1-100",
            min_trino_version=429,
            category="test",
            set_session_template="SET SESSION test_prop = 42",
        )
        assert prop.name == "test_prop"
        assert prop.description == "A test property"
        assert prop.default == "42"
        assert prop.valid_range == "1-100"
        assert prop.min_trino_version == 429
        assert prop.category == "test"


class TestSessionPropertiesDict:
    """SESSION_PROPERTIES should contain known session properties."""

    def test_join_distribution_type_present(self) -> None:
        assert "join_distribution_type" in SESSION_PROPERTIES

    def test_enable_dynamic_filtering_present(self) -> None:
        assert "enable_dynamic_filtering" in SESSION_PROPERTIES

    def test_task_concurrency_present(self) -> None:
        assert "task_concurrency" in SESSION_PROPERTIES

    def test_join_reordering_strategy_present(self) -> None:
        assert "join_reordering_strategy" in SESSION_PROPERTIES

    def test_join_max_broadcast_table_size_present(self) -> None:
        assert "join_max_broadcast_table_size" in SESSION_PROPERTIES


class TestRuleSessionProperties:
    """RULE_SESSION_PROPERTIES maps rules to their session properties."""

    def test_r4_maps_to_dynamic_filtering(self) -> None:
        assert "enable_dynamic_filtering" in RULE_SESSION_PROPERTIES["R4"]

    def test_r5_maps_to_join_distribution_and_broadcast(self) -> None:
        props = RULE_SESSION_PROPERTIES["R5"]
        assert "join_distribution_type" in props
        assert "join_max_broadcast_table_size" in props

    def test_r6_maps_to_join_reordering(self) -> None:
        assert "join_reordering_strategy" in RULE_SESSION_PROPERTIES["R6"]

    def test_r7_maps_to_task_concurrency(self) -> None:
        assert "task_concurrency" in RULE_SESSION_PROPERTIES["R7"]

    def test_r8_maps_to_join_distribution(self) -> None:
        assert "join_distribution_type" in RULE_SESSION_PROPERTIES["R8"]


class TestBuildSetSessionStatements:
    """build_set_session_statements with various capability scenarios."""

    def test_r5_with_cap_matrix_480(self) -> None:
        """R5 on Trino 480 => SET SESSION statements."""
        cap = _FakeCapabilityMatrix(trino_version_major=480)
        stmts = build_set_session_statements("R5", cap)
        assert any("SET SESSION join_distribution_type" in s for s in stmts)

    def test_r5_with_none_capability_matrix(self) -> None:
        """R5 offline => advisory-only statements."""
        stmts = build_set_session_statements("R5", None)
        assert len(stmts) > 0
        for s in stmts:
            assert s.startswith("-- Advisory:")

    def test_r5_with_old_trino_version(self) -> None:
        """R5 on old Trino below min_version => advisory-only."""
        # Create a property with high min_version to test
        cap = _FakeCapabilityMatrix(trino_version_major=400)
        stmts = build_set_session_statements("R5", cap)
        # Properties with min_trino_version=429 should be advisory on Trino 400
        for s in stmts:
            assert s.startswith("-- Advisory:")

    def test_r1_has_no_session_properties(self) -> None:
        """R1 is not in RULE_SESSION_PROPERTIES => empty list."""
        cap = _FakeCapabilityMatrix(trino_version_major=480)
        stmts = build_set_session_statements("R1", cap)
        assert stmts == []

    def test_r4_with_cap_matrix_480(self) -> None:
        """R4 on Trino 480 => SET SESSION for dynamic filtering."""
        cap = _FakeCapabilityMatrix(trino_version_major=480)
        stmts = build_set_session_statements("R4", cap)
        assert any("SET SESSION enable_dynamic_filtering" in s for s in stmts)
