# Kalpi Trade Execution Engine

Portfolio trade execution engine: takes a target portfolio (or explicit rebalance instructions),
executes trades through a user's broker, and notifies the consumer with an execution report.

## Run

One command does everything (.env → dependencies → tests → Docker stack → health check):

```bash
make all
```

Or step by step:

```bash
make up          # builds and starts the stack in Docker, waits until healthy
curl localhost:8000/api/v1/health
make down
```

API docs: http://localhost:8000/api/v1/docs

## Local development

```bash
make install     # venv + dependencies
make db-up       # Postgres only, exposed on localhost:5433
make run         # uvicorn with --reload
make test
```

Run `make` to list all commands.

## Architecture

_TODO_

### Schema management

Tables are created on application startup with SQLAlchemy's `Base.metadata.create_all()`
(see `src/core/database.py`), instead of a migration tool such as Alembic.

**Why:** within a 24-hour build the schema changes constantly and there is no deployed data to
preserve. `create_all()` makes `docker compose up` produce a ready database with zero extra steps
and no migration files to keep in sync.

**Trade-offs (accepted deliberately):**

- **Create-only, not a migration.** `create_all()` creates *missing* tables; it never alters existing
  ones. Adding a column to a model will not change a table that already exists. During development
  the fix is to reset the volume: `docker compose down -v`.
- **No versioned schema history.** There is no record of what changed when, and no downgrade path.
- **Races under multiple replicas.** If several app instances start at once, they all run DDL
  concurrently. Schema changes should run as a single, separate deploy step, not inside app boot.
- **The app needs DDL privileges.** The runtime DB user can create tables, which violates least
  privilege. In production, migrations would run under a separate privileged role.

**Path to production:** introduce Alembic, generate a baseline revision from the current models
(`alembic revision --autogenerate`), run `alembic upgrade head` as a one-off job before rollout,
and remove `init_db()` from the startup lifespan.

## Rebalance logic

_TODO_

## Third-party libraries

_TODO_
