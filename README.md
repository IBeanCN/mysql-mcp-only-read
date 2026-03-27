# MySQL Readonly MCP Server

A Python MCP (Model Context Protocol) server that provides **readonly** access to a MySQL database.

- Chinese documentation: `README.zh-CN.md`

- Transport: **stdio** (recommended for MCP clients) and **HTTP/SSE** (standalone service)
- Safety: Only `SELECT`, `SHOW`, `DESCRIBE`, `DESC`, and `EXPLAIN` statements are permitted
- Config: All parameters are passed via `mcp.json` — no code changes needed to switch databases

---

## Requirements

- Python 3.10+
- A reachable MySQL instance

## Installation

```bash
cd /path/to/MySQL_MCP
pip install -r requirements.txt
```

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
      "command": "python",
      "args": ["/absolute/path/to/server.py"],
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
Replace the `env` values with your actual MySQL credentials.

### Option B — HTTP/SSE transport

Start the server as a standalone HTTP service first:

```bash
# Environment variables carry the MySQL config
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export MYSQL_USER=your_mysql_user
export MYSQL_PASSWORD=your_mysql_password
export MYSQL_DATABASE=your_database_name

python server.py --transport sse --host 0.0.0.0 --port 8000
```

Then point your MCP client at the SSE endpoint:

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

| Variable               | Required | Default     | Description                                      |
|------------------------|----------|-------------|--------------------------------------------------|
| `MYSQL_HOST`           | No       | `127.0.0.1` | MySQL server hostname or IP                      |
| `MYSQL_PORT`           | No       | `3306`      | MySQL server port                                |
| `MYSQL_USER`           | **Yes**  | —           | MySQL username                                   |
| `MYSQL_PASSWORD`       | No       | `""`        | MySQL password                                   |
| `MYSQL_DATABASE`       | **Yes**  | —           | Target database name                             |
| `MYSQL_CONNECT_TIMEOUT`| No       | `10`        | Connection timeout in seconds                    |
| `MYSQL_SSL`            | No       | `false`     | Enable SSL: `"true"` or `"false"`                |
| `QUERY_DEFAULT_LIMIT`  | No       | `100`       | Max rows returned per SELECT (server-side cap)   |
| `QUERY_TABLE_BLACKLIST`| No       | `""`        | Comma-separated blocked table names for `query`/`describe_table` |
| `MCP_HOST`             | No       | `0.0.0.0`   | Bind host for SSE transport                      |
| `MCP_PORT`             | No       | `8000`      | Bind port for SSE transport                      |

---

## Available Tools

### `query`

Execute a readonly SQL statement and return results as structured JSON.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sql`     | str  | —       | SQL statement (`SELECT` / `SHOW` / `DESCRIBE` / `EXPLAIN`) |
| `limit`   | int  | `QUERY_DEFAULT_LIMIT` | Row cap for `SELECT` queries without a `LIMIT` clause |

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
5. **Table blacklist** — if a referenced table is in `QUERY_TABLE_BLACKLIST`, the server rejects
   the request and returns a bilingual structured error payload (English/Chinese).

> For production use, also configure the MySQL user with `SELECT`-only privileges at the
> database level as an additional layer of defense.

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
  python server.py --transport sse
```

---

## Project Structure

```
MySQL_MCP/
├── server.py            # MCP server: tools, SQL guard, MySQL connector
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

Then start the container:

```bash
docker compose up -d
```

The MCP SSE endpoint will be available at `http://localhost:8000/sse`.

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
- **mTLS / auth** — add token authentication to the SSE endpoint

---

## License

This project is licensed under the MIT License. See `LICENSE`.
