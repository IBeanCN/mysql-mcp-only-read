# MySQL 只读 MCP 服务

一个使用 Python 实现的 MCP（Model Context Protocol）服务，提供对 MySQL 的**只读**访问能力。

- 传输方式：`stdio`（推荐给 MCP 客户端）和 `HTTP/SSE`（独立进程）
- 安全限制：仅允许 `SELECT`、`SHOW`、`DESCRIBE`、`DESC`、`EXPLAIN`
- 配置：`stdio` 模式下 MySQL 等参数通过 `mcp.json` 的 `env` 注入；`SSE` 模式下在启动进程的环境变量中配置，并可选用 `MCP_BEARER_TOKEN` 保护 HTTP 端点
- 表黑名单：`QUERY_TABLE_BLACKLIST` 中的表禁止通过 **`query` 工具读数据**，仍可通过 **`describe_table` 查看表结构**

---

## 环境要求

- Python **3.10+**（运行 `install.py` 的解释器会先校验版本，**不符合则立即退出**，不会创建 venv 或安装依赖）
- 可访问的 MySQL 实例

## 安装

### 首次安装（推荐）

请用 **3.10+** 的 `python` / `python3` / `py -3` 执行 `install.py`。脚本用该解释器执行
`python -m venv .venv`，再在 `.venv` 中 `python -m pip install …`。MCP 配置请使用 **`.venv` 内** 的 python。

安装成功且 stdin 为终端时，会进入**交互向导**，依次询问：传输方式（**stdio** 或 **sse**）、MySQL 核心字段、**QUERY_TABLE_BLACKLIST**（必问）、可选超时与 **QUERY_DEFAULT_LIMIT** / TLS 路径；若选 **sse** 还会问 **MCP_HOST** / **MCP_PORT** / **MCP_BEARER_TOKEN**。向导会打印可粘贴的完整 `mcp.json` 片段，以及 sse 时的 `export` 行与启动命令。可用 **`--no-wizard`** 跳过；非交互 stdin 会自动跳过向导。

**Windows**（CMD 或资源管理器中双击）：

```bat
cd \path\to\MySQL_MCP
install.bat
```

常用参数：`--recreate`、`--dry-run`、`--no-wizard`、`--python EXE`（用指定 3.10+ 解释器创建 venv）。

