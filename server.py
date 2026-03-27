#!/usr/bin/env python3
"""
MySQL Readonly MCP Server

A Model Context Protocol server that provides readonly access to a MySQL database.
Supports both stdio and HTTP/SSE transports.

Configuration is passed via environment variables, which are set through the `env`
section of mcp.json for stdio transport, or via shell environment for HTTP/SSE mode.

Environment Variables:
    MYSQL_HOST              MySQL server hostname          (default: 127.0.0.1)
    MYSQL_PORT              MySQL server port              (default: 3306)
    MYSQL_USER              MySQL username                 (required)
    MYSQL_PASSWORD          MySQL password                 (default: "")
    MYSQL_DATABASE          Target database name           (required)
    MYSQL_CONNECT_TIMEOUT   Connection timeout in seconds  (default: 10)
    MYSQL_SSL               Enable SSL: "true"/"false"     (default: false)
    QUERY_DEFAULT_LIMIT     Default row limit for SELECT   (default: 100)
    QUERY_TABLE_BLACKLIST   Comma-separated table blacklist (default: "")
    MCP_HOST                Bind host for SSE transport    (default: 0.0.0.0)
    MCP_PORT                Bind port for SSE transport    (default: 8000)
"""

import argparse
import json
import os
import re
import sys
from typing import Any

import pymysql
import pymysql.cursors
from mcp.server.fastmcp import FastMCP

# ── Configuration (read from environment, injected via mcp.json `env`) ────────

MYSQL_HOST: str = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT: int = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER: str = os.environ.get("MYSQL_USER", "")
MYSQL_PASSWORD: str = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DATABASE: str = os.environ.get("MYSQL_DATABASE", "")
MYSQL_CONNECT_TIMEOUT: int = int(os.environ.get("MYSQL_CONNECT_TIMEOUT", "10"))
MYSQL_SSL: bool = os.environ.get("MYSQL_SSL", "false").strip().lower() == "true"
QUERY_DEFAULT_LIMIT: int = int(os.environ.get("QUERY_DEFAULT_LIMIT", "100"))
QUERY_TABLE_BLACKLIST_RAW: str = os.environ.get("QUERY_TABLE_BLACKLIST", "")

MCP_HOST: str = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT: int = int(os.environ.get("MCP_PORT", "8000"))

# ── MCP Server ────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="mysql-readonly",
    instructions=(
        "Provides readonly access to a MySQL database. "
        "Only SELECT, SHOW, DESCRIBE, DESC, and EXPLAIN statements are permitted. "
        "Available tools: query, list_tables, describe_table. "
        "Blacklisted tables (QUERY_TABLE_BLACKLIST) allow structure inspection via "
        "describe_table only; data queries against them are blocked."
    ),
)

# ── SQL Safety Guard ──────────────────────────────────────────────────────────

_ALLOWED_PREFIXES: frozenset[str] = frozenset(
    ["SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"]
)

# Patterns that must never appear in any readonly query
_FORBIDDEN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bINSERT\b"),
    re.compile(r"\bUPDATE\b"),
    re.compile(r"\bDELETE\b"),
    re.compile(r"\bDROP\b"),
    re.compile(r"\bALTER\b"),
    re.compile(r"\bCREATE\b"),
    re.compile(r"\bTRUNCATE\b"),
    re.compile(r"\bREPLACE\b"),
    re.compile(r"\bMERGE\b"),
    re.compile(r"\bCALL\b"),
    re.compile(r"\bEXEC(UTE)?\b"),
    re.compile(r"\bGRANT\b"),
    re.compile(r"\bREVOKE\b"),
    re.compile(r"\bFLUSH\b"),
    re.compile(r"\bRESET\b"),
    re.compile(r"\bPURGE\b"),
    re.compile(r"\bCOMMIT\b"),
    re.compile(r"\bROLLBACK\b"),
    re.compile(r"\bSAVEPOINT\b"),
    re.compile(r"\bBEGIN\b"),
    re.compile(r"\bSTART\s+TRANSACTION\b"),
    re.compile(r"\bLOCK\s+TABLES\b"),
    re.compile(r"\bUNLOCK\s+TABLES\b"),
    re.compile(r"\bLOAD\s+DATA\b"),
    re.compile(r"\bINTO\s+OUTFILE\b"),
    re.compile(r"\bINTO\s+DUMPFILE\b"),
    re.compile(r"\bSLEEP\s*\("),
    re.compile(r"\bBENCHMARK\s*\("),
]

