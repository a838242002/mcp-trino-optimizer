# mcp-trino-optimizer

A Model Context Protocol (MCP) server that helps Claude Code (and other
MCP-compatible clients) optimize Trino SQL queries running against Iceberg
data lakes. Analyzes queries using `EXPLAIN` / `EXPLAIN ANALYZE` evidence,
applies a deterministic rule engine to diagnose performance issues, suggests
prioritized optimizations, and safely rewrites SQL while preserving
semantics.

Designed for data engineers, analytics engineers, and platform teams working
with Trino + Iceberg.

## Status

**Phase 1 — Skeleton & Safety Foundation.** The server boots on `stdio`
and Streamable HTTP, answers `initialize`, and exposes a single tool:
`mcp_selftest`. No Trino-touching code lands until Phase 2.

## Install

### uv tool install (recommended)

```bash
uv tool install mcp-trino-optimizer
mcp-trino-optimizer --help
```

### uvx (zero-install)

```bash
uvx mcp-trino-optimizer serve
```

### pip

```bash
pip install mcp-trino-optimizer
mcp-trino-optimizer --help
```

### Docker

```bash
docker pull mcp-trino-optimizer:latest
docker run --rm -i mcp-trino-optimizer serve
```

## Claude Code MCP configuration

Add one of the following blocks to your Claude Code `~/.claude.json` (or
equivalent `mcpServers` config file) and restart Claude Code.

### Stdio (local install)

```json
{
  "mcpServers": {
    "trino-optimizer": {
      "command": "mcp-trino-optimizer",
      "args": ["serve", "--transport", "stdio"]
    }
  }
}
```

### Streamable HTTP (remote or self-hosted)

The HTTP transport binds `127.0.0.1:8080` by default and requires a static
bearer token. Generate a strong token first:

```bash
openssl rand -hex 32
```

Set the token via environment variable and start the server:

```bash
MCPTO_HTTP_BEARER_TOKEN=<your-token> mcp-trino-optimizer serve --transport http
```

Then configure Claude Code:

```json
{
  "mcpServers": {
    "trino-optimizer": {
      "url": "http://127.0.0.1:8080/mcp",
      "transport": "http",
      "headers": {
        "Authorization": "Bearer YOUR_TOKEN_HERE"
      }
    }
  }
}
```

For production deployments put a reverse proxy (nginx, Caddy, Traefik) in
front of the server for TLS termination.

### Docker (stdio)

```json
{
  "mcpServers": {
    "trino-optimizer": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "mcp-trino-optimizer", "serve", "--transport", "stdio"]
    }
  }
}
```

## Self-test

Once Claude Code connects, call the `mcp_selftest` tool:

```
mcp_selftest(echo="hello")
```

A healthy server returns `server_version`, `transport`, `echo`, `capabilities`,
`python_version`, `package_version`, `git_sha`, `log_level`, and `started_at`.

## Configuration

All configuration happens through `MCPTO_*` environment variables or a
`.env` file. Precedence: CLI flags > OS env > `.env` > defaults.

See [`.env.example`](./.env.example) for the full list.

| Variable                    | Default       | Notes                                          |
|-----------------------------|---------------|------------------------------------------------|
| `MCPTO_TRANSPORT`           | `stdio`       | `stdio` or `http`                              |
| `MCPTO_HTTP_HOST`           | `127.0.0.1`   | Bind address (localhost only by default)       |
| `MCPTO_HTTP_PORT`           | `8080`        | 1–65535                                        |
| `MCPTO_HTTP_BEARER_TOKEN`   | *(required)*  | Required when `transport=http`. No default.    |
| `MCPTO_LOG_LEVEL`           | `INFO`        | `DEBUG` / `INFO` / `WARNING` / `ERROR`         |

## Safety posture

Phase 1 ships these day-one safety primitives before any Trino-touching code:

- **stdout discipline** — `stdio` transport installs a sentinel writer on
  `sys.stdout` and duplicates the pristine fd for JSON-RPC framing. Any
  stray write is captured as a `stdout_violation` log event, not dropped.
- **Structured logging to stderr only** — every log line is JSON with
  `request_id`, `tool_name`, `git_sha`, `package_version`, and ISO8601
  UTC timestamp. Logs never touch stdout.
- **Secret redaction** — any log field matching the denylist
  (`authorization`, `x-trino-extra-credentials`, `cookie`, `token`,
  `password`, `api_key`, `apikey`, `bearer`, `secret`, `ssl_password`,
  or `credential.*`) is hard-redacted to `[REDACTED]`. `pydantic.SecretStr`
  values render as `[REDACTED]` regardless of the key they're stored under.
- **Strict JSON Schema** — every tool input has
  `additionalProperties: false`, bounded `maxLength` on strings, bounded
  `maxItems` on arrays, and a `pattern` on identifier fields. A runtime
  schema-lint runs at startup and crashes the server before it binds a
  port if any tool is non-compliant.
- **Untrusted-content envelope** — every tool response that echoes a
  user-origin string routes it through `wrap_untrusted()`, which returns
  `{"source": "untrusted", "content": "..."}`. MCP clients key off the
  `source` field to isolate content from instructions.
- **Bearer token with constant-time compare** — the HTTP transport
  validates the `Authorization: Bearer <token>` header using
  `hmac.compare_digest`, and the token is never logged.

## Documentation

- [`CONTRIBUTING.md`](./CONTRIBUTING.md) — coding rules, Definition of Done, validation workflow
- [`CLAUDE.md`](./CLAUDE.md) — project context, technology stack, constraints
- [`LICENSE`](./LICENSE) — Apache License 2.0

## License

Apache-2.0
