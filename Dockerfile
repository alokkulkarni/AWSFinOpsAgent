# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/finops

WORKDIR /app

# Install package + agent (A2A/MCP) + api + dashboard extras so this one image runs every
# service: preflight, cost-tools MCP server, A2A agent/orchestrator servers, and the dashboard.
COPY pyproject.toml README.md ./
COPY finops_core ./finops_core
COPY apps ./apps
RUN pip install --no-cache-dir -e ".[agent,api,dashboard]"

# Config is also bind-mounted read-only at runtime via compose.
COPY config ./config

# Non-root runtime user; ~/.aws is mounted read-only into $HOME by compose.
RUN useradd -m -u 10001 finops && chown -R finops:finops /app
USER finops

ENTRYPOINT ["finops"]
CMD ["preflight"]
