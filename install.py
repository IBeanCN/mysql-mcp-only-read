#!/usr/bin/env python3
"""
First-time setup for MySQL Readonly MCP Server.

Requires Python 3.10+ for the interpreter that runs this script — version is checked
immediately; on failure nothing else runs.

Creates `.venv` with `python -m venv`, then `python -m pip install -r requirements.txt`.
Optional: interactive wizard prints copy-paste-ready mcp.json JSON.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
SERVER_PY = ROOT / "server.py"
MIN_PYTHON = (3, 10)


def _require_host_python() -> None:
    if sys.version_info < MIN_PYTHON:
        print(
            f"ERROR: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required to run this installer.\n"
            f"  Current interpreter: {sys.executable}\n"
            f"  Version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            file=sys.stderr,
        )
        print(
            "\n  Use a newer interpreter, e.g.:\n"
            "    python3.12 install.py\n"
            "    py -3.12 install.py   (Windows)\n",
            file=sys.stderr,
        )
        sys.exit(1)


def _resolve_python_exe(cli_value: str | None) -> str:
    if not cli_value:
        return sys.executable
    found = shutil.which(cli_value)
    if found:
        return found
    p = Path(cli_value)
    if p.is_file():
        return str(p.resolve())
    return cli_value


def _venv_python() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _version_ok_subprocess(exe: str) -> tuple[bool, str]:
    try:
        out = subprocess.run(
            [
                exe,
                "-c",
                "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'); "
                "raise SystemExit(0 if sys.version_info >= (3, 10) else 1)",
            ],
            check=False,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        line = (out.stdout or "").strip().splitlines()
        ver = line[0] if line else "?"
        return out.returncode == 0, ver
    except OSError as e:
        return False, str(e)


def _create_venv(base_py: str) -> bool:
    try:
        subprocess.run(
            [base_py, "-m", "venv", str(VENV_DIR)],
            check=True,
            cwd=str(ROOT),
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: python -m venv failed: {e}", file=sys.stderr)
        return False


def _pip_install(py_exe: Path) -> bool:
    try:
        subprocess.run(
            [str(py_exe), "-m", "ensurepip", "--upgrade"],
            check=True,
            cwd=str(ROOT),
        )
    except subprocess.CalledProcessError:
        print(
            "Note: ensurepip failed (some Linux images). Continuing.",
            file=sys.stderr,
        )
    try:
        subprocess.run(
            [str(py_exe), "-m", "pip", "install", "-r", str(REQUIREMENTS)],
            check=True,
            cwd=str(ROOT),
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: pip install failed: {e}", file=sys.stderr)
        return False


def _inp(prompt: str, default: str = "") -> str:
    tip = f" [{default}]" if default else ""
    try:
        line = input(f"{prompt}{tip}: ").strip()
    except EOFError:
        return default
    return line if line else default


def _inp_yes(prompt: str, default: bool = False) -> bool:
    d = "Y/n" if default else "y/N"
    s = _inp(f"{prompt} ({d})", "y" if default else "n").lower()
    return s in ("y", "yes", "1", "true")


def run_config_wizard(py_exe: Path) -> None:
    print()
    print("=" * 60)
    print("  MCP configuration wizard (copy-paste output into Cursor mcp.json)")
    print("=" * 60)
    print("  Do not commit passwords or bearer tokens to public repositories.")
    print()

    transport = _inp("Transport: stdio or sse", "stdio").lower()
    if transport not in ("stdio", "sse"):
        transport = "stdio"

    host = _inp("MYSQL_HOST", "127.0.0.1")
    port = _inp("MYSQL_PORT", "3306")
    user = _inp("MYSQL_USER", "root")
    password = _inp("MYSQL_PASSWORD", "")
    database = _inp("MYSQL_DATABASE", "your_database_name")
    print(
        "  (Blacklist: `query` cannot read these tables; `describe_table` still works.)"
    )
    blacklist = _inp(
        "QUERY_TABLE_BLACKLIST (comma-separated table names, empty for none)",
        "",
    )

    env: dict[str, str] = {
        "MYSQL_HOST": host,
        "MYSQL_PORT": port,
        "MYSQL_USER": user,
        "MYSQL_PASSWORD": password,
        "MYSQL_DATABASE": database,
        "MYSQL_CONNECT_TIMEOUT": "10",
        "MYSQL_SSL": "false",
        "QUERY_DEFAULT_LIMIT": "100",
        "QUERY_TABLE_BLACKLIST": blacklist,
    }

    if _inp_yes("Configure optional MySQL / query settings?", False):
        env["MYSQL_CONNECT_TIMEOUT"] = _inp("MYSQL_CONNECT_TIMEOUT", env["MYSQL_CONNECT_TIMEOUT"])
        env["MYSQL_READ_TIMEOUT"] = _inp("MYSQL_READ_TIMEOUT", "30")
        env["MYSQL_WRITE_TIMEOUT"] = _inp("MYSQL_WRITE_TIMEOUT", "30")
        env["MYSQL_MAX_EXECUTION_TIME"] = _inp("MYSQL_MAX_EXECUTION_TIME", "30000")
        env["QUERY_DEFAULT_LIMIT"] = _inp("QUERY_DEFAULT_LIMIT", env["QUERY_DEFAULT_LIMIT"])
        env["QUERY_TABLE_BLACKLIST"] = _inp(
            "QUERY_TABLE_BLACKLIST (comma-separated, edit or Enter to keep)",
            env["QUERY_TABLE_BLACKLIST"],
        )

        if _inp_yes("Enable MySQL TLS (MYSQL_SSL=true)?", False):
            env["MYSQL_SSL"] = "true"
            env["MYSQL_SSL_CA"] = _inp("MYSQL_SSL_CA (path, optional)", "")
            env["MYSQL_SSL_CERT"] = _inp("MYSQL_SSL_CERT (optional)", "")
            env["MYSQL_SSL_KEY"] = _inp("MYSQL_SSL_KEY (optional)", "")
            env["MYSQL_SSL_VERIFY_CERT"] = _inp("MYSQL_SSL_VERIFY_CERT", "true")
        else:
            env["MYSQL_SSL"] = _inp("MYSQL_SSL", "false")

    cmd = str(py_exe.absolute())
    arg0 = str(SERVER_PY.absolute())
    name = _inp("MCP server id in mcp.json", "mysql-readonly")

    if transport == "stdio":
        clean_env = {k: v for k, v in env.items() if v != ""}
        block = {
            "command": cmd,
            "args": [arg0],
            "env": clean_env,
        }
        out = {"mcpServers": {name: block}}
        print()
        print("--- Paste under your MCP config root (merge mcpServers) ---")
        print(json.dumps(out, indent=2, ensure_ascii=False))
        print("--- end ---")
        return

    mcp_host = _inp("MCP_HOST (bind address for server)", "127.0.0.1")
    mcp_port = _inp("MCP_PORT", "8000")
    bearer = _inp("MCP_BEARER_TOKEN (empty to disable)", "")

    sse_env = {**env, "MCP_HOST": mcp_host, "MCP_PORT": mcp_port}
    if bearer:
        sse_env["MCP_BEARER_TOKEN"] = bearer
    sse_env = {k: v for k, v in sse_env.items() if v != ""}

    client_host = "127.0.0.1" if mcp_host in ("0.0.0.0", "::") else mcp_host
    if client_host == "::":
        client_host = "127.0.0.1"
    url = f"http://{client_host}:{mcp_port}/sse"

    client = {"mcpServers": {name: {"url": url}}}
    if bearer:
        print()
        print("Note: Your MCP client must send Authorization: Bearer <token> if the server uses MCP_BEARER_TOKEN.")

    print()
    print("--- 1) Start the server with these environment variables ---")
    lines = [f'export {k}="{v}"' for k, v in sse_env.items()]
    print("\n".join(lines))
    print("# Windows CMD: use  set VAR=value  for each variable above")
    print(f'{cmd} "{arg0}" --transport sse --host {mcp_host} --port {mcp_port}')
    print()
    print("--- 2) MCP client config (SSE) ---")
    print(json.dumps(client, indent=2, ensure_ascii=False))
    print("--- end ---")
    if mcp_host == "0.0.0.0":
        print()
        print("Hint: Server listens on all interfaces; use your machine IP instead of 127.0.0.1 in url if connecting remotely.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create .venv and install deps; optional MCP config wizard.",
    )
    parser.add_argument(
        "--python",
        metavar="EXE",
        help="Interpreter for `python -m venv` (must be 3.10+; default: same as this process).",
    )
    parser.add_argument("--recreate", action="store_true", help="Delete .venv and recreate.")
    parser.add_argument("--dry-run", action="store_true", help="Show plan only.")
    parser.add_argument(
        "--no-wizard",
        action="store_true",
        help="Skip interactive mcp.json wizard after successful install.",
    )
    args = parser.parse_args()

    _require_host_python()

    if not REQUIREMENTS.is_file():
        print(f"ERROR: Missing {REQUIREMENTS}", file=sys.stderr)
        return 1
    if not SERVER_PY.is_file():
        print(f"ERROR: Missing {SERVER_PY}", file=sys.stderr)
        return 1

    if args.python:
        base_py = _resolve_python_exe(args.python)
        ok, ver = _version_ok_subprocess(base_py)
        if not ok:
            print(
                f"ERROR: --python must be {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+: {base_py!r} ({ver})",
                file=sys.stderr,
            )
            return 1
        base_py_for_venv = base_py
        ver_display = ver
    else:
        base_py_for_venv = sys.executable
        ver_display = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    if args.dry_run:
        print("[dry-run] Root:", ROOT)
        if args.recreate and VENV_DIR.exists():
            print("[dry-run] Would remove existing .venv first.")
        print("[dry-run] Create venv with:", base_py_for_venv, f"(Python {ver_display})")
        print("[dry-run] Then: <venv>/python -m pip install -r", REQUIREMENTS.name)
        vhint = (
            ".venv\\Scripts\\python.exe" if sys.platform == "win32" else ".venv/bin/python"
        )
        print("  mcp.json command → (absolute path to)", vhint)
        print("  mcp.json args    →", SERVER_PY.resolve())
        return 0

    if args.recreate and VENV_DIR.exists():
        print("Removing existing .venv ...")
        shutil.rmtree(VENV_DIR)

    if not VENV_DIR.exists():
        print(f"Creating .venv with: {base_py_for_venv} (Python {ver_display})")
        if not _create_venv(base_py_for_venv):
            return 1

    py_exe = _venv_python()
    if not py_exe.is_file():
        print(f"ERROR: Missing venv interpreter: {py_exe}", file=sys.stderr)
        return 1

    print("Installing dependencies into .venv ...")
    if not _pip_install(py_exe):
        print(f"Try: {py_exe} -m ensurepip --upgrade", file=sys.stderr)
        return 1

    print()
    print("Installation finished successfully.")
    print(f"Venv Python: {py_exe}")

    if not args.no_wizard:
        if sys.stdin.isatty():
            run_config_wizard(py_exe)
        else:
            print()
            print(
                "Skipping configuration wizard (stdin is not a TTY). "
                "Run install interactively to use the wizard, or pass --no-wizard."
            )
            print(f'  "command": {json.dumps(str(py_exe.absolute()))},')
            print(f'  "args": [{json.dumps(str(SERVER_PY.absolute()))}],')
    else:
        print()
        print("Skipped wizard (--no-wizard). Minimal stdio hints:")
        print(f'  "command": {json.dumps(str(py_exe.absolute()))},')
        print(f'  "args": [{json.dumps(str(SERVER_PY.absolute()))}],')
        print('  "env": { ... see README.md ... }')

    return 0


if __name__ == "__main__":
    sys.exit(main())
