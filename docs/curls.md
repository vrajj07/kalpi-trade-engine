# API requests (curl), for Postman

Import each command in Postman with **Import → Raw text**, pasting one curl at a time.

The commands use Postman variables. Set them once in an environment:

| Variable | Value |
|---|---|
| `base_url` | `http://localhost:8000/api/v1` |
| `user_id` | any id, e.g. `demo-user` (change it to get a clean user) |
| `idempotency_key` | any string of 8+ characters. Change it for each new execution; keep it to test a replay |
| `execution_id` | the `id` from a `POST /executions` response |

`{{$randomUUID}}` is a Postman built-in that generates a new value on every send.

The flows assume this mock broker setup in `.env`, applied with `make up`:
`MOCK_HOLDINGS={"INFY": 10, "TCS": 5}`, `MOCK_CASH=`, `MOCK_FAIL={}`.

---

## Health

### 1. Health (public, no user header) → 200
```bash
curl -X GET '{{base_url}}/health'
```

---

## Brokers

### 2. List brokers with this user's connection status → 200
```bash
curl -X GET '{{base_url}}/brokers' \
  -H 'X-User-Id: {{user_id}}'
```

### 3. Connect the mock broker → 200 (the response never contains the token)
```bash
curl -X PUT '{{base_url}}/brokers/mock/connection' \
  -H 'X-User-Id: {{user_id}}' \
  -H 'Content-Type: application/json' \
  -d '{"access_token": "mock-token"}'
```

### 4. Connect with a client id and a known expiry (the AngelOne shape) → 200
```bash
curl -X PUT '{{base_url}}/brokers/mock/connection' \
  -H 'X-User-Id: {{user_id}}' \
  -H 'Content-Type: application/json' \
  -d '{"access_token": "mock-token", "client_id": "A123456", "expires_at": "2026-12-31T10:00:00Z"}'
```

### 5. Connect with an expiry in the past → 200. Later calls report the connection as EXPIRED
```bash
curl -X PUT '{{base_url}}/brokers/mock/connection' \
  -H 'X-User-Id: {{user_id}}' \
  -H 'Content-Type: application/json' \
  -d '{"access_token": "mock-token", "expires_at": "2020-01-01T00:00:00Z"}'
```
Then run 7 (holdings): it returns 401. Reconnect with 3 to continue.

### 6. Get the connection status → 200 (409 BrokerNotConnectedError if not connected)
```bash
curl -X GET '{{base_url}}/brokers/mock/connection' \
  -H 'X-User-Id: {{user_id}}'
```

### 7. Holdings from the broker → 200
```bash
curl -X GET '{{base_url}}/brokers/mock/holdings' \
  -H 'X-User-Id: {{user_id}}'
```

### 8. Disconnect → 204
```bash
curl -X DELETE '{{base_url}}/brokers/mock/connection' \
  -H 'X-User-Id: {{user_id}}'
```

### 9. Unknown broker → 422
```bash
curl -X GET '{{base_url}}/brokers/notabroker/connection' \
  -H 'X-User-Id: {{user_id}}'
```

---

## Executions

Connect first (request 3).

### 10. Rebalance: SELL, then REBALANCE, then BUY → 202
```bash
curl -X POST '{{base_url}}/executions' \
  -H 'X-User-Id: {{user_id}}' \
  -H 'Idempotency-Key: {{idempotency_key}}' \
  -H 'Content-Type: application/json' \
  -d '{
    "broker": "mock",
    "instructions": [
      {"action": "SELL", "symbol": "INFY", "quantity": 10},
      {"action": "REBALANCE", "symbol": "TCS", "quantity": 2},
      {"action": "BUY", "symbol": "WIPRO", "quantity": 3}
    ]
  }'
```
Copy the `id` from the response into `execution_id`.

### 11. Replay: send 10 again with the same key and body → 202, the same `id`, header `Idempotent-Replayed: true`
No new orders are placed.

### 12. Same key, different body → 409 IdempotencyKeyReusedError
```bash
curl -X POST '{{base_url}}/executions' \
  -H 'X-User-Id: {{user_id}}' \
  -H 'Idempotency-Key: {{idempotency_key}}' \
  -H 'Content-Type: application/json' \
  -d '{"broker": "mock", "instructions": [{"action": "BUY", "symbol": "WIPRO", "quantity": 1}]}'
```

### 13. Rebalance down (partial reduce) and a LIMIT buy → 202
```bash
curl -X POST '{{base_url}}/executions' \
  -H 'X-User-Id: {{user_id}}' \
  -H 'Idempotency-Key: {{$randomUUID}}' \
  -H 'Content-Type: application/json' \
  -d '{
    "broker": "mock",
    "instructions": [
      {"action": "REBALANCE", "symbol": "INFY", "quantity": -4},
      {"action": "BUY", "symbol": "HDFCBANK", "exchange": "NSE", "quantity": 2, "price": 1650.50}
    ]
  }'
```

### 14. Get the execution report → 200
```bash
curl -X GET '{{base_url}}/executions/{{execution_id}}' \
  -H 'X-User-Id: {{user_id}}'
```

### 15. Audit trail (every state change, oldest first) → 200
```bash
curl -X GET '{{base_url}}/executions/{{execution_id}}/events' \
  -H 'X-User-Id: {{user_id}}'
```

