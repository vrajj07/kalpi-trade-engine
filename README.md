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

## Broker connections and authentication

**Flow:** the user logs in to their broker in the Kalpi app, then the app stores the resulting session:

```bash
curl -X PUT localhost:8000/api/v1/brokers/mock/connection -H "X-User-Id: demo-user" \
  -H "Content-Type: application/json" -d '{"access_token": "<token from the broker login>"}'
# optional: "client_id" (AngelOne client code), "expires_at" (when the broker expires the token)
```

Executions then need no token: the engine loads the stored session itself. That includes a resumed run
or a future queue worker. `GET` on the connection shows its status, and `DELETE` disconnects it.
`GET /brokers` lists every broker with the user's connection status.

- **Who the user is.** Every request carries `X-User-Id`, set by the upstream API gateway after it has
  authenticated the user. This is an internal service that trusts that header, so it must never be
  exposed publicly. Everything is scoped by it:
  - connections are keyed by `(user_id, broker)`
  - Idempotency-Keys are unique per user, so one user's key never replays another user's execution
  - another user's execution returns `404`, not `403`, so the API does not reveal that it exists
    (no IDOR, no existence oracle)
- **Tokens are encrypted at rest.** Fernet (AES + HMAC, from `cryptography`), keyed by
  `TOKEN_ENCRYPTION_KEYS`. `make env` generates the key.
  - Several comma-separated keys can be set, newest first: the first encrypts and any of them decrypts,
    so a key can be rotated without reconnecting everyone.
  - Tokens are never returned by the API or logged (`SecretStr`).
  - *Trust boundary:* this protects a leaked database, backup or replica. It does not protect against
    anyone who can read the app's environment, where the key lives. In production the key would come
    from a KMS or secrets manager (envelope encryption).
- **Only the user's session is per user.** App-level settings stay in the environment, because they
  identify Kalpi's app to the broker: `ZERODHA_API_KEY`, the Fyers app id, AngelOne's machine headers.
  A deployment-wide access token is deliberately not supported: any `X-User-Id` would trade on that
  one account.
- **Expiry.** Most brokers expire tokens daily, so a connection is typically refreshed once per trading
  day.
  - A `401` from the broker marks the connection `EXPIRED`, whether it comes from the holdings read or
    mid-run (the run aborts and asks the user to log in again).
  - A known `expires_at` expires it early, lazily on the next read, so an execution is rejected before
    any order is sent.
  - Reconnecting reactivates the connection.
- **Out of scope: each broker's login flow.** Examples: Zerodha's login URL, then `request_token`, then a
  checksum exchange for `access_token`; Fyers' `auth_code`; AngelOne's TOTP; Upstox and Groww OAuth.
  These are browser redirects owned by the Kalpi app and each broker's developer console. This service
  starts where they end, with a valid session.

## Rebalance logic

### Request

A request is **exactly one** of two modes.

**First-time portfolio: `target`.** The stocks and quantities to end up holding. The user must hold
nothing yet, and every stock becomes a `BUY`.

```bash
curl -X POST localhost:8000/api/v1/executions -H "X-User-Id: demo-user" \
  -H "Idempotency-Key: $(uuidgen)" -H "Content-Type: application/json" \
  -d '{"broker": "mock", "target": [
        {"symbol": "INFY", "quantity": 5},
        {"symbol": "TCS",  "quantity": 2}]}'
```

**Rebalance: `instructions`.** As the assignment specifies, the engine does not compute the delta: the
payload says what to do with each stock.

```bash
curl -X POST localhost:8000/api/v1/executions -H "X-User-Id: demo-user" \
  -H "Idempotency-Key: $(uuidgen)" -H "Content-Type: application/json" \
  -d '{"broker": "mock", "instructions": [
        {"action": "SELL",      "symbol": "INFY",  "quantity": 10},
        {"action": "REBALANCE", "symbol": "TCS",   "quantity": -2},
        {"action": "BUY",       "symbol": "WIPRO", "quantity": 3, "price": "250.50"}]}'
# 202 + Location: /api/v1/executions/{id}  ->  GET it for the report, GET .../events for the audit trail
```

