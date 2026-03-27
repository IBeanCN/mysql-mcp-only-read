# MySQL 只读 MCP 服务

一个使用 Python 实现的 MCP（Model Context Protocol）服务，提供对 MySQL 的**只读**访问能力。

- 传输方式：`stdio`（推荐给 MCP 客户端）和 `HTTP/SSE`（独立服务）
- 安全限制：仅允许 `SELECT`、`SHOW`、`DESCRIBE`、`DESC`、`EXPLAIN`
- 配置方式：通过 `mcp.json` 传参，无需改代码即可切换数据库

---

## 环境要求

- Python 3.10+
- 可访问的 MySQL 实例

## 安装

```bash
cd /path/to/MySQL_MCP
pip install -r requirements.txt
```

---

## 通过 mcp.json 配置

MySQL 连接参数通过 MCP 配置文件注入。根据客户端场景选择以下两种方式。

### 方式 A：stdio（推荐）

客户端会以子进程方式启动 `server.py`，并通过 `env` 注入 MySQL 参数。

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
        "QUERY_DEFAULT_LIMIT": "100"
      }
    }
  }
}
```

### 方式 B：HTTP/SSE

先启动独立服务：

```bash
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export MYSQL_USER=your_mysql_user
export MYSQL_PASSWORD=your_mysql_password
export MYSQL_DATABASE=your_database_name

python server.py --transport sse --host 0.0.0.0 --port 8000
```

客户端配置：

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

## 可用工具

### `query`

执行只读 SQL，返回结构化 JSON。

- 参数：
  - `sql`：只读 SQL（`SELECT` / `SHOW` / `DESCRIBE` / `EXPLAIN`）
  - `limit`：当 `SELECT` 未写 `LIMIT` 时，使用服务端默认上限
- 返回：
  - `columns`
  - `rows`
  - `row_count`

### `list_tables`

列出当前数据库全部表名。

### `describe_table`

查询指定表结构。

- 参数：
  - `table_name`：表名（仅允许字母、数字、下划线）

---

## 安全机制（只读防护）

服务端默认启用多层防护：

1. 白名单：首关键字必须是允许的只读语句类型。
2. 黑名单：拒绝 `INSERT`、`UPDATE`、`DELETE`、`DROP`、`ALTER` 等危险语句。
3. 多语句拦截：拒绝注入式多语句执行。
4. 标识符校验：`describe_table` 的表名会做合法性校验。

建议在 MySQL 层面同时使用只读账号，形成双重保障。

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
```

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

启动：

```bash
docker compose up -d
```

SSE 地址：`http://localhost:8000/sse`

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
