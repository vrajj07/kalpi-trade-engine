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

Try every endpoint:
- **Postman:** import `docs/kalpi.postman_collection.json` and `docs/kalpi.postman_environment.json`, select
  the `kalpi` environment, and run the collection (every request has tests). The mock broker needs
  `MOCK_HOLDINGS={"INFY": 10, "TCS": 5}` in `.env`.
- **curl:** `docs/curls.md` lists each request with its expected status.

## Local development

```bash
make install     # venv + dependencies
make db-up       # Postgres only, exposed on localhost:5433
make run         # uvicorn with --reload
make test
```

Run `make` to list all commands.

## Architecture

```
HTTP ─► api/ (routers)          parse and shape the request; authentication (core/auth.py)
          │
          ▼
        service/                one class per use case: gather data, validate semantics,
          │                     orchestrate, convert domain errors to HTTP errors
          ▼
        modules/                the domain: one facade class per module
          │  execution/         ExecutionModule: plan, write-ahead record, run, state machine
          │  broker/            BrokerModule: users' connections, encrypted tokens, expiry
          │  notification/      NotificationModule: outbox relay, delivery, retries
          │
          ├─► dao/ ─► utils/database.py (DatabaseService) ─► PostgreSQL
          └─► integrations/brokers/  one adapter per broker, behind BrokerAdapter
```

Dependencies point one way, top to bottom. A router never touches a DAO, a module never raises an HTTP
error, and nothing outside `integrations/brokers/` knows a broker's API.

### Layers

- **`api/`** (routers). Syntactic validation only, through the Pydantic schemas in `schemas/`: types,
  lengths, "exactly one of `target` or `instructions`". Authentication is applied once per router in
  `api/__init__.py` (see "Broker connections and authentication").
- **`service/`**. `ExecutionService` and `BrokerService` stay thin: they gather data (holdings from the
  broker, the stored connection), run the semantic validators, and call a module. Each method catches the
  module's errors, rolls back, and converts them with `to_http_exception`, so the HTTP mapping lives in one
  place per module.
- **`modules/`**. Each module exposes one facade class in its `__init__.py`, the only thing the service
  imports. Inside: `helpers/` (planner, lifecycle, runner, retry policy...), `validators/` (semantic checks,
  fail-slow so every error is reported at once), and `exceptions.py` (a `ModuleError` base with its HTTP
  mapping).
- **`dao/` and `utils/database.py`**. DAOs say *what* they need; the generic `DatabaseService` owns *how* it
  is queried and when the transaction commits, so query idioms live in one place.
- **`models/`**. One package per module, each with its own `enums.py`. Enums live with the models, not the
  modules, so models never import the domain.
- **`middlewares/error_handler.py`**. Every error leaves as the same envelope:
  `{"error": {"code", "message", "details"}}`.

### Broker adapters

Every broker implements `BrokerAdapter` (`integrations/brokers/base.py`), which is the only interface
the executor sees:

| Method | Used for |
|---|---|
| `place_order(order)` | send one order, tagged with its deterministic tag |
| `get_order(broker_order_id)` | poll an order until it is final |
| `find_order(tag)` | after a crash or a lost response: was this order placed? (never re-send blindly) |
| `get_holdings()` | validation at submission, and first-time detection |

Five real brokers (Zerodha, Fyers, AngelOne, Upstox, Groww) and a mock. Each broker is one package with the
same shape:

```
integrations/brokers/zerodha/
  adapter.py    BrokerAdapter implementation: domain in, domain out
  client.py     endpoints, auth headers, the broker's error envelope
  builder.py    domain OrderRequest ─► broker request schema
  mappers.py    broker response ─► domain BrokerOrder / Holding, status mapping
  enums.py      the broker's own codes
  schemas/      request / response models (Pydantic): a changed response shape fails loudly
```

- **One transport for all brokers.** `common/client.py` (`BaseBrokerClient`) owns HTTP, rate limiting,
  retries and error mapping. A broker client only adds its endpoints, headers and error parsing.
- **Errors carry the decision, not the code.** Broker errors map onto one taxonomy (`errors.py`): auth,
  rate limit, unavailable, rejected, instrument not found, *state unknown*. Callers decide from the class
  (and its `retryable` flag), never from a broker's error codes.
- **Retries only when provably safe.** A request is retried only when the broker provably did not act
  on it: `429`, `503`, or a connection that was never established. A timeout or `5xx` after an order `POST`
  becomes `OrderStateUnknownError` and is never retried; the executor reconciles it with `find_order(tag)`.
