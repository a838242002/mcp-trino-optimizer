---
phase: 01-skeleton-safety-foundation
plan: 06
subsystem: infra
tags: [ci, github-actions, pre-commit, ruff, mypy, windows-compat, test-matrix]

requires:
  - phase: 01-04
    provides: "Working CLI + test suite for CI to exercise"
  - phase: 01-05
    provides: "Dockerfile and README referenced by CI docs checks"
provides:
  - ".github/workflows/ci.yml — 3 jobs (lint-types, unit-smoke 9-cell matrix, integration stub)"
  - ".pre-commit-config.yaml — ruff format + ruff check + mypy strict + hygiene hooks"
  - "PLAT-01 dual install-path coverage (uv pip install -e + uv tool install)"
  - "PLAT-13 9-cell (3 OS × 3 Python) test matrix"
affects: [all future phases]

tech-stack:
  added:
    - "GitHub Actions CI with astral-sh/setup-uv@v4"
    - "pre-commit hooks: pre-commit-hooks v5.0.0, astral-sh/ruff-pre-commit v0.15.10, mirrors-mypy v1.11.2"
  patterns:
    - "Every CI run step declares shell: bash explicitly (Windows default cmd breaks uv venv + pipes)"
    - "MCPTO_GIT_SHA + PYTHONUNBUFFERED env vars on every test step so runtime_info reflects the commit and stdio frames flush"
    - "fail-fast: false on matrix so one cell failure doesn't mask others; concurrency group cancels stale runs"
    - "mypy pre-commit hook scoped to ^src/ with explicit additional_dependencies for isolated env type resolution"
    - "mixed-line-ending --fix=lf in pre-commit complements .gitattributes (belt-and-suspenders CRLF protection)"

key-files:
  created:
    - ".github/workflows/ci.yml"
    - ".pre-commit-config.yaml"
  modified: []

key-decisions:
  - "integration job stubbed with 'if: false' rather than a branch/path condition — Phase 2+ flips the flag to a real condition without restructuring the workflow"
  - "Explicit 'Stdio cleanliness smoke test' and 'HTTP bearer smoke test' steps (not just rolled into the unit pytest invocation) so CI logs make the PLAT-05 and PLAT-03 guarantees traceable on every matrix cell"
  - "Both PLAT-01 install paths exercised: uv pip install -e .[dev] in the main step, uv tool install . + uv tool run in a dedicated step so each path is independently covered"
  - "astral-sh/setup-uv@v4 chosen over manual actions/setup-python + pip install — the uv action manages Python version + uv binary + cache across all three runners"
  - "mypy pre-commit hook files: '^src/' (not tests/) to keep commit-time feedback fast; CI runs mypy strict on src/ separately in lint-types"
  - "pre-commit mypy additional_dependencies lists every runtime dep that provides type stubs (pydantic, pydantic-settings, structlog, mcp, typer, types-orjson) so the hook's isolated env can resolve imports"

patterns-established:
  - "CI workflow as the authoritative validation surface: every PR must pass 9 cells + 1 lint cell to be mergeable"
  - "Pre-commit as the developer-facing enforcement layer; CI is the PR-facing enforcement layer; CONTRIBUTING.md DoD enumerates both"

requirements-completed:
  - PLAT-01
  - PLAT-13

duration: ~10min
completed: 2026-04-11
---

# Phase 01 Plan 06: CI + Pre-commit Summary

**GitHub Actions CI with 9-cell install matrix (Linux/macOS/Windows × Python 3.11/3.12/3.13), dual install-path coverage (uv pip install -e AND uv tool install), explicit stdio + HTTP smoke test steps per cell, and a pre-commit config enforcing ruff format/check + mypy strict + hygiene hooks. PLAT-01 and PLAT-13 closed; Phase 1 is ready for verification.**

## Performance

- **Duration:** ~10 min
- **Completed:** 2026-04-11
- **Tasks:** 2 (ci.yml + .pre-commit-config.yaml)
- **Files created:** 2

## Accomplishments

- `.github/workflows/ci.yml` has three jobs:
  - **lint-types** (Linux / Python 3.12): ruff format check → ruff check → mypy src strict
  - **unit-smoke** (3 OS × 3 Python = 9 cells): pip install -e path → pytest → stdio smoke → HTTP bearer smoke → CLI --help → uv tool install path
  - **integration** (stubbed with `if: false`): Phase 2+ flips the flag to run the testcontainers-based suite without restructuring
- Every `run:` step declares `shell: bash` explicitly so Windows runners don't fall back to `cmd` (which breaks `uv venv` and pipe syntax)
- `MCPTO_GIT_SHA: ${{ github.sha }}` + `PYTHONUNBUFFERED: "1"` on every test step
- `fail-fast: false` on the matrix so one cell's failure doesn't mask the others
- `concurrency:` group cancels in-progress runs on the same ref to save CI minutes
- `.pre-commit-config.yaml` has three repo groups:
  - pre-commit-hooks v5.0.0 (trailing-whitespace, end-of-file-fixer, check-merge-conflict, check-yaml, check-toml, check-added-large-files --maxkb=500, detect-private-key, check-case-conflict, mixed-line-ending --fix=lf)
  - astral-sh/ruff-pre-commit v0.15.10 (ruff-check --fix --exit-non-zero-on-fix, ruff-format) — pin matches CLAUDE.md exactly
  - mirrors-mypy v1.11.2 (mypy --strict on `^src/` with explicit additional_dependencies)
- Both YAML files parse cleanly via `yaml.safe_load`
- 9-cell matrix confirmed programmatically (`len(os) * len(python) == 9`)
- Full test suite still 61 passed, 0 skipped, mypy strict clean, ruff clean after plan lands

## Task Commits

1. **Task 1 + 2: ci.yml + .pre-commit-config.yaml** — `7a65e3f` (feat) — committed together since both files are small YAML and share no code path

## Files Created/Modified

- `.github/workflows/ci.yml` — 3-job GitHub Actions pipeline with 9-cell PLAT-13 matrix
- `.pre-commit-config.yaml` — ruff + mypy + hygiene hooks

## Decisions Made

- See key-decisions frontmatter for the full list.
- Headline calls: integration stubbed with `if: false`, both PLAT-01 install paths exercised in the same job, astral-sh/setup-uv@v4 over manual setup-python, mypy pre-commit scoped to `^src/` with explicit additional_dependencies.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- **mypy pre-commit additional_dependencies drift risk.** Pinning runtime deps separately from pyproject.toml risks drift. Accepted as the cost of having mypy run in an isolated environment; the list is short enough that a CI-enforced sync check could be added in a later phase if needed.

## User Setup Required

None. First developer on the repo can run `uv run pre-commit install` to activate the hooks.

## Next Phase Readiness

- Phase 1 is fully implemented at the source level (6 plans complete: scaffold → safety primitives → runtime/logging/settings → app/tools/transports/cli → docker/docs → ci/pre-commit)
- All PLAT-01..PLAT-13 requirements are closed
- Full test suite: 61 passed, 0 skipped, 0 xfailed, 0 errors
- `mcp-trino-optimizer serve` works end-to-end for both stdio and HTTP transports
- Phase 1 is ready for `gsd-verifier` verification and phase-completion marking

---
*Phase: 01-skeleton-safety-foundation*
*Plan: 06-ci-precommit*
*Completed: 2026-04-11*
