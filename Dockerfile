# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy only the server source
COPY server.py .

# Non-root user for least-privilege execution
RUN adduser --disabled-password --gecos "" mcpuser
USER mcpuser

# SSE transport port
EXPOSE 8000

# Default to SSE transport; override CMD for stdio
CMD ["python", "server.py", "--transport", "sse"]
