# Football Data Platform — developer & deployment targets.
# `make up` is the single command that builds and runs the whole stack.
#
# Local dev uses a plain pip virtualenv at ./.venv (no uv). `make venv` creates
# it and installs everything editable; the other targets run tools out of it.

.DEFAULT_GOAL := help
VENV := .venv
PY := $(VENV)/bin/python
# On Windows the venv layout differs (Scripts/, python.exe). Override on the CLI
# if needed:  make test PY=.venv/Scripts/python.exe
.PHONY: help venv up down build run dev lint fmt typecheck test ingest clean

help: ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  %-12s %s\n", $$1, $$2}'

# --- Environment ------------------------------------------------------------
venv: ## Create ./.venv and install all packages + dev tooling (pip, editable).
	python -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements-dev.txt
	@for pkg in shared ingestion unification api ui app; do \
		$(PY) -m pip install --no-deps -e packages/$$pkg; \
	done

# --- Deployment (single entry point) ---------------------------------------
up: ## Build and run the whole stack via docker compose (single entry point).
	@test -f .env || cp .env.template .env
	docker compose up --build

down: ## Stop the stack.
	docker compose down

build: ## Build the app image.
	docker compose build

# --- Local dev (pip venv) ---------------------------------------------------
run: ## Run API + UI locally (uses .env; targets host Mongo at :27171).
	$(PY) -m fdp_app.cli

dev: ## Run Uvicorn with reload (API + NiceGUI hot-reload) against host Mongo.
	$(PY) -m uvicorn fdp_app.main:app --reload --host 0.0.0.0 --port $${APP_PORT:-8000}

lint: ## Ruff lint + format check.
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

fmt: ## Apply Ruff formatting + autofixes.
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

typecheck: ## Strict mypy over the shipped source (tests excluded; see pyproject).
	$(PY) -m mypy packages/shared/src packages/ingestion/src packages/unification/src packages/api/src packages/ui/src packages/app/src

test: ## Run unit + integration tests (integration auto-skips without Docker).
	$(PY) -m pytest

ingest: ## Trigger an ingestion run against a locally-running API.
	curl -s -X POST "http://localhost:$${APP_PORT:-8000}/api/ingestion/run" | python -m json.tool

clean: ## Remove the local virtualenv.
	rm -rf $(VENV)