- `price` makes it a LIMIT order; omitted means MARKET. One entry per symbol.
- `REBALANCE` carries a signed change: `-2` sells 2, `+2` buys 2.

### Validation against holdings

Before anything is saved or sent, the service reads the user's holdings from the broker and checks that
every action keeps its meaning:

| Request | Rule | If broken |
|---|---|---|
| `target` | Nothing is held | `409 PortfolioNotEmptyError`: send explicit instructions instead |
| `BUY` | The stock is not held (a new stock) | `422`, hint: `REBALANCE +q` |
| `SELL` | The stock is held, and `quantity` equals the whole holding (an exit) | `422`, hint: `REBALANCE -q` for a partial reduce |
| `REBALANCE -q` | The stock is held, and `q` is at most the holding | `422` |
| `REBALANCE +q` | The stock is held | `422`, hint: `BUY` |

- **SELL is strict.** A partial SELL would mean the same as `REBALANCE -q`, giving two ways to say one
  thing. Worse, it hides a disagreement between the model's view of the portfolio and the broker's: if the
  model thinks 7 are held but 10 are, a lenient SELL leaves 3 orphan shares. The strict rule rejects it at
  submission.
- **All errors at once.** Every broken rule is reported in `error.details`, with its index.
- **Fail closed.** If holdings cannot be read, nothing is saved or placed: `503`, or `401` for an expired
  broker session. Retrying with the same `Idempotency-Key` is safe, because the check runs before the
  execution record is written.
- **A replay is not re-checked.** A resumed execution's own fills have already changed the holdings.
- **A guard, not a guarantee.** See "Known limitations" (TOCTOU).

### Execution order: follow the money

| Phase | Orders | How |
|---|---|---|
| **RELEASE** | `SELL`, `REBALANCE` with negative quantity | in parallel |
| **SPEND** | `REBALANCE` with positive quantity, `BUY` | one at a time, in input order; each is tracked to a final state before the next |

Phases are decided by the **direction of money**, not the instruction type, because a REBALANCE can go
either way. Sells first so their proceeds fund the buys; buys sequential so the investor's ordering is
their priority and funding is never decided by a network race.

### Failure rules

- **Gate.** SPEND starts only after every RELEASE order is final. If any sell is **unresolved**
  (`UNCONFIRMED` or `STILL_OPEN`), no buy is sent: its funding is not proven to exist
  (an unconfirmed sell counts as zero cash).
- **Strict priority.** SPEND stops at the first order that is not `FILLED` or `FAILED`.
  - A rejection may mean insufficient funds.
  - An unknown outcome may already have used the money.
  - Later buys are `SKIPPED`, with the blocking order named in `message`. A cheaper buy never jumps the queue.
- **Failures before send don't block.** A `FAILED` order provably never reached the broker (unknown
  symbol, broker unreachable after retries), so it used no money.
- **Expired session aborts.** An auth failure is not transient. Retrying cannot help, so everything
  not yet sent is `SKIPPED` and the report asks the investor to log in again.
- **Fills count, not status.** A `CANCELLED` order with fills is `PARTIALLY_FILLED`, with `filled_quantity`.

### Never place an order twice

- **Retries.** The broker client only retries errors that prove the order was not executed
  (429, 503, connection refused). A timeout after send, a 5xx or an unreadable response is `UNKNOWN`.
  It is never re-sent: the executor looks up the order book for the order's tag until the order is found
  or the deadline passes. If it is never found, the order is `UNCONFIRMED`.
- **Deterministic tags.** Each order carries `tag = sha256(execution_id:position)[:20]`. A retry or resume
  of the same execution produces the same tag. Brokers do not reject duplicate tags, so this is
  **check-before-write** on our side.
- **Write-ahead record.** The whole plan is committed before the first order. Each order is saved as
  `SUBMITTING` *before* it is sent. On resume, a `SUBMITTING` order is looked up by tag and only sent
  if the broker has none.
- **Idempotency-Key** (required header):
  - same key and same body: returns the same execution, resuming it if a crash interrupted it
  - same key and a different body: `409`
  - a new key: a new execution