# Simple identifier: letters, digits, underscores only
_IDENTIFIER_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_]+$")
_FROM_JOIN_RE: re.Pattern[str] = re.compile(
    r"\b(?:FROM|JOIN)\s+`?([A-Za-z0-9_]+)`?(?:\s*\.\s*`?([A-Za-z0-9_]+)`?)?",
    re.IGNORECASE,
)
_DESCRIBE_RE: re.Pattern[str] = re.compile(
    r"^\s*(?:DESCRIBE|DESC)\s+`?([A-Za-z0-9_]+)`?(?:\s*\.\s*`?([A-Za-z0-9_]+)`?)?",
    re.IGNORECASE,
)
_SHOW_TABLE_TARGET_RE: re.Pattern[str] = re.compile(
    r"^\s*SHOW\s+(?:COLUMNS|FIELDS|INDEX|INDEXES|KEYS|CREATE\s+TABLE)\s+"
    r"(?:FROM|IN)\s+`?([A-Za-z0-9_]+)`?(?:\s*\.\s*`?([A-Za-z0-9_]+)`?)?",
    re.IGNORECASE,
)


def validate_readonly_sql(sql: str) -> None:
    """Validate that the SQL statement is safe and readonly.

    Applies a whitelist check on the leading keyword and a blacklist scan for
    any forbidden DML/DDL/admin patterns.  Raises ValueError on violation.
    """
    stripped = sql.strip()

    # Remove a single trailing semicolon
    if stripped.endswith(";"):
        stripped = stripped[:-1].rstrip()

    # Reject multi-statement chains
    if ";" in stripped:
        raise ValueError(
            "Multi-statement SQL is not allowed. "
            "Send each statement as a separate tool call."
        )

    upper = stripped.upper()
    tokens = upper.split()
    if not tokens:
        raise ValueError("Empty SQL statement.")

    first_token = tokens[0]
    if first_token not in _ALLOWED_PREFIXES:
        allowed = ", ".join(sorted(_ALLOWED_PREFIXES))
        raise ValueError(
            f"Statement type '{first_token}' is not permitted. "
            f"Allowed prefixes: {allowed}."
        )

    for pattern in _FORBIDDEN_PATTERNS:
        if pattern.search(upper):
            raise ValueError(
                f"Forbidden keyword matched by pattern '{pattern.pattern}' in SQL."
            )


def validate_identifier(name: str, label: str = "identifier") -> None:
    """Validate a MySQL identifier to prevent injection attacks."""
    if not name:
        raise ValueError(f"Empty {label}.")
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(
            f"Invalid {label} '{name}': "
            "only letters, digits, and underscores are allowed."
        )


def _parse_table_blacklist(raw: str) -> frozenset[str]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    for name in values:
        validate_identifier(name, "blacklisted table name")
    return frozenset(name.lower() for name in values)


QUERY_TABLE_BLACKLIST: frozenset[str] = _parse_table_blacklist(
    QUERY_TABLE_BLACKLIST_RAW
)


def _bilingual_error_payload(
    code: str, message_en: str, message_zh: str, **extra: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message_en": message_en,
            "message_zh": message_zh,
        }
    }
    payload["error"].update(extra)
    return payload


def _extract_referenced_tables(sql: str) -> set[str]:
    tables: set[str] = set()

    for match in _FROM_JOIN_RE.finditer(sql):
        table = match.group(2) or match.group(1)
        if table:
            tables.add(table.lower())

    describe_match = _DESCRIBE_RE.match(sql)
    if describe_match:
        table = describe_match.group(2) or describe_match.group(1)
        if table:
            tables.add(table.lower())

    show_match = _SHOW_TABLE_TARGET_RE.match(sql)
    if show_match:
        table = show_match.group(2) or show_match.group(1)
        if table:
            tables.add(table.lower())

    return tables


def validate_table_blacklist_for_sql(sql: str) -> None:
    if not QUERY_TABLE_BLACKLIST:
        return

    blocked_tables = sorted(
        table
        for table in _extract_referenced_tables(sql)
        if table in QUERY_TABLE_BLACKLIST
    )
    if blocked_tables:
        raise ValueError(
            json.dumps(
                _bilingual_error_payload(
                    code="TABLE_DATA_BLOCKED",
                    message_en=(
                        "Data query on blacklisted table(s) is not allowed. "
                        "Use the describe_table tool to view the table structure."
                    ),
                    message_zh="黑名单中的表禁止查询数据，如需查看表结构请使用 describe_table 工具。",
                    blocked_tables=blocked_tables,
                ),
                ensure_ascii=False,
            )
        )



