# MySQL Readonly MCP Server

A Python MCP (Model Context Protocol) server that provides **readonly** access to a MySQL database.

- Chinese documentation: `README.zh-CN.md`

- Transport: **stdio** (recommended for MCP clients) and **HTTP/SSE** (standalone service)
- Safety: Only `SELECT`, `SHOW`, `DESCRIBE`, `DESC`, and `EXPLAIN` statements are permitted
- Config: **stdio** — MySQL settings via `mcp.json` `env`; **SSE** — environment at process start, optional `MCP_BEARER_TOKEN` for HTTP auth
- Table blacklist: `QUERY_TABLE_BLACKLIST` blocks **data** access via `query`; **`describe_table` still works** for schema on listed tables

---

## Requirements

- **Installer and MCP runtime:** Python **3.10+**. `install.py` checks the interpreter
  that runs it **before** any other step; if the version is too low, it exits immediately
  (use `python3.12 install.py`, `py -3.12 install.py`, etc.).
- **Optional:** `install.py --python /path/to/python3.12` creates `.venv` with that
  binary instead of `sys.executable` (that binary must also be 3.10+).
- A reachable MySQL instance.

## Installation

### First-time install (recommended)

Run `install.py` with a **3.10+** interpreter (`python`, `python3`, or `py -3`).

The script creates `.venv` with `python -m venv`, then `python -m pip install -r requirements.txt`.

After a successful install, an **interactive wizard** (if stdin is a TTY) asks for:
transport (**stdio** or **sse**), core MySQL fields, **QUERY_TABLE_BLACKLIST** (always),
optional timeouts / **QUERY_DEFAULT_LIMIT** / TLS paths, and for SSE **MCP_HOST** /
**MCP_PORT** / **MCP_BEARER_TOKEN**. It prints a **complete `mcp.json` snippet** (and for
SSE, shell `export` lines plus the server command). Use **`--no-wizard`** to skip (CI /
automation). Non-interactive stdin skips the wizard automatically.

**Windows** (CMD or double-click in Explorer):

```bat
cd \path\to\MySQL_MCP
install.bat
```

**macOS / Linux**:

```bash
cd /path/to/MySQL_MCP
python3 install.py
```

Useful flags:

| Flag | Meaning |
|------|---------|
| `--recreate` | Delete `.venv` and reinstall |
| `--dry-run` | Show the planned venv/pip steps only (still requires 3.10+ to run the script) |
| `--no-wizard` | Do not run the post-install configuration wizard |
| `--python EXE` | Create `.venv` with this 3.10+ interpreter (`EXE` on PATH or full path) |

