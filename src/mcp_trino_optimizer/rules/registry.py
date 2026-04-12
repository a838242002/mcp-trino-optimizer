"""Rule registry — plugin registry for deterministic rules.

Rules are registered either as a decorator (@registry.register) or by an explicit
call (registry.register(RuleClass)). The module-level `registry` singleton is the
default registry used by RuleEngine.
"""

from __future__ import annotations

from mcp_trino_optimizer.rules.base import Rule


class RuleRegistry:
    """Registry of Rule subclasses.

    Provides register() as both a decorator and an explicit call.
    Duplicate registrations (same rule_id) silently overwrite.
    """

    def __init__(self) -> None:
        self._rules: dict[str, type[Rule]] = {}

    def register(self, rule_cls: type[Rule]) -> type[Rule]:
        """Register a Rule subclass. Returns the class unchanged (usable as @decorator).

        If a rule with the same rule_id is already registered, it is replaced.

        Args:
            rule_cls: A concrete subclass of Rule with rule_id and evidence_requirement.

        Returns:
            The rule class unchanged, so this method doubles as a class decorator.
        """
        self._rules[rule_cls.rule_id] = rule_cls
        return rule_cls

    def all_rules(self) -> list[type[Rule]]:
        """Return all registered Rule subclasses in registration order."""
        return list(self._rules.values())


registry = RuleRegistry()
"""Module-level singleton. Import and use @registry.register or registry.register(Cls)."""

__all__ = ["RuleRegistry", "registry"]
