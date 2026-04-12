"""Discriminated-union round-trip tests for RuleFinding, RuleError, RuleSkipped."""

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from mcp_trino_optimizer.rules.findings import (
    EngineResult,
    RuleError,
    RuleFinding,
    RuleSkipped,
)

_adapter: TypeAdapter[EngineResult] = TypeAdapter(EngineResult)  # type: ignore[type-arg]


def test_rule_finding_round_trip() -> None:
    """RuleFinding serializes and deserializes correctly via discriminated union."""
    finding = RuleFinding(
        rule_id="R1",
        severity="high",
        confidence=0.9,
        message="Missing table stats",
        evidence={"scan_node_id": "n1"},
        operator_ids=["n1"],
    )
    assert finding.kind == "finding"

    as_dict = json.loads(finding.model_dump_json())
    restored = _adapter.validate_python(as_dict)
    assert isinstance(restored, RuleFinding)
    assert restored.rule_id == "R1"
    assert restored.severity == "high"
    assert restored.confidence == pytest.approx(0.9)


def test_rule_error_round_trip() -> None:
    """RuleError serializes and deserializes correctly via discriminated union."""
    err = RuleError(rule_id="R7", error_type="ValueError", message="bad input")
    assert err.kind == "error"

    as_dict = json.loads(err.model_dump_json())
    restored = _adapter.validate_python(as_dict)
    assert isinstance(restored, RuleError)
    assert restored.error_type == "ValueError"
    assert restored.message == "bad input"


def test_rule_skipped_round_trip() -> None:
    """RuleSkipped serializes and deserializes correctly via discriminated union."""
    skip = RuleSkipped(rule_id="I3", reason="offline_mode_no_catalog_source")
    assert skip.kind == "skipped"

    as_dict = json.loads(skip.model_dump_json())
    restored = _adapter.validate_python(as_dict)
    assert isinstance(restored, RuleSkipped)
    assert restored.reason == "offline_mode_no_catalog_source"


def test_confidence_boundary_valid() -> None:
    """Confidence of 0.0 and 1.0 are valid boundaries."""
    f_min = RuleFinding(
        rule_id="R1",
        severity="low",
        confidence=0.0,
        message="min",
        evidence={},
        operator_ids=[],
    )
    assert f_min.confidence == 0.0

    f_max = RuleFinding(
        rule_id="R1",
        severity="low",
        confidence=1.0,
        message="max",
        evidence={},
        operator_ids=[],
    )
    assert f_max.confidence == 1.0


def test_confidence_out_of_range_raises() -> None:
    """Confidence > 1.0 must raise ValidationError."""
    with pytest.raises(ValidationError):
        RuleFinding(
            rule_id="R1",
            severity="low",
            confidence=1.01,
            message="bad",
            evidence={},
            operator_ids=[],
        )


def test_discriminated_union_list_deserialization() -> None:
    """A mixed list of finding/error/skipped dicts deserializes via discriminator."""
    list_adapter: TypeAdapter[list[EngineResult]] = TypeAdapter(list[EngineResult])  # type: ignore[type-arg]
    raw = [
        {"kind": "finding", "rule_id": "R1", "severity": "high", "confidence": 0.8,
         "message": "m", "evidence": {}, "operator_ids": []},
        {"kind": "error", "rule_id": "R7", "error_type": "KeyError", "message": "k"},
        {"kind": "skipped", "rule_id": "I3", "reason": "offline_mode_no_catalog_source"},
    ]
    results = list_adapter.validate_python(raw)
    assert len(results) == 3
    assert isinstance(results[0], RuleFinding)
    assert isinstance(results[1], RuleError)
    assert isinstance(results[2], RuleSkipped)
