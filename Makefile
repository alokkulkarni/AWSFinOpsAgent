.PHONY: install preflight whoami config dashboard api docker-build docker-preflight sandbox-preflight test fmt clean

PY ?= python3

install:
	$(PY) -m pip install -e ".[agent,api,dashboard,dev]"

# Phase-0 smoke check: AWS identity (STS) + Bedrock model availability
preflight:
	$(PY) -m finops_core.cli preflight

whoami:
	$(PY) -m finops_core.cli whoami

config:
	$(PY) -m finops_core.cli config

# Placeholders until Phase 2 / Phase 5
dashboard:
	$(PY) -m streamlit run apps/dashboard/app.py --server.port 8501

api:
	$(PY) -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000

docker-build:
	docker build -t aws-finops-agent:dev .

docker-preflight:
	docker compose run --rm preflight

sandbox-preflight:
	docker compose -f docker-compose.yml -f docker-compose.sandbox.yml run --rm preflight

# Distributed stack (cost-tools MCP + cost-agent/orchestrator A2A + dashboard)
stack-up:
	docker compose up -d --build

stack-up-sandbox:
	docker compose -f docker-compose.yml -f docker-compose.sandbox.yml up -d --build

stack-logs:
	docker compose logs -f

stack-down:
	docker compose down

# Full stack + OpenTelemetry fan-out (collector -> Jaeger + Prometheus). UIs: Jaeger :16686,
# Prometheus :9090. See docs/OBSERVABILITY.md.
observability:
	docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build

observability-down:
	docker compose -f docker-compose.yml -f docker-compose.observability.yml down

# Publish the MCP servers on the host for IDE-over-HTTP (Claude Code/Cursor/VS Code).
# Agents: :8090 ask_finops, :8095 ask_devops.  Tools: :8081 cost :8082 optimize :8083 anomaly
# :8085 devops. See docs/IDE_INTEGRATION.md ("HTTP / Docker route").
mcp-http:
	docker compose -f docker-compose.yml -f docker-compose.mcp.yml up -d --build

mcp-http-down:
	docker compose -f docker-compose.yml -f docker-compose.mcp.yml down

# Run a single distributed service locally (each in its own shell)
serve-cost-tools:
	$(PY) -m finops_core.cli serve cost-tools
serve-cost-agent:
	$(PY) -m finops_core.cli serve cost-agent
serve-orchestrator:
	$(PY) -m finops_core.cli serve orchestrator

test:
	$(PY) -m pytest -q

fmt:
	$(PY) -m ruff check --fix . || true

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