若未安装 Python Launcher，请从 [python.org](https://www.python.org/downloads/) 安装 Python 3.10+ 并勾选加入 PATH，或执行 `py -3.12 install.py`。

**macOS / Linux**：

```bash
cd /path/to/MySQL_MCP
python3 install.py
```

若默认 `python3` 低于 3.10，请改用 `python3.12 install.py` 等；否则脚本会在第一步报错退出。

### 不使用脚本的手动安装

```bash
cd /path/to/MySQL_MCP
python3 -m venv .venv
# Windows: .venv\Scripts\pip install -r requirements.txt
# Unix:    .venv/bin/pip install -r requirements.txt
```

无论哪种方式，`mcp.json` 里的 `command` 请填 **虚拟环境内** 的 `python` / `python.exe`
绝对路径，不要依赖 PATH 上的裸 `python`。

---

## 通过 mcp.json 配置

MySQL 连接参数通过 MCP 配置文件注入。根据客户端场景选择以下两种方式。

### 方式 A：stdio（推荐）

客户端会以子进程方式启动 `server.py`，并通过 `env` 注入 MySQL 参数。

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

`args` 须为 `server.py` 的绝对路径。Windows 下 `command` 请使用
`C:\\path\\to\\MySQL_MCP\\.venv\\Scripts\\python.exe`（JSON 中反斜杠需转义）。

### 方式 B：HTTP/SSE

先启动独立服务。MySQL 相关变量写在进程环境（或 systemd / Docker 的 `environment`）中。

```bash
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export MYSQL_USER=your_mysql_user
export MYSQL_PASSWORD=your_mysql_password
export MYSQL_DATABASE=your_database_name

# 默认监听 127.0.0.1。仅在可信网络或反向代理后使用 0.0.0.0；对外暴露时建议设置
# MCP_BEARER_TOKEN，客户端需在 SSE / 消息请求上携带 Authorization: Bearer <token>
export MCP_BEARER_TOKEN=your-long-random-secret   # 可选，暴露服务时强烈推荐

# 安装后请在仓库根目录使用虚拟环境解释器：
# Unix/macOS:  .venv/bin/python server.py --transport sse --port 8000
# Windows:     .venv\Scripts\python.exe server.py --transport sse --port 8000
.venv/bin/python server.py --transport sse --port 8000
```

客户端配置（若启用了 Bearer，请在客户端中配置对应 Token）：

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

## 环境变量说明

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `MYSQL_HOST` | 否 | `127.0.0.1` | MySQL 主机 |
| `MYSQL_PORT` | 否 | `3306` | MySQL 端口 |
| `MYSQL_USER` | **是** | — | 用户名 |
| `MYSQL_PASSWORD` | 否 | `""` | 密码 |
| `MYSQL_DATABASE` | **是** | — | 数据库名 |
| `MYSQL_CONNECT_TIMEOUT` | 否 | `10` | TCP 连接超时（秒） |
| `MYSQL_READ_TIMEOUT` | 否 | `30` | 套接字读超时（秒） |
| `MYSQL_WRITE_TIMEOUT` | 否 | `30` | 套接字写超时（秒） |
| `MYSQL_MAX_EXECUTION_TIME` | 否 | `30000` | 单条查询服务端超时（毫秒），对应会话 `MAX_EXECUTION_TIME` |
| `MYSQL_SSL` | 否 | `false` | 是否对 MySQL 使用 TLS |
| `MYSQL_SSL_CA` | 否 | `""` | CA 证书路径 |
| `MYSQL_SSL_CERT` | 否 | `""` | 客户端证书路径 |
| `MYSQL_SSL_KEY` | 否 | `""` | 客户端私钥路径 |
| `MYSQL_SSL_VERIFY_CERT` | 否 | `true` | 设为 `false` 则跳过服务端证书校验（不推荐） |
| `QUERY_DEFAULT_LIMIT` | 否 | `100` | `SELECT` 最大返回行数；SQL 里显式写的 `LIMIT` 也会被压到此上限（并结合工具参数 `limit`） |
| `QUERY_TABLE_BLACKLIST` | 否 | `""` | 逗号分隔表名。**`query` 工具**引用这些表（含 `JOIN`）会拒绝；**`describe_table` 仍可查结构**。不能替代库端授权。 |
| `MCP_HOST` | 否 | `127.0.0.1` | SSE 监听地址（命令行 `--host` 可覆盖） |
| `MCP_PORT` | 否 | `8000` | SSE 端口（命令行 `--port` 可覆盖） |
| `MCP_BEARER_TOKEN` | 否 | `""` | 非空时要求 HTTP 请求带 `Authorization: Bearer <token>` |

---

## 可用工具

### `query`

执行只读 SQL，返回结构化 JSON。

- 参数：
  - `sql`：只读 SQL（`SELECT` / `SHOW` / `DESCRIBE` / `EXPLAIN`）
  - `limit`：与 `QUERY_DEFAULT_LIMIT` 取较小值作为有效上限；服务端会改写 `SELECT`，使显式 `LIMIT` 也不能超过该上限
- 返回：`columns`、`rows`、`row_count`

### `list_tables`

列出当前数据库全部表名。

### `describe_table`

查询指定表结构（`DESCRIBE`）。**即使表在 `QUERY_TABLE_BLACKLIST` 中，仍可使用本工具查看字段定义**；黑名单下请勿用 `query` 执行 `DESCRIBE`/`SELECT`，应使用本工具。

- 参数：
  - `table_name`：表名（仅允许字母、数字、下划线）

---

## 安全机制（只读防护）

服务端默认启用多层防护：

1. 白名单：首关键字必须是允许的只读语句类型。
2. 黑名单：拒绝 `INSERT`、`UPDATE`、`DELETE`、`DROP`、`ALTER` 等危险语句。
3. 多语句拦截：拒绝注入式多语句执行。
4. 标识符校验：`describe_table` 的表名会做合法性校验。
5. 查询表黑名单：列在 `QUERY_TABLE_BLACKLIST` 中的表，**不能通过 `query` 读数据**（含 `JOIN` 引用）；**`describe_table` 仍可查看其结构**。错误体为 JSON，含 `message_en` / `message_zh`。

建议在 MySQL 层面使用只读账号；应用层黑名单是辅助手段，**不能替代数据库授权**。

---

## 验证示例

```sql
-- 应该成功
SHOW TABLES;
SELECT * FROM your_table LIMIT 5;
DESCRIBE your_table;
EXPLAIN SELECT id FROM your_table;

-- 应该被拒绝
DELETE FROM your_table WHERE id = 1;
INSERT INTO your_table(name) VALUES('x');
SELECT 1; DROP TABLE your_table;
SELECT SLEEP(5);
```

---

## 本地调试（不经过 MCP 客户端）

```bash
pip install "mcp[cli]"

MYSQL_HOST=127.0.0.1 MYSQL_USER=root MYSQL_PASSWORD=secret MYSQL_DATABASE=mydb \
  mcp dev server.py

MYSQL_HOST=127.0.0.1 MYSQL_USER=root MYSQL_PASSWORD=secret MYSQL_DATABASE=mydb \
  .venv/bin/python server.py --transport sse
```

---

## 项目结构

```
MySQL_MCP/
├── server.py            # MCP 服务：工具、SQL 防护、MySQL 连接
├── install.py           # 首次安装：创建 venv 并 pip 安装依赖
├── install.bat          # Windows 下启动 install.py
├── mcp.json             # MCP 配置模板（stdio + SSE）
├── requirements.txt
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── README.md
└── README.zh-CN.md      # 本文件
```

---

## 后续可扩展方向

- 连接池（如 DBUtils / SQLAlchemy）
- 基于 AST 的 SQL 校验（sqlglot / sqlparse）
- 审计日志（时间、客户端、行数等）
- 按客户端限流
- 在反向代理上终止 HTTPS / mTLS，并与 `MCP_BEARER_TOKEN` 组合使用

---

## Docker 部署

### 使用 docker compose

先在项目根目录创建 `.env`：

```bash
MYSQL_HOST=host.docker.internal
MYSQL_PORT=3306
MYSQL_USER=your_mysql_user
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=your_database_name
```

请先在 [`docker-compose.yml`](docker-compose.yml) 中**取消注释** `ports` 段（示例为绑定宿主机 `127.0.0.1`），默认注释是为了减小暴露面。对外访问时建议在 `.env` 中设置 `MCP_BEARER_TOKEN`。

启动：

```bash
docker compose up -d
```

SSE 地址：`http://localhost:8000/sse`（或你映射的宿主机端口）

### 与本地 MySQL 容器联调

可在 `docker-compose.yml` 中取消注释 `mysql` 服务及 `depends_on` / `volumes`，按文件内说明启动本地数据库。

### 手动运行容器

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

---

## 许可证

本项目采用 MIT 协议，详见 `LICENSE`。