- **Rate limits per broker account.** A leaky-bucket limiter (`aiolimiter`) per `(broker, account)`, shared by
  every client for that account, with each broker's published order limit. `Retry-After` is honoured.
  In-process only: several replicas would need a distributed limiter (for example a Redis token bucket).
- **Composition root.** `registry.py` is the only place that reads broker configuration and maps a
  `BrokerName` to its adapter. Adding a broker is one package plus one registry line.

### Request lifecycle

`POST /executions` with an `Idempotency-Key`:

1. **Authenticate** (`core/auth.py`) and parse the body (`schemas/execution.py`).
2. **Replay check.** The key is looked up for this user. Same body: return (and resume) that execution.
   Different body: `409`.
3. **Validate** (`ExecutionValidator`): the instructions, then against live holdings from the broker (fail
   closed: `503` if they cannot be read, `401` if the session has expired).
4. **Plan and write ahead** (`ExecutionModule.create`). Every order is persisted with its phase, position
   and deterministic tag, before anything is sent.
5. **`202 Accepted`**, and the run starts in the background (`helpers/runner.py`).
6. **Run** (`executor.py`). RELEASE orders in parallel, the gate, then SPEND orders in sequence. Every state
   change goes through `transitions.py` and is logged in `execution_events`.
7. **Notify.** The final transition writes an outbox row in the same transaction; the relay delivers the
   report (see "Notification").

Where each design decision is explained:

| Decision | Section |
|---|---|
| Sell before buy, gate on unresolved sells | "Execution order: follow the money" |
| No duplicate orders (deterministic tags, write-ahead, reconcile by tag) | "Never place an order twice" |
| State machine guard and append-only audit log, not a workflow engine | "State machine and audit log" |
| Transactional outbox for notifications | "Notification" |
| Per-user encrypted broker sessions | "Broker connections and authentication" |
| Queue workers, partitioning | "Path to production", "Scaling the audit log" |

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
  exposed publicly.
  - `src/core/auth.py` reads it, and is applied to every router except health (`api/__init__.py`), so a
    new endpoint is authenticated by default. A missing or invalid header is `401`.
  - Swapping the header for a verified token (a signed JWT) changes only that file.

  Everything is scoped by it:
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

The final report goes to `NOTIFICATION_WEBHOOK_URL` if it is set; otherwise it is logged.

```
final transition ─► commit state + audit event + outbox row (one transaction)
                                                   │
      relay (poll every 5 s, woken on finish) ─────┘  claims due rows with a lease
         │
         ▼
  notifier (webhook / console) ─► SENT | retry later | FAILED
```

- **Transactional outbox.** "Commit the final state, then send" loses the report if the process dies in
  between (a dual write). Instead, the state machine (`transitions.py`) writes a `notification_outbox` row in
  the same transaction as the final state, next to the audit event. A crash can delay a report, not lose it.
- **Claim check.** The row holds the `execution_id`, not the report. The report is built at delivery time;
  the execution is final, so it no longer changes.
- **In-process relay** (`modules/notification/helpers/relay.py`). One background loop claims due rows
  (`FOR UPDATE SKIP LOCKED`), delivers them concurrently, and records each outcome. It polls on an interval
  and is woken when an execution finishes, so reports go out within moments. The poll is the guarantee; the
  wake only cuts latency.
- **Lease, not a held lock.** A claim commits before any HTTP call: it counts the attempt and pushes
  `next_attempt_at` out by `NOTIFICATION_LEASE_SECONDS`. No transaction stays open across a slow consumer,
  and a relay that dies mid-delivery leaves the row to be picked up again when the lease runs out.
- **Retry policy.** Timeouts, connection errors, `5xx`, `408`, `425` and `429` are retried with exponential
  backoff and full jitter, honouring `Retry-After`. Any other `4xx` (and a `3xx`: redirects are not
  followed) is a refusal and is dead-lettered at once, since retrying would repeat it. After
  `NOTIFICATION_MAX_ATTEMPTS` the row is `FAILED` with `last_error`, which is the dead-letter state.
- **At-least-once.** A lease can run out during a slow but successful delivery, and a response can be lost
  after the consumer processed it. Consumers deduplicate on the `X-Delivery-Id` header
  (`<execution_id>:<event>`).
- **Graceful shutdown.** The relay finishes the batch in flight before the app stops; past a grace period it
  is cancelled, which the lease makes safe.

Not built yet:
- **Per-user destinations.** One global webhook URL receives every user's report. A multi-tenant setup needs
  a per-user endpoint, registered with an SSRF check (`https` only, no private, loopback or link-local
  addresses, re-checked at connect time against DNS rebinding).
