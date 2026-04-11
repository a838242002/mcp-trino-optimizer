---
phase: 01-skeleton-safety-foundation
plan: 06
type: execute
wave: 3
depends_on:
  - 01-04-app-tools-transports-cli
files_modified:
  - .github/workflows/ci.yml
  - .pre-commit-config.yaml
autonomous: true
requirements:
  - PLAT-01
  - PLAT-13
must_haves:
  truths:
    - "GitHub Actions CI workflow defines exactly three jobs: lint-types, unit-smoke, integration (the last with if: false or equivalent stub)"
    - "unit-smoke runs on a 3 OS × 3 Python matrix (ubuntu-latest/macos-latest/windows-latest × 3.11/3.12/3.13 = 9 cells), satisfies PLAT-13"
    - "unit-smoke runs pytest -m 'not integration', the stdio cleanliness smoke test, and the CLI entry point check (both `pip install -e` and `uv tool install .` paths)"
    - "lint-types runs ruff format --check, ruff check, and mypy --strict on one cell (Linux × Python 3.12)"
    - "integration job is stubbed with if: false so Phase 2+ can flip the flag without restructuring the workflow"
    - "pre-commit config enforces ruff format, ruff check, and mypy src at commit time"
    - "Every job uses shell: bash explicitly to work on Windows runners (RESEARCH.md §12.1)"
  artifacts:
    - path: ".github/workflows/ci.yml"
      provides: "GitHub Actions CI with three jobs matching D-14"
      contains: "unit-smoke"
    - path: ".pre-commit-config.yaml"
      provides: "pre-commit hooks for ruff and mypy"
      contains: "ruff"
  key_links:
    - from: ".github/workflows/ci.yml"
      to: "tests/smoke/test_stdio_initialize.py"
      via: "CI step 'Stdio cleanliness smoke test' runs this test explicitly"
      pattern: "test_stdio_initialize"
---

<objective>
Land the CI pipeline that satisfies PLAT-13 (9-cell install matrix) and PLAT-01 (both `pip install` AND `uv tool install` paths tested) AND the pre-commit configuration that enforces coding rules on every developer commit. This plan is the last Wave 3 plan; after it lands, Phase 1 is done.

Critical design constraints from CONTEXT.md D-14 and RESEARCH.md §12:
- Three jobs: `lint-types` (1 cell), `unit-smoke` (9 cells = 3 OS × 3 Python), `integration` (stub with `if: false`)
- Every step uses `shell: bash` explicitly because Windows runners default to `cmd` which breaks `uv venv` and `|` pipes
- The smoke test MUST be run explicitly as a named step (not just rolled into `pytest`) so CI log output makes the PLAT-05 guarantee traceable
- Both `pip install -e .` and `uv tool install .` paths get exercised in the matrix — per PLAT-01 and RESEARCH.md §12 assumption A3
- Use `astral-sh/setup-uv@v4` as the uv action; it manages Python version installs cleanly across all three runners

Purpose: Close PLAT-13 and PLAT-01 with a real CI pipeline plus pre-commit enforcement of coding rules.
Output: `.github/workflows/ci.yml` with three jobs; `.pre-commit-config.yaml` with ruff + mypy hooks.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md
@.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md
@CLAUDE.md
@pyproject.toml
@tests/smoke/test_stdio_initialize.py