- **Expiry.** Executions expire at the next market close (IST). Order books only cover the current
  day, so a later resume could no longer find placed orders; it is marked `EXPIRED` instead.

### Order states in the report

`FILLED` · `PARTIALLY_FILLED` · `REJECTED` · `CANCELLED` · `FAILED` (never placed) · `SKIPPED` (not attempted) ·
`STILL_OPEN` (placed, not final within `ORDER_TIMEOUT_SECONDS`) · `UNCONFIRMED` (outcome never established).
The last two, plus partial fills, are listed in `needs_attention`. The investor must check the broker
before retrying them.

### State machine and audit log

- **Guarded transitions.** Every legal state change is declared in one table
  (`src/modules/execution/transitions.py`), and `transition_order` / `transition_execution` are the only
  code that changes state. Anything else raises `IllegalTransitionError`: a bug fails loudly instead of
  silently corrupting an order. Final states have no way out, so a `FILLED` order can never become `PLACED`,
  and an `UNKNOWN` order can never go back to `SUBMITTING` (that would mean sending it twice).
- **Append-only event log.** Each transition writes an `execution_events` row (from, to, message, time)
  in the same transaction as the state change, so the history and the current state cannot disagree.
  `GET /api/v1/executions/{id}/events` returns the trail, e.g. why a BUY was skipped and when.

**Why not a generic workflow engine (YAGNI).** This is already a durable, resumable workflow:
`Executor` is the workflow definition, the `executions` / `execution_orders` rows are the instance and
its checkpoints, `execution_events` is the event log, and `runner` is an in-process worker. There is only
one workflow type, and its hardest rules (the RELEASE/SPEND gate, strict priority, fills over status) are
domain-specific and would not fit a generic step/`depends_on` model. So only the two parts with value on
their own were built: the transition guard and the event log.

It generalises when a second workflow appears (for example scheduled SIP buys):
- `workflow_type` plus a per-type config of steps, transitions and dependencies
- one generic `transition()` that writes the event
- a worker that claims instances with a lease (owner + heartbeat) and resumes stuck ones itself, instead of
  waiting for the client to resubmit

### Notification

The final report goes to `NOTIFICATION_WEBHOOK_URL` if it is set; otherwise it is logged. Delivery is
at-least-once with 3 attempts, so consumers should deduplicate on `id`.

The mock broker is configured in `.env` (modes listed in `.env.example`):
- `MOCK_HOLDINGS={}` to try a first-time `target` portfolio
- `MOCK_CASH=1000` to trigger an insufficient-funds rejection
- `MOCK_FAIL={"INFY": "unknown"}` to try a failure mode

### Known limitations

- **Holdings checks are a guard, not a guarantee.**
  - *Time-of-check to time-of-use (TOCTOU):* holdings are read at submission, and the investor can still
    trade in the broker's own app before the orders are sent.
  - *Holdings are not the sellable quantity:* holdings are settled shares. Today's buys (still under
    positions), shares blocked by open orders and pledged shares are not counted.

  Only the broker can check and act atomically, so its rejection remains the source of truth, the same as
  for funds.
- **No funds pre-check.** The broker's rejection is the source of truth. A `get_funds()` pre-flight
  would let unaffordable buys be skipped with an exact reason before sending. It is only a snapshot
  (time-of-check to time-of-use, TOCTOU), so the broker's rejection would still be needed as a backstop.
- **Resumption is per process.** With several replicas, two could resume the same execution.
  A lease (owner + heartbeat, or `SELECT … FOR UPDATE SKIP LOCKED`) would make it exclusive.
- **No automatic recovery on startup.** A crashed run resumes when the client resubmits its key.
  Both this and per-process resumption are solved by queue workers; see "Path to production: execution workers".
- **No trading calendar.** Expiry ignores weekends and exchange holidays.
- **Unverified broker details.** Some broker response fields are marked `UNVERIFIED` in code: Fyers
  status codes and order-book tag format, the AngelOne rate limit, Groww order-status fields.
  They come from docs, not live calls.
- **The audit log is a single table.** `execution_events` only grows. See "Scaling the audit log".

### Scaling the audit log

At production volume, `execution_events` would be **range-partitioned by `created_at`, one partition per month**.

