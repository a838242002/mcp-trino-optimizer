"""Offline adapters — no Trino cluster required.

Offline adapters accept pre-materialized EXPLAIN JSON from tool input and
return the same domain types as live adapters, keeping the rule/recommender/
rewrite engines mode-agnostic.
"""
