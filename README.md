# Kalpi Trade Execution Engine

Portfolio trade execution engine: takes a target portfolio (or explicit rebalance instructions),
executes trades through a user's broker, and notifies the consumer with an execution report.

## Run

```bash
cp .env.example .env
docker compose up --build
curl localhost:8000/health
```

API docs: http://localhost:8000/docs

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
pytest
```

## Architecture

_TODO_

## Rebalance logic

_TODO_

## Third-party libraries

_TODO_
