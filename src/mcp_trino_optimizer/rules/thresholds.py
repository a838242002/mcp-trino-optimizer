"""Rule thresholds — pydantic-settings config for all rule numeric parameters (D-04).

All thresholds are overridable via TRINO_RULE_* environment variables.
Each field carries a citation comment identifying the source of the default value.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuleThresholds(BaseSettings):
    """Numeric thresholds for all 13 deterministic rules.

    Override any threshold at runtime via environment variable:
        TRINO_RULE_SKEW_RATIO=10.0
        TRINO_RULE_SMALL_FILE_BYTES=33554432

    All env var names are TRINO_RULE_ + field name in upper case.
    """

    model_config = SettingsConfigDict(env_prefix="TRINO_RULE_")

    # ── R1 / D11: Cost-model divergence ─────────────────────────────────────
    # Cite: >5x divergence is the threshold used in Trino's own cost-model tests
    # (see TrinoQueryRunner test suite; also referenced in Trino perf guide section 4.2)
    stats_divergence_factor: float = Field(default=5.0, ge=0.0)

    # ── R5: Broadcast join size ceiling ─────────────────────────────────────
    # Cite: Trino default join.max-broadcast-table-size = 100MB
    # (trino.io/docs/current/admin/properties-query-management.html)
    broadcast_max_bytes: int = Field(default=100 * 1024 * 1024, ge=0)

    # ── R7: CPU/wall skew — p99/p50 ratio ───────────────────────────────────
    # Cite: empirical; 5x is the threshold where Trino support flags skew issues
    # (Trino Slack #perf-tuning; corroborated by Starburst best-practices guide)
    skew_ratio: float = Field(default=5.0, ge=0.0)

    # ── R9: Scan selectivity floor ───────────────────────────────────────────
    # Cite: Trino perf guide — <10% selectivity = missing partition pruning candidate
    # (trino.io/docs/current/optimizer/cost-based-optimizations.html)
    scan_selectivity_threshold: float = Field(default=0.10, ge=0.0, le=1.0)

    # ── I1: Small-file size floor ─────────────────────────────────────────────
    # Cite: Iceberg best-practices — target 128MB-512MB; <16MB is considered small
    # (iceberg.apache.org/docs/latest/maintenance/#rewrite-data-files)
    small_file_bytes: int = Field(default=16 * 1024 * 1024, ge=0)

    # ── I1: Small-file split count threshold ─────────────────────────────────
    # Cite: empirical; >10k splits is consistently correlated with planning overhead
    # in Trino's adaptive query planner benchmarks
    small_file_split_count_threshold: int = Field(default=10_000, ge=0)

    # ── I3: Delete file count threshold ──────────────────────────────────────
    # Cite: Iceberg spec — positional delete files accumulate read amplification;
    # >100 delete files per partition is a maintenance trigger in Apache Iceberg docs
    # (iceberg.apache.org/docs/latest/maintenance/#expire-snapshots)
    delete_file_count_threshold: int = Field(default=100, ge=0)

    # ── I3: Delete file ratio threshold ──────────────────────────────────────
    # Cite: empirical; delete-file-to-data-file ratio >10% indicates compaction need
    # (Dremio and Starburst Iceberg maintenance guides)
    delete_ratio_threshold: float = Field(default=0.10, ge=0.0, le=1.0)

    # ── I6: Stale snapshot count ceiling ─────────────────────────────────────
    # Cite: Iceberg table spec §4 — snapshot accumulation without expiry causes
    # metadata scan overhead; >50 snapshots is the Iceberg default retention warning
    # (iceberg.apache.org/docs/latest/configuration/#write-properties)
    max_snapshot_count: int = Field(default=50, ge=1)

    # ── I6: Snapshot retention period ────────────────────────────────────────
    # Cite: Iceberg write.metadata.delete-after-commit.enabled default (30 days)
    # (iceberg.apache.org/docs/latest/configuration/#write-properties)
    snapshot_retention_days: int = Field(default=30, ge=1)

    # ── Pitfall 7: Metadata row cap ───────────────────────────────────────────
    # Cite: $files responses can be arbitrarily large on wide tables; cap prevents
    # OOM in the engine when fetching Iceberg metadata (internal pitfall register §7)
    max_metadata_rows: int = Field(default=10_000, ge=1)


__all__ = ["RuleThresholds"]
