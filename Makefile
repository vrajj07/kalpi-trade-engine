.DEFAULT_GOAL := help

VENV   := .venv
PYTHON := $(VENV)/bin/python
PIP    := $(VENV)/bin/pip

.PHONY: help all venv install env run test docker-build up down logs health db-up db-shell clean

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

all: env install test up health ## One command: .env -> deps -> tests -> Docker stack -> health check
	@echo "\n✓ Stack is up: http://localhost:8000/api/v1/docs"

$(VENV):
	python3 -m venv $(VENV)

venv: $(VENV) ## Create the virtualenv

install: $(VENV) ## Install app + dev dependencies
	$(PIP) install -r requirements-dev.txt

env: ## Create .env from .env.example (won't overwrite)
	@test -f .env || cp .env.example .env

run: env ## Run the API locally with auto-reload (start the DB first: make db-up)
	$(PYTHON) -m uvicorn src.main:app --reload --port 8000

test: ## Run tests
	$(PYTHON) -m pytest -q

docker-build: ## Build the Docker image
	docker compose build

up: env ## Start the stack in Docker (waits until containers are healthy)
	docker compose up --build -d --wait

down: ## Stop the stack
	docker compose down

logs: ## Tail container logs
	docker compose logs -f api

health: ## Check the API health endpoint
	@curl -fsS http://localhost:8000/api/v1/health && echo

db-up: env ## Start only Postgres (for `make run` on the host)
	docker compose up -d --wait db

db-shell: ## Open psql inside the Postgres container
	docker compose exec db psql -U kalpi -d kalpi

clean: ## Remove caches and the virtualenv
	rm -rf $(VENV) .pytest_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
