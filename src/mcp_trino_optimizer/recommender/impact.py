"""Impact extractor registry — stub for Task 1, fully implemented in Task 2."""

from __future__ import annotations

from typing import Any

DEFAULT_IMPACT: float = 0.5
"""Default impact score for rules without quantifiable evidence."""

_IMPACT_EXTRACTORS: dict[str, Any] = {}


def register_impact(rule_id: str) -> Any:
    """Decorator to register an impact extractor for a rule_id."""

    def decorator(func: Any) -> Any:
        _IMPACT_EXTRACTORS[rule_id] = func
        return func

    return decorator


def get_impact(rule_id: str, evidence: dict[str, Any]) -> float:
    """Look up and call the impact extractor for a rule_id.

    Returns DEFAULT_IMPACT if no extractor is registered.
    Result is clamped to [0.0, 1.0].
    """
    extractor = _IMPACT_EXTRACTORS.get(rule_id)
    if extractor is None:
        return DEFAULT_IMPACT
    try:
        result = float(extractor(evidence))
    except (TypeError, ValueError, ZeroDivisionError):
        return DEFAULT_IMPACT
    return max(0.0, min(1.0, result))


__all__ = [
    "DEFAULT_IMPACT",
    "get_impact",
    "register_impact",
]