- **Signed payloads.** Consumers cannot tell our POST from a forged or replayed one. An HMAC-SHA256 signature
  over `timestamp.body` with a per-user secret (`X-Signature`, `X-Timestamp`, rejected if too old) would
  let them.

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

### Path to production: notification delivery

At scale, webhook delivery leaves the API process, so a slow or dead consumer endpoint cannot take API
capacity (a bulkhead). The relay stops POSTing and **publishes** outbox rows to a queue instead, and
separate delivery workers POST. That is one more `Notifier`; the outbox, the claim and the retry policy stay.

- **FIFO with `MessageGroupId` = user.** A user's reports arrive in order, and one user's dead endpoint only
  blocks that user's group (head-of-line blocking contained to one tenant). While there is a single event per
  execution, a standard queue would do; ordering starts to matter once `execution.started` or per-order events
  exist.
- **Failures go to a dead-letter queue** after `maxReceiveCount`, and the worker applies the same retryable
  vs terminal classification.
- **No runtime fallback to in-process delivery.** If the queue is unreachable, rows wait in the outbox and
  drain when it recovers. Falling back to in-process delivery would weaken durability exactly when the
  infrastructure is unhealthy, and could overtake messages already queued for the same user. Local
  development picks the in-process relay by configuration, not by fallback.

## Third-party libraries

Kept deliberately small: each library replaces code that is easy to get subtly wrong.

| Library | Used for | Why this one |
|---|---|---|
| `fastapi`, `uvicorn` | HTTP API, ASGI server | Async end to end, which suits an I/O-bound engine that waits on broker APIs. Request validation and OpenAPI docs come from the same Pydantic models. |
| `pydantic`, `pydantic-settings` | Request/response schemas, broker schemas, settings | One validation model everywhere: API bodies, broker responses (a changed shape fails loudly instead of flowing on as `None`), and typed settings from the environment with `SecretStr` for tokens. |
| `sqlalchemy[asyncio]` 2.0 | ORM and queries | Async sessions, typed `Mapped[...]` models, `WriteOnlyMapped` for the append-only audit log, `FOR UPDATE SKIP LOCKED` for the outbox. |
| `psycopg[binary]` 3 | PostgreSQL driver | The maintained successor to psycopg2, with native async support. |
| `httpx` | Broker REST calls, webhook delivery | Async, with timeouts and connection pooling. It separates *connect* errors (never reached the broker, safe to retry) from errors after the request was sent, which is what decides whether an order may be retried. |
| `tenacity` | Retrying broker calls | Declarative retry policy (which errors, how many attempts, exponential backoff with jitter, `Retry-After`), instead of a hand-written loop per call site. |
| `aiolimiter` | Per-account rate limiting | A small async leaky-bucket limiter; brokers publish per-second order limits. |
| `cryptography` | Encrypting broker tokens at rest | Fernet is authenticated encryption (AES-CBC + HMAC), so a tampered token fails to decrypt instead of decrypting to garbage. `MultiFernet` gives key rotation. The standard, audited choice, instead of combining primitives by hand. |

Development only:

| Library | Used for |
|---|---|
| `pytest`, `pytest-asyncio` | Tests, including async ones |
| `respx` | Mocking `httpx` at the transport layer: broker adapters and webhooks are tested against recorded response shapes, with no network |
| `aiosqlite` | API tests on a throwaway SQLite file, so `make test` needs no running database |

### Deliberately not used

- **Broker SDKs** (`kiteconnect`, `fyers-apiv3`, `smartapi-python`, the Upstox and Groww SDKs). Adapters
  call the REST APIs directly with `httpx`.
  - *Async.* The SDKs are mostly synchronous (built on `requests`); calling them would block the event loop
    or need a thread pool.
  - *One retry and error model.* Five SDKs mean five different error types and hidden retry behaviours.
    The one rule that matters most, never retry an order `POST` whose outcome is unknown, has to hold for
    every broker, so it lives in one shared transport (`common/client.py`) that we control.
  - *Testability and footprint.* Plain HTTP is mocked the same way for every broker, and five SDKs with
    their transitive dependencies stay out of the image.

  The cost is maintaining the request and response schemas ourselves. Pydantic schemas make a broker's
  API change fail loudly; fields not confirmed against a live account are marked `UNVERIFIED`.
- **Celery or Temporal.** One workflow type does not justify a workflow engine or a broker process; see
  "State machine and audit log" and "Path to production".
- **Alembic.** Deferred to production; see "Schema management".
- **Redis.** Not needed with one process; it would be the distributed rate limiter at several replicas.