- **Pruning.** An execution lives within one trading day, because it expires at market close. The audit
  query can therefore add a narrow `created_at` window next to `execution_id` and touch one partition.
- **Retention.** Old months are removed with `DETACH PARTITION`, then archived to cold storage (for example
  Parquet on S3) for the regulatory retention period, instead of a large `DELETE` that bloats the table and
  loads vacuum.
- **Primary key.** It becomes `(id, created_at)`, because Postgres requires the partition key in every
  unique constraint.
- **Creating partitions.** Future partitions are created ahead of time by `pg_partman` or a scheduled job.
  A `DEFAULT` partition is avoided: rows that land in it block creating the matching partition later.
- **Why not broker first.** Broker is not partitioned on. The audit query does not filter on it, and volume
  is heavily skewed across brokers (a hot partition). A two-level layout would also multiply the partitions
  (brokers × months) that retention and query planning have to handle. Broker stays a filter, unless a
  broker-scoped requirement appears (per-broker retention or purge).
- **Sub-partitioning.** `HASH (execution_id)` sub-partitions only if a single month becomes too large.

The same applies to `execution_orders` if order volume grows. `create_all()` cannot declare partitions,
so this arrives together with Alembic (see "Schema management").

### Path to production: execution workers

Today the API process runs each execution as an in-process background task (`helpers/runner.py`). In
production, running would move to separate workers fed by a queue. `ExecutionModule.run(execution_id)` is
already the worker's entry point, so the change is in *who calls it*, not in the execution logic.

```
POST /executions ─► commit execution + outbox row (one transaction)
                          │
       relay ─────────────┘  publishes outbox rows
         │
         ▼
  SQS FIFO queue  (MessageGroupId = broker account)
         │
         ▼
  worker ─► claim lease ─► ExecutionModule.run(execution_id) ─► release lease
```

- **What it solves.**
  - *Exclusivity:* one consumer holds a message at a time, replacing the in-process `_tasks` registry.
  - *Automatic recovery:* a crashed worker's message becomes visible again and another worker resumes the
    execution, without the client resubmitting its key.
  - *Horizontal scaling:* workers scale independently of API replicas.
- **Ordering per broker account, not globally.** A single global FIFO would put every investor behind
  the slowest execution (head-of-line blocking; an order may wait `ORDER_TIMEOUT_SECONDS` to fill).
  Only executions on the **same broker account** must not overlap, because they compete for the same cash.
  So the `MessageGroupId` is the broker account: executions on the same account stay in order, and
  different accounts run in parallel.
- **The message carries only `execution_id`** (the claim-check pattern). The database stays the source of
  truth for the plan and its progress, and messages stay small.
- **No lost executions (dual write).** "Commit, then enqueue" can commit and then fail to enqueue, leaving
  the execution `RUNNING` forever. Instead, the execution and an outbox row are written in **one transaction**
  (the transactional outbox), and a relay publishes the outbox rows. A sweeper re-enqueues `RUNNING`
  executions whose lease has gone stale, as a backstop.
- **Duplicate deliveries are harmless.** Delivery is at-least-once, even with FIFO, and the consumer is
  idempotent:
  - a finished execution is skipped
  - orders keep their deterministic tags
  - a `SUBMITTING` or `UNKNOWN` order is looked up by tag, never re-sent
- **Long runs outlive the visibility timeout.** An execution can take minutes, longer than a message's
  visibility timeout. So a worker also claims a **lease** in the database (`lease_owner`, `lease_expires_at`,
  taken with `UPDATE … WHERE lease_expires_at < now()`) and renews it with a heartbeat. It extends the
  message's visibility at the same time. A second worker that receives the same message cannot claim the
  lease and leaves it alone.
- **Shutdown.** Workers stop taking messages, then cancel running executions the way `runner.shutdown()`
  does today. A cancelled run stays `RUNNING` and its message is redelivered.
- **Idempotency-Key is still needed.** The queue deduplicates *deliveries* of one execution. The key
  deduplicates *client requests*: a retried `POST` after a timeout must not create a second execution.

## Third-party libraries

_TODO_
