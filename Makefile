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

test:
	$(PY) -m pytest -q

fmt:
	$(PY) -m ruff check --fix . || true

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