### 16. First-time portfolio (target mode) with holdings present → 409 PortfolioNotEmptyError
```bash
curl -X POST '{{base_url}}/executions' \
  -H 'X-User-Id: {{user_id}}' \
  -H 'Idempotency-Key: {{$randomUUID}}' \
  -H 'Content-Type: application/json' \
  -d '{
    "broker": "mock",
    "target": [
      {"symbol": "INFY", "quantity": 5},
      {"symbol": "TCS", "quantity": 3}
    ]
  }'
```
Set `MOCK_HOLDINGS={}` and run `make up`, then send it again: → 202, with BUY orders only.

---

## Validation errors

### 17. Partial SELL (SELL must exit the whole holding) → 422, hint: use REBALANCE -5
```bash
curl -X POST '{{base_url}}/executions' \
  -H 'X-User-Id: {{user_id}}' \
  -H 'Idempotency-Key: {{$randomUUID}}' \
  -H 'Content-Type: application/json' \
  -d '{"broker": "mock", "instructions": [{"action": "SELL", "symbol": "INFY", "quantity": 5}]}'
```

### 18. Every rule at once (fail-slow): BUY a held stock, SELL one not held, REBALANCE beyond the holding → 422, with all errors listed in `details`
```bash
curl -X POST '{{base_url}}/executions' \
  -H 'X-User-Id: {{user_id}}' \
  -H 'Idempotency-Key: {{$randomUUID}}' \
  -H 'Content-Type: application/json' \
  -d '{
    "broker": "mock",
    "instructions": [
      {"action": "BUY", "symbol": "TCS", "quantity": 1},
      {"action": "SELL", "symbol": "RELIANCE", "quantity": 1},
      {"action": "REBALANCE", "symbol": "INFY", "quantity": -50}
    ]
  }'
```

### 19. The same symbol twice → 422
```bash
curl -X POST '{{base_url}}/executions' \
  -H 'X-User-Id: {{user_id}}' \
  -H 'Idempotency-Key: {{$randomUUID}}' \
  -H 'Content-Type: application/json' \
  -d '{
    "broker": "mock",
    "instructions": [
      {"action": "BUY", "symbol": "WIPRO", "quantity": 1},
      {"action": "BUY", "symbol": "WIPRO", "quantity": 2}
    ]
  }'
```

### 20. Both `target` and `instructions` → 422
```bash
curl -X POST '{{base_url}}/executions' \
  -H 'X-User-Id: {{user_id}}' \
  -H 'Idempotency-Key: {{$randomUUID}}' \
  -H 'Content-Type: application/json' \
  -d '{
    "broker": "mock",
    "target": [{"symbol": "INFY", "quantity": 1}],
    "instructions": [{"action": "BUY", "symbol": "WIPRO", "quantity": 1}]
  }'
```

### 21. Missing Idempotency-Key → 422
```bash
curl -X POST '{{base_url}}/executions' \
  -H 'X-User-Id: {{user_id}}' \
  -H 'Content-Type: application/json' \
  -d '{"broker": "mock", "instructions": [{"action": "BUY", "symbol": "WIPRO", "quantity": 1}]}'
```

---

## Authentication and tenancy

### 22. No user header → 401
```bash
curl -X GET '{{base_url}}/brokers'
```

### 23. Another user's execution → 404, not 403 (the API doesn't reveal that it exists)
```bash
curl -X GET '{{base_url}}/executions/{{execution_id}}' \
  -H 'X-User-Id: someone-else'
```

### 24. Execution before connecting a broker → 409 BrokerNotConnectedError
```bash
curl -X POST '{{base_url}}/executions' \
  -H 'X-User-Id: never-connected-user' \
  -H 'Idempotency-Key: {{$randomUUID}}' \
  -H 'Content-Type: application/json' \
  -d '{"broker": "mock", "instructions": [{"action": "BUY", "symbol": "WIPRO", "quantity": 1}]}'
```

### 25. Unknown execution id → 404
```bash
curl -X GET '{{base_url}}/executions/00000000-0000-0000-0000-000000000000' \
  -H 'X-User-Id: {{user_id}}'
```

---

## Failure modes (change `.env`, then `make up`, then send 10 with a new key)

| `.env` | Expected in the report (14) |
|---|---|
| `MOCK_FAIL={"WIPRO": "reject"}` | WIPRO `REJECTED` |
| `MOCK_FAIL={"INFY": "unknown"}` | INFY reconciled by tag; if unconfirmed, the buys are `SKIPPED` (the gate) |
| `MOCK_FAIL={"INFY": "open"}` | INFY `STILL_OPEN` after the order timeout; buys `SKIPPED` |
| `MOCK_FAIL={"TCS": "partial"}` | TCS `PARTIALLY_FILLED` |
| `MOCK_FAIL={"INFY": "rate_limit"}` | retried after `Retry-After`, then placed |
| `MOCK_FAIL={"WIPRO": "auth"}` | execution `ABORTED`; 6 shows the connection `EXPIRED` |
| `MOCK_CASH=1000` | buys rejected for insufficient funds |

Notifications: the report shows up in `make logs` (`[execution.finished]`), or at `NOTIFICATION_WEBHOOK_URL` if it is set.
