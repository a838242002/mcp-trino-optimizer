# syntax=docker/dockerfile:1.7

# ── Builder stage ───────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

# Install uv (Astral)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build

# Copy only the files needed for dependency resolution
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

# Install into a dedicated venv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
RUN uv venv /opt/venv
RUN UV_PROJECT_ENVIRONMENT=/opt/venv uv pip install --no-cache .

# Bake git SHA if provided as build arg
ARG GIT_SHA=unknown
RUN echo "${GIT_SHA}" > /opt/venv/lib/python3.12/site-packages/mcp_trino_optimizer/_git_sha.txt

# ── Runtime stage ───────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

# Copy the installed venv from the builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Non-root user
RUN useradd --system --uid 1000 --create-home --shell /usr/sbin/nologin mcp
USER mcp
WORKDIR /home/mcp

# Log hygiene — force unbuffered stderr
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# Default: stdio transport
ENTRYPOINT ["mcp-trino-optimizer", "serve"]
CMD ["--transport", "stdio"]

# Healthcheck is ONLY useful for HTTP mode; disabled by default.
HEALTHCHECK NONE