<interfaces>
<!-- This plan produces YAML files only. No code interfaces. -->
<!-- Inputs: pinned tool versions from CLAUDE.md + pyproject.toml.             -->
<!-- Outputs: CI matrix that runs tests Phase 1 already shipped.               -->
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write .github/workflows/ci.yml</name>
  <files>.github/workflows/ci.yml</files>
  <read_first>
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-RESEARCH.md §12 (GitHub Actions template — copy verbatim), §12.1 (per-OS/Python pitfalls and mitigations)
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md D-14 (CI matrix shape — three jobs)
    - /Users/allen/repo/mcp-trino-optimizer/CLAUDE.md (tool versions)
    - /Users/allen/repo/mcp-trino-optimizer/pyproject.toml (dev deps already pinned)
  </read_first>
  <action>
    COPY RESEARCH.md §12 VERBATIM with a few tightenings for actual usability. Write `.github/workflows/ci.yml`:

    ```yaml
    name: CI

    on:
      push:
        branches: [main]
      pull_request:
        branches: [main]

    concurrency:
      group: ${{ github.workflow }}-${{ github.ref }}
      cancel-in-progress: true

    jobs:
      # ────────────────────────────────────────────────────────────────
      # lint-types — one cell
      # ────────────────────────────────────────────────────────────────
      lint-types:
        name: Lint + Types (Linux / Python 3.12)
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4

          - name: Install uv
            uses: astral-sh/setup-uv@v4
            with:
              python-version: "3.12"

          - name: Install dev deps
            run: uv sync --all-extras
            shell: bash

          - name: Ruff format check
            run: uv run ruff format --check .
            shell: bash

          - name: Ruff lint
            run: uv run ruff check .
            shell: bash

          - name: Mypy strict
            run: uv run mypy src
            shell: bash

      # ────────────────────────────────────────────────────────────────
      # unit-smoke — 9-cell matrix (PLAT-13)
      # ────────────────────────────────────────────────────────────────
      unit-smoke:
        name: Unit + Smoke (${{ matrix.os }} / Python ${{ matrix.python }})
        strategy:
          fail-fast: false
          matrix:
            os: [ubuntu-latest, macos-latest, windows-latest]
            python: ["3.11", "3.12", "3.13"]
        runs-on: ${{ matrix.os }}
        steps:
          - uses: actions/checkout@v4

          - name: Install uv
            uses: astral-sh/setup-uv@v4
            with:
              python-version: ${{ matrix.python }}

          - name: Install package (pip install -e path — PLAT-01)
            run: |
              uv venv
              uv pip install -e ".[dev]"
            shell: bash

          - name: Run unit tests (not integration)
            run: uv run pytest -m "not integration" -x
            shell: bash
            env:
              MCPTO_GIT_SHA: ${{ github.sha }}
              PYTHONUNBUFFERED: "1"

          - name: Stdio cleanliness smoke test (PLAT-05)
            run: uv run pytest tests/smoke/test_stdio_initialize.py -v
            shell: bash
            env:
              MCPTO_GIT_SHA: ${{ github.sha }}
              PYTHONUNBUFFERED: "1"

          - name: HTTP bearer smoke test (PLAT-03)
            run: uv run pytest tests/smoke/test_http_bearer.py -v
            shell: bash
            env:
              MCPTO_GIT_SHA: ${{ github.sha }}
              PYTHONUNBUFFERED: "1"

          - name: Verify CLI entry point exists
            run: uv run mcp-trino-optimizer --help
            shell: bash

          - name: Verify `uv tool install .` path (PLAT-01 — second install variant)
            run: |
              uv tool install .
              uv tool run mcp-trino-optimizer --help
            shell: bash

      # ────────────────────────────────────────────────────────────────
      # integration — reserved for Phase 2+ (docker-compose stack)
      # ────────────────────────────────────────────────────────────────
      integration:
        name: Integration (Phase 2+ — docker-compose stack)
        if: false  # Phase 2+ flips this to run the testcontainers-based suite
        runs-on: ubuntu-latest
        steps:
          - run: echo "Integration job placeholder — populated in Phase 2+"
    ```

    **Critical gotchas from RESEARCH.md §12.1 to preserve:**
    - Every `run:` block declares `shell: bash` explicitly — Windows defaults to `cmd` which breaks `uv venv` and `|` pipes.
    - `PYTHONUNBUFFERED: "1"` set on every test step so stdio frames are flushed immediately — avoids timeout deadlocks.
    - `MCPTO_GIT_SHA: ${{ github.sha }}` on every test step so `runtime_info().git_sha` returns a real value in CI.
    - `fail-fast: false` on the matrix so one cell's failure doesn't mask another's.
    - `concurrency` group cancels in-progress runs on the same ref to save CI minutes on rapid pushes.
    - `astral-sh/setup-uv@v4` is the canonical uv action; it handles Python install and caching.

    **Do NOT add `paths-ignore: ["*.md"]`** — RESEARCH.md §20 Q5 notes that would be a reasonable future optimization but adds complexity now.

    **Do NOT gate `integration` on branch/path** — the `if: false` is enough; Phase 2 flips it to an actual condition like `if: ${{ !contains(github.event.pull_request.labels.*.name, 'skip-integration') }}`.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && test -f .github/workflows/ci.yml && grep -c "jobs:" .github/workflows/ci.yml && grep -c "matrix:" .github/workflows/ci.yml</automated>
  </verify>
  <acceptance_criteria>
    - `.github/workflows/ci.yml` exists
    - `grep -c "lint-types:" .github/workflows/ci.yml` returns `1`
    - `grep -c "unit-smoke:" .github/workflows/ci.yml` returns `1`
    - `grep -c "integration:" .github/workflows/ci.yml` returns `1`
    - `grep -c "if: false" .github/workflows/ci.yml` returns at least `1` (integration stub)
    - `grep -c "ubuntu-latest" .github/workflows/ci.yml` returns at least `2`
    - `grep -c "macos-latest" .github/workflows/ci.yml` returns at least `1`
    - `grep -c "windows-latest" .github/workflows/ci.yml` returns at least `1`
    - `grep -c '"3.11"' .github/workflows/ci.yml` returns at least `1`
    - `grep -c '"3.12"' .github/workflows/ci.yml` returns at least `2` (lint-types pinned + matrix)
    - `grep -c '"3.13"' .github/workflows/ci.yml` returns at least `1`
    - `grep -c "shell: bash" .github/workflows/ci.yml` returns at least `8` (bash on every run step)
    - `grep -c "ruff format --check" .github/workflows/ci.yml` returns `1`
    - `grep -c "ruff check" .github/workflows/ci.yml` returns `1`
    - `grep -c "mypy src" .github/workflows/ci.yml` returns `1`
    - `grep -c "test_stdio_initialize" .github/workflows/ci.yml` returns `1`
    - `grep -c "test_http_bearer" .github/workflows/ci.yml` returns `1`
    - `grep -c "uv tool install" .github/workflows/ci.yml` returns `1` (PLAT-01 second install path)
    - `grep -c "uv pip install -e" .github/workflows/ci.yml` returns `1` (PLAT-01 pip path)
    - `grep -c "astral-sh/setup-uv@v4" .github/workflows/ci.yml` returns at least `2` (both jobs)
    - `grep -c "MCPTO_GIT_SHA" .github/workflows/ci.yml` returns at least `3` (every test step)
    - `grep -c "PYTHONUNBUFFERED" .github/workflows/ci.yml` returns at least `3`
    - `grep -c "fail-fast: false" .github/workflows/ci.yml` returns `1`
    - `grep -c "concurrency:" .github/workflows/ci.yml` returns `1`
    - YAML is syntactically valid: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` exits 0
  </acceptance_criteria>
  <done>CI workflow has all three jobs (lint-types, unit-smoke with 9-cell matrix, integration stubbed); every step uses `shell: bash`; both `pip install -e` and `uv tool install` paths get exercised for PLAT-01; stdio and HTTP smoke tests are explicit steps; YAML parses cleanly.</done>
</task>

<task type="auto">
  <name>Task 2: Write .pre-commit-config.yaml</name>
  <files>.pre-commit-config.yaml</files>
  <read_first>
    - /Users/allen/repo/mcp-trino-optimizer/.planning/phases/01-skeleton-safety-foundation/01-CONTEXT.md Claude's Discretion on pre-commit hooks (must include ruff format, ruff check, mypy at minimum)
    - /Users/allen/repo/mcp-trino-optimizer/CLAUDE.md (ruff>=0.15.10, mypy>=1.11)
    - /Users/allen/repo/mcp-trino-optimizer/pyproject.toml (dev deps pinned)
  </read_first>
  <action>
    Write `.pre-commit-config.yaml` using upstream hooks (astral-sh/ruff-pre-commit for ruff, pre-commit/mirrors-mypy for mypy). Pin rev tags to match the pyproject.toml dev dep versions.

    ```yaml
    # .pre-commit-config.yaml
    # Install hooks with: uv run pre-commit install
    # Run manually with: uv run pre-commit run --all-files
    #
    # Minimum hooks required by CONTRIBUTING.md Definition of Done:
    #   - ruff format
    #   - ruff check
    #   - mypy src
    # Plus the usual hygiene (trailing whitespace, end-of-file, merge conflicts).

    default_language_version:
      python: python3.12

    repos:
      # ── Hygiene ──────────────────────────────────────────────────
      - repo: https://github.com/pre-commit/pre-commit-hooks
        rev: v5.0.0
        hooks:
          - id: trailing-whitespace
            exclude: '\.md$'  # markdown tables sometimes need trailing spaces
          - id: end-of-file-fixer
          - id: check-merge-conflict
          - id: check-yaml
          - id: check-toml
          - id: check-added-large-files
            args: ['--maxkb=500']
          - id: detect-private-key
          - id: check-case-conflict
          - id: mixed-line-ending
            args: ['--fix=lf']

      # ── Ruff (lint + format) ─────────────────────────────────────
      - repo: https://github.com/astral-sh/ruff-pre-commit
        rev: v0.15.10
        hooks:
          - id: ruff-check
            args: ['--fix', '--exit-non-zero-on-fix']
          - id: ruff-format

      # ── Mypy (strict) ────────────────────────────────────────────
      - repo: https://github.com/pre-commit/mirrors-mypy
        rev: v1.11.2
        hooks:
          - id: mypy
            args: ['--strict', '--config-file=pyproject.toml']
            files: '^src/'
            additional_dependencies:
              - 'pydantic>=2.9'
              - 'pydantic-settings>=2.13.1'
              - 'structlog>=25.5.0'
              - 'mcp>=1.27.0,<2'
              - 'typer>=0.12'
              - 'types-orjson'
    ```

    **Why these rev pins:**
    - `pre-commit-hooks v5.0.0`: latest stable as of 2026-04-11.
    - `ruff-pre-commit v0.15.10`: exact match to CLAUDE.md pin.
    - `mirrors-mypy v1.11.2`: matches `mypy>=1.11` pin; use the first 1.11.x patch that's in mirrors-mypy.

    **Why `additional_dependencies` on mypy:** pre-commit runs hooks in isolated envs, so the mypy hook needs every type-providing runtime dep explicitly listed to resolve imports. Mirror the key deps from pyproject.toml.

    **Why `files: '^src/'`:** only lint our source tree with mypy in the pre-commit hook; tests lint via `uv run mypy src` in CI plus `uv run pytest` (which doesn't require mypy). This keeps pre-commit fast.

    **IMPORTANT:** The mypy mirror pin may lag the real mypy release. If `v1.11.2` doesn't exist in the mirror at execution time, use the closest 1.11.x tag that does exist (e.g., `v1.11.1`). This is discretionary per CONTEXT.md.
  </action>
  <verify>
    <automated>cd /Users/allen/repo/mcp-trino-optimizer && test -f .pre-commit-config.yaml && uv run python -c "import yaml; data = yaml.safe_load(open('.pre-commit-config.yaml')); print('repos:', len(data['repos']))"</automated>
  </verify>
  <acceptance_criteria>
    - `.pre-commit-config.yaml` exists
    - YAML parses cleanly: `uv run python -c "import yaml; yaml.safe_load(open('.pre-commit-config.yaml'))"` exits 0
    - `grep -c "astral-sh/ruff-pre-commit" .pre-commit-config.yaml` returns `1`
    - `grep -c "id: ruff-format" .pre-commit-config.yaml` returns `1`
    - `grep -c "id: ruff-check" .pre-commit-config.yaml` returns `1`
    - `grep -c "mirrors-mypy" .pre-commit-config.yaml` returns `1`
    - `grep -c "id: mypy" .pre-commit-config.yaml` returns `1`
    - `grep -c '\-\-strict' .pre-commit-config.yaml` returns `1`
    - `grep -c "detect-private-key" .pre-commit-config.yaml` returns `1`
    - `grep -c "check-added-large-files" .pre-commit-config.yaml` returns `1`
    - `grep -c "end-of-file-fixer" .pre-commit-config.yaml` returns `1`
    - `grep -c "mixed-line-ending" .pre-commit-config.yaml` returns `1` (CRLF protection)
    - `grep -c "v0.15.10" .pre-commit-config.yaml` returns `1` (ruff pin matches CLAUDE.md)
  </acceptance_criteria>
  <done>pre-commit config has ruff format + ruff check + mypy strict hooks plus hygiene hooks (trailing whitespace, EOL fixer, private-key detection, large-file guard, YAML/TOML syntax check); YAML is valid.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| CI job outputs → phase gate | PLAT-13 requires 9-cell green; a single failing cell blocks phase completion |
| pre-commit hook → dev commit | Developer can bypass with `--no-verify`; CI catches the bypass on PR |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-10 | Supply chain | Unpinned GitHub Action version | mitigate | Every action pinned to a major version tag (`@v4`); pre-commit hooks pinned to exact rev; ruff rev matches CLAUDE.md pin exactly |
| T-01-11 | Tampering | Developer commits secret via `--no-verify` | mitigate | `detect-private-key` pre-commit hook catches the obvious cases; `.gitignore` excludes `.env`; `check-added-large-files` blocks accidental large binaries |
</threat_model>

<verification>
Run `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` and `uv run python -c "import yaml; yaml.safe_load(open('.pre-commit-config.yaml'))"` — both must exit 0. Manually inspect the `ci.yml` matrix rendering and confirm 3 × 3 = 9 cells.
</verification>

<success_criteria>
- CI workflow has three jobs (lint-types, unit-smoke with 9-cell matrix, integration stub)
- Every step uses `shell: bash` explicitly (Windows compatibility)
- Both `pip install -e` and `uv tool install` paths are exercised
- Stdio and HTTP smoke tests are explicit named steps (PLAT-05, PLAT-03 traceability)
- pre-commit config includes ruff format, ruff check, mypy strict
- YAML files both parse cleanly
</success_criteria>

<output>
After completion, create `.planning/phases/01-skeleton-safety-foundation/01-06-SUMMARY.md`
</output>