If the Python Launcher is missing on Windows, install Python 3.10+ from [python.org](https://www.python.org/downloads/) and enable “Add to PATH”.

### Manual install (without the script)

```bash
cd /path/to/MySQL_MCP
python3 -m venv .venv
# Windows: .venv\Scripts\pip install -r requirements.txt
# Unix:    .venv/bin/pip install -r requirements.txt
```

After either method, set `mcp.json` `command` to the **venv** `python` / `python.exe`
absolute path — not a bare `python` on PATH.

---

## Configuration via mcp.json

All MySQL connection parameters are passed through the standard MCP configuration file.
Choose **Option A** (stdio) or **Option B** (SSE) depending on your client.

### Option A — stdio transport (recommended)

The MCP client launches `server.py` as a subprocess and injects MySQL credentials via the
`env` block.  No separate server process is needed.

Copy the following block into your client's MCP settings (e.g. Cursor `mcp.json`,
Claude Desktop `claude_desktop_config.json`, or a project-level `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "mysql-readonly": {
      "command": "/absolute/path/to/MySQL_MCP/.venv/bin/python",
      "args": ["/absolute/path/to/MySQL_MCP/server.py"],
      "env": {
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": "3306",
        "MYSQL_USER": "your_mysql_user",
        "MYSQL_PASSWORD": "your_mysql_password",
        "MYSQL_DATABASE": "your_database_name",
        "MYSQL_CONNECT_TIMEOUT": "10",
        "MYSQL_SSL": "false",
        "QUERY_DEFAULT_LIMIT": "100",
        "QUERY_TABLE_BLACKLIST": "sensitive_table,internal_audit_log"
      }
    }
  }
}
```

`args` must contain the **absolute path** to `server.py`.  
On Windows, use `"command": "C:\\path\\to\\MySQL_MCP\\.venv\\Scripts\\python.exe"` (escape backslashes in JSON).

Replace the `env` values with your actual MySQL credentials.

### Option B — HTTP/SSE transport

Start the server as a standalone HTTP service first. MySQL settings come from the
process environment (or your shell / systemd / Docker `environment` block).

```bash
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export MYSQL_USER=your_mysql_user
export MYSQL_PASSWORD=your_mysql_password
export MYSQL_DATABASE=your_database_name

# Default bind is 127.0.0.1 (safer). Use 0.0.0.0 only on trusted networks or
# behind a reverse proxy; set MCP_BEARER_TOKEN so clients must send
# Authorization: Bearer <token> on SSE and message requests.
export MCP_BEARER_TOKEN=your-long-random-secret   # optional but recommended if exposed

# Use the venv interpreter (from repo root after install):
# Unix/macOS:  .venv/bin/python server.py --transport sse --port 8000
# Windows:     .venv\Scripts\python.exe server.py --transport sse --port 8000
.venv/bin/python server.py --transport sse --port 8000
```

Then point your MCP client at the SSE endpoint (and configure the client to send
the Bearer token if `MCP_BEARER_TOKEN` is set):

```json
{
  "mcpServers": {
    "mysql-readonly": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

---

## Environment Variables Reference

| Variable                    | Required | Default      | Description |
|-----------------------------|----------|--------------|-------------|
| `MYSQL_HOST`                | No       | `127.0.0.1`  | MySQL hostname or IP |
| `MYSQL_PORT`                | No       | `3306`       | MySQL port |
| `MYSQL_USER`                | **Yes**  | —            | MySQL username |
| `MYSQL_PASSWORD`            | No       | `""`         | MySQL password |
| `MYSQL_DATABASE`            | **Yes**  | —            | Target database name |
| `MYSQL_CONNECT_TIMEOUT`     | No       | `10`         | TCP connect timeout (seconds) |
| `MYSQL_READ_TIMEOUT`        | No       | `30`         | Socket read timeout (seconds) |
| `MYSQL_WRITE_TIMEOUT`       | No       | `30`         | Socket write timeout (seconds) |
| `MYSQL_MAX_EXECUTION_TIME`  | No       | `30000`      | Per-query server limit (milliseconds); `SET SESSION MAX_EXECUTION_TIME` |
| `MYSQL_SSL`                 | No       | `false`      | Enable TLS to MySQL: `"true"` / `"false"` |
| `MYSQL_SSL_CA`              | No       | `""`         | Path to CA certificate (when using TLS) |
| `MYSQL_SSL_CERT`            | No       | `""`         | Path to client certificate |
| `MYSQL_SSL_KEY`             | No       | `""`         | Path to client private key |
| `MYSQL_SSL_VERIFY_CERT`     | No       | `true`       | Set `"false"` to skip server cert verification (not recommended) |
| `QUERY_DEFAULT_LIMIT`       | No       | `100`        | Upper bound on rows for `SELECT`; explicit `LIMIT` is also capped to this (after applying the `limit` tool argument) |
| `QUERY_TABLE_BLACKLIST`     | No       | `""`         | Comma-separated table names. The **`query` tool** rejects SQL that references them (including `JOIN`); **`describe_table` still returns schema** for those tables. Not a substitute for DB grants. |
| `MCP_HOST`                  | No       | `127.0.0.1`  | Bind address for SSE transport (`CLI --host` overrides at runtime) |
| `MCP_PORT`                  | No       | `8000`       | Bind port for SSE (`CLI --port` overrides) |
| `MCP_BEARER_TOKEN`          | No       | `""`         | If non-empty, SSE HTTP requests require `Authorization: Bearer <token>` |

---

## Available Tools

### `query`

Execute a readonly SQL statement and return results as structured JSON.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sql`     | str  | —       | SQL statement (`SELECT` / `SHOW` / `DESCRIBE` / `EXPLAIN`) |
| `limit`   | int  | `QUERY_DEFAULT_LIMIT` | Capped at `QUERY_DEFAULT_LIMIT`; combined with server rewrite so `SELECT` never returns more rows than this effective cap (even if SQL contains a larger `LIMIT`) |

**Returns:**
```json
{
  "columns": ["id", "name", "email"],
  "rows": [
    {"id": 1, "name": "Alice", "email": "alice@example.com"}
  ],
  "row_count": 1
}
```

### `list_tables`

List all tables in the configured database.

**Returns:**
```json
{
  "database": "mydb",
  "tables": ["users", "orders", "products"],
  "count": 3
}
```

### `describe_table`

Get the column schema of a specific table.

For tables in `QUERY_TABLE_BLACKLIST`, use this tool for schema — the `query` tool
rejects any SQL (including `DESCRIBE`) that references those tables.

| Parameter    | Type | Description         |
|--------------|------|---------------------|
| `table_name` | str  | Table name (letters, digits, underscores only) |

**Returns:**
```json
{
  "table": "users",
  "columns": [
    {"Field": "id",    "Type": "int",          "Null": "NO",  "Key": "PRI", "Default": null, "Extra": "auto_increment"},
    {"Field": "name",  "Type": "varchar(255)", "Null": "YES", "Key": "",    "Default": null, "Extra": ""},
    {"Field": "email", "Type": "varchar(255)", "Null": "YES", "Key": "UNI", "Default": null, "Extra": ""}
  ]
}
```

---

## Security — Readonly Enforcement

The server enforces readonly access at the application layer with a two-stage guard:

1. **Whitelist** — the first keyword must be one of `SELECT`, `SHOW`, `DESCRIBE`, `DESC`, `EXPLAIN`.
2. **Blacklist** — the full statement is scanned for forbidden patterns: `INSERT`, `UPDATE`,
   `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `REPLACE`, `GRANT`, `REVOKE`,
   `COMMIT`, `ROLLBACK`, `LOAD DATA`, `INTO OUTFILE`, `SLEEP`, `BENCHMARK`, and more.
3. **Multi-statement rejection** — any SQL containing `;` (after stripping a single trailing
   semicolon) is rejected.
4. **Identifier validation** — table names passed to `describe_table` are validated to contain
   only `[A-Za-z0-9_]` characters before being interpolated into the query.
5. **Table blacklist** — tables listed in `QUERY_TABLE_BLACKLIST` cannot be used for **data**
   access through the `query` tool (including subqueries / `JOIN`s that reference them).
   The **`describe_table` tool is still allowed** for those names so agents can inspect schema.
   Errors use a bilingual JSON payload (`message_en` / `message_zh`).

> For production use, also configure the MySQL user with `SELECT`-only privileges at the
> database level as an additional layer of defense. Treat the app-level blacklist as a
> convenience, not the primary authorization boundary.

---

## Verification

After configuration, test the server with these queries:

```sql
-- Should succeed
SHOW TABLES
SELECT * FROM your_table LIMIT 5
DESCRIBE your_table
EXPLAIN SELECT id FROM your_table

-- Should be rejected with an error
DELETE FROM your_table WHERE id = 1
INSERT INTO your_table (name) VALUES ('x')
SELECT 1; DROP TABLE your_table
SELECT SLEEP(5)
```

---

## Running Locally (without an MCP client)

You can test the server directly from the command line using the MCP CLI:

```bash
# Install dev dependency
pip install "mcp[cli]"

# stdio mode — interactive inspector
MYSQL_HOST=127.0.0.1 MYSQL_USER=root MYSQL_PASSWORD=secret MYSQL_DATABASE=mydb \
  mcp dev server.py

# SSE mode — start server, then open http://localhost:8000/sse in a browser or curl
MYSQL_HOST=127.0.0.1 MYSQL_USER=root MYSQL_PASSWORD=secret MYSQL_DATABASE=mydb \
  .venv/bin/python server.py --transport sse
```

---

## Project Structure

```
MySQL_MCP/
├── server.py            # MCP server: tools, SQL guard, MySQL connector
├── install.py           # First-time setup: venv + pip install (all platforms)
├── install.bat          # Windows launcher for install.py
├── mcp.json             # MCP configuration template (stdio + SSE examples)
├── requirements.txt     # Python dependencies
├── pyproject.toml       # Package metadata
├── Dockerfile           # Container image definition
├── docker-compose.yml   # Compose file (MCP server + optional local MySQL)
└── README.md            # This file
```

---

## Docker Deployment

### Build and run with Docker Compose

Create a `.env` file in the project root with your MySQL credentials:

```bash
MYSQL_HOST=host.docker.internal   # use host.docker.internal to reach the host machine
MYSQL_PORT=3306
MYSQL_USER=your_mysql_user
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=your_database_name
```

Uncomment the `ports` block in [`docker-compose.yml`](docker-compose.yml) (see the
`127.0.0.1:${MCP_PORT:-8000}:8000` example) so the host can reach the container; it is
commented out by default for safety.

Then start the container:

```bash
docker compose up -d
```

Set `MCP_BEARER_TOKEN` in `.env` when exposing SSE. The MCP SSE endpoint is then
`http://localhost:8000/sse` (or the mapped host/port you chose).

Point your MCP client at it:

```json
{
  "mcpServers": {
    "mysql-readonly": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

### Build and run manually

```bash
docker build -t mysql-mcp-server .

docker run -d \
  --name mysql-mcp-server \
  -p 8000:8000 \
  -e MYSQL_HOST=host.docker.internal \
  -e MYSQL_USER=your_user \
  -e MYSQL_PASSWORD=your_password \
  -e MYSQL_DATABASE=your_db \
  mysql-mcp-server
```

### Using with a local MySQL container

Uncomment the `mysql` service block in `docker-compose.yml` to spin up a local MySQL
alongside the MCP server.  The service uses a `healthcheck` so the MCP server only
starts after MySQL is ready.

---

## Extending

The following improvements are recommended before production use:

- **Connection pooling** — replace per-request connections with `DBUtils` or `SQLAlchemy` pool
- **SQL AST validation** — use `sqlglot` or `sqlparse` for structural analysis instead of regex
- **Audit logging** — log every executed query with timestamp, client identity, and row count
- **Row-level rate limiting** — enforce per-client query frequency limits
- **TLS / mTLS at the edge** — terminate HTTPS and optional client certificates in a reverse
  proxy in front of SSE; combine with `MCP_BEARER_TOKEN` for defense in depth

---

## License

This project is licensed under the MIT License. See `LICENSE`.
