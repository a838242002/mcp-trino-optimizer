# Phase 5: Recommendation Engine - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md -- this log preserves the alternatives considered.

**Date:** 2026-04-13
**Phase:** 05-recommendation-engine
**Areas discussed:** Priority scoring formula, Conflict resolution, Template design, Session property source

---

## Priority Scoring Formula

| Option | Description | Selected |
|--------|-------------|----------|
| Numeric product (Recommended) | Map severity to numeric weight (critical=4, high=3, medium=2, low=1), multiply by confidence and impact. Priority = severity_weight x impact_score x confidence. | ✓ |
| Severity-first bucket sort | Group by severity tier first, sort within by confidence x impact. | |
| You decide | Claude picks the approach. | |

**User's choice:** Numeric product
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Evidence-based heuristic (Recommended) | Each rule declares an impact_extractor that pulls 0-1.0 from evidence dict. Default 0.5 for rules without quantifiable evidence. | ✓ |
| Severity equals impact | Skip separate impact. Use severity_weight x confidence only. | |
| You decide | Claude designs impact extraction. | |

**User's choice:** Evidence-based heuristic
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Both (Recommended) | Raw float for sorting + tier label (P1-P4) for readability. Thresholds configurable. | ✓ |
| Raw float only | Just the numeric score. | |
| Tiers only | P1/P2/P3/P4 labels only. | |

**User's choice:** Both
**Notes:** None

---

## Conflict Resolution

| Option | Description | Selected |
|--------|-------------|----------|
| Confidence-first (Recommended) | Higher confidence wins. On tie, higher severity wins. Loser kept as considered_but_rejected. | ✓ |
| Priority-score-first | Use computed priority score to pick winner. | |
| You decide | Claude designs conflict resolution. | |

**User's choice:** Confidence-first
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Declared conflicts (Recommended) | Each rule declares conflict_with rule_ids. Only declared pairs on same operator trigger resolution. | ✓ |
| Same-operator heuristic | Any two findings on same operator_id with different recommendations treated as conflicting. | |
| You decide | Claude picks the approach. | |

**User's choice:** Declared conflicts
**Notes:** None

---

## Template Design

| Option | Description | Selected |
|--------|-------------|----------|
| Python string templates (Recommended) | str.format() templates as constants in a templates module, keyed by rule_id. No Jinja dependency. | ✓ |
| Jinja2 templates | *.j2 template files. More powerful but adds dependency. | |
| Structured builders | Programmatic dataclass builders. Most type-safe but verbose. | |
| You decide | Claude picks based on complexity. | |

**User's choice:** Python string templates
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Structured model + template (Recommended) | Dedicated IcebergTableHealth pydantic model aggregating I1/I3/I6/I8, with template rendering. | ✓ |
| Inline in recommendations | Fold health data into each rule's recommendation text. | |
| You decide | Claude designs the format. | |

**User's choice:** Structured model + template
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Top 5 (Recommended) | Rank by wall/CPU time, take top 5. Configurable. | ✓ |
| Top 3 | More concise but may miss important operators. | |
| All with findings | Every operator with at least one finding. No fixed cap. | |

**User's choice:** Top 5
**Notes:** None

---

## Session Property Source

| Option | Description | Selected |
|--------|-------------|----------|
| Embedded data module (Recommended) | session_properties.py with dict of names, descriptions, ranges. Phase 8 wraps as MCP resource. | ✓ |
| JSON data file | session_properties.json loaded via importlib.resources. | |
| Port interface + stub | SessionPropertySource port ABC with in-memory impl. | |

**User's choice:** Embedded data module
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, with version gates (Recommended) | Each property includes min_trino_version. Recommender checks capability matrix. | ✓ |
| No, skip version gates | All properties assumed available. | |
| You decide | Claude decides based on capability matrix. | |

**User's choice:** Yes, with version gates
**Notes:** None

---

## Claude's Discretion

- Tie-breaking logic beyond confidence-then-severity
- Exact tier threshold values for P1/P2/P3/P4
- Internal module structure within recommender package
- Template wording for each rule_id's recommendation narrative

## Deferred Ideas

None -- discussion stayed within phase scope.