# ── MySQL Connection ───────────────────────────────────────────────────────────

def _get_connection() -> pymysql.Connection:
    """Open and return a new MySQL connection.

    Raises RuntimeError if required configuration is missing.
    """
    if not MYSQL_USER or not MYSQL_DATABASE:
        raise RuntimeError(
            "MySQL is not configured. "
            "Set MYSQL_USER and MYSQL_DATABASE via environment variables "
            "or the mcp.json 'env' section."
        )

    kwargs: dict[str, Any] = {
        "host": MYSQL_HOST,
        "port": MYSQL_PORT,
        "user": MYSQL_USER,
        "password": MYSQL_PASSWORD,
        "database": MYSQL_DATABASE,
        "connect_timeout": MYSQL_CONNECT_TIMEOUT,
        "cursorclass": pymysql.cursors.DictCursor,
        "charset": "utf8mb4",
    }
    if MYSQL_SSL:
        kwargs["ssl"] = {}

    return pymysql.connect(**kwargs)


# ── MCP Tools ─────────────────────────────────────────────────────────────────

@mcp.tool()
def query(sql: str, limit: int = QUERY_DEFAULT_LIMIT) -> dict[str, Any]:
    """Execute a readonly SQL query (SELECT / SHOW / DESCRIBE / EXPLAIN).

    Args:
        sql:   Readonly SQL statement to execute.
        limit: Maximum rows returned for SELECT queries that have no LIMIT clause.
               Capped at QUERY_DEFAULT_LIMIT from server config.

    Returns:
        dict with keys:
            columns   – list of column names
            rows      – list of row dicts
            row_count – number of rows returned
    """
    validate_readonly_sql(sql)
    validate_table_blacklist_for_sql(sql)

    effective_limit = min(max(1, limit), QUERY_DEFAULT_LIMIT)

    # Auto-append LIMIT to bare SELECT queries
    upper_stripped = sql.strip().upper()
    if upper_stripped.startswith("SELECT") and not re.search(
        r"\bLIMIT\b", upper_stripped
    ):
        sql = sql.rstrip("; \t\n") + f" LIMIT {effective_limit}"

    conn = _get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            rows: list[dict[str, Any]] = list(cursor.fetchall())
            columns: list[str] = (
                [desc[0] for desc in cursor.description]
                if cursor.description
                else []
            )
            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
            }
    finally:
        conn.close()


@mcp.tool()
def list_tables() -> dict[str, Any]:
    """List all tables in the configured MySQL database.

    Returns:
        dict with keys:
            database – current database name
            tables   – list of table name strings
            count    – number of tables
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            rows: list[dict[str, Any]] = list(cursor.fetchall())
            table_names: list[str] = [list(row.values())[0] for row in rows]
            return {
                "database": MYSQL_DATABASE,
                "tables": table_names,
                "count": len(table_names),
            }
    finally:
        conn.close()


@mcp.tool()
def describe_table(table_name: str) -> dict[str, Any]:
    """Get the column schema of a specific table.

    Args:
        table_name: Name of the table (letters, digits, underscores only).
                    Blacklisted tables are permitted here — structure inspection
                    is always allowed even when data queries are blocked.

    Returns:
        dict with keys:
            table   – table name
            columns – list of column definition dicts
                      (Field, Type, Null, Key, Default, Extra)
    """
    validate_identifier(table_name, "table name")
    conn = _get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"DESCRIBE `{table_name}`")
            columns: list[dict[str, Any]] = list(cursor.fetchall())
            return {
                "table": table_name,
                "columns": columns,
            }
    finally:
        conn.close()


# ── Entrypoint ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="MySQL Readonly MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Transport modes:
  stdio  (default) – communicate over stdin/stdout; ideal for mcp.json integration
                     in Cursor, Claude Desktop, and other MCP clients.
  sse              – run as an HTTP server with Server-Sent Events; clients connect
                     to http://<host>:<port>/sse.

Examples:
  python server.py                          # stdio mode
  python server.py --transport sse          # SSE on 0.0.0.0:8000
  python server.py --transport sse --port 9000
""",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport type (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default=MCP_HOST,
        help="Bind host for SSE transport (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=MCP_PORT,
        help="Bind port for SSE transport (default: %(default)s)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        print(
            f"[mysql-mcp] Starting SSE server on http://{args.host}:{args.port}/sse",
            file=sys.stderr,
        )
        print(
            f"[mysql-mcp] MySQL: {MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}",
            file=sys.stderr,
        )
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
