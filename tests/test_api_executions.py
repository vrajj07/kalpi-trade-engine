import time
import uuid

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from src.core.config import settings
from src.integrations.brokers import registry
from src.integrations.brokers.errors import BrokerAuthError, BrokerUnavailableError
from src.integrations.brokers.mock import MockBroker
from src.core.config.mock import MockConfig
from src.main import app
from src.modules.execution.helpers import runner
from src.modules import notification
from src.modules.notification.helpers.notifiers import ConsoleNotifier

URL = f"{settings.api_prefix}/executions"
BROKERS = f"{settings.api_prefix}/brokers"
REBALANCE = {"broker": "mock", "instructions": [
    {"action": "SELL", "symbol": "INFY", "quantity": 10},
    {"action": "REBALANCE", "symbol": "TCS", "quantity": 2},
    {"action": "BUY", "symbol": "WIPRO", "quantity": 3},
]}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(registry, "mock_config", MockConfig(holdings={"INFY": 10, "TCS": 5}))
    # A fresh user per test (the SQLite file is shared), connected to the mock broker.
    with TestClient(app, headers={"X-User-Id": f"user-{uuid.uuid4().hex[:8]}"}) as c:  # lifespan: creates tables
        assert c.put(f"{BROKERS}/mock/connection", json={"access_token": "mock-token"}).status_code == 200
        yield c
        # Let background runs finish rather than be cancelled mid-write at shutdown: SQLite has one
        # file-wide write lock, and a cancelled writer can hold it into the next test.
        deadline = time.monotonic() + 5
        while runner._tasks and time.monotonic() < deadline:
            time.sleep(0.01)


def submit(client, body=REBALANCE, key=None):
    return client.post(URL, json=body, headers={"Idempotency-Key": key or uuid.uuid4().hex})


def wait_finished(client, execution_id) -> dict:
    for _ in range(200):
        report = client.get(f"{URL}/{execution_id}").json()
        if report["state"] != "RUNNING":
            return report
        time.sleep(0.01)
    raise AssertionError("execution did not finish")


def test_rebalance_runs_to_completion(client):
    response = submit(client)
    assert response.status_code == 202
    assert response.headers["Location"].endswith(response.json()["id"])
    report = wait_finished(client, response.json()["id"])
    assert report["state"] == "COMPLETED"
    assert [(o["symbol"], o["phase"], o["state"]) for o in report["orders"]] == [
        ("INFY", "RELEASE", "FILLED"), ("TCS", "SPEND", "FILLED"), ("WIPRO", "SPEND", "FILLED")]
    assert report["summary"] == {"FILLED": 3}


def test_every_state_change_is_in_the_audit_log(client):
    execution_id = submit(client).json()["id"]
    report = wait_finished(client, execution_id)
    events = client.get(f"{URL}/{execution_id}/events").json()
    by_order: dict = {}
    for e in events:
        by_order.setdefault(e["order_id"], []).append((e["from_state"], e["to_state"]))
    assert by_order.pop(None) == [("RUNNING", "COMPLETED")]
    assert list(by_order.values()) == [[("PENDING", "SUBMITTING"), ("SUBMITTING", "FILLED")]] * 3
    assert events[-1]["to_state"] == report["state"]  # the execution closes last


def test_events_of_unknown_execution_is_404(client):
    assert client.get(f"{URL}/{uuid.uuid4()}/events").status_code == 404


def test_invalid_instructions_are_422_with_every_error(client):
    body = {"broker": "mock", "instructions": [{"action": "BUY", "symbol": "INFY", "quantity": 0},
                                               {"action": "SELL", "symbol": "INFY", "quantity": 1}]}
    response = submit(client, body)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "InvalidInstructionsError"
    assert len(error["details"]) == 2


def test_first_time_target_portfolio_buys_everything(client, monkeypatch):
    monkeypatch.setattr(registry, "mock_config", MockConfig(holdings={}))
    body = {"broker": "mock", "target": [{"symbol": "INFY", "quantity": 5}, {"symbol": "TCS", "quantity": 2}]}
    report = wait_finished(client, submit(client, body).json()["id"])
    assert [(o["action"], o["symbol"], o["quantity"], o["state"]) for o in report["orders"]] == [
        ("BUY", "INFY", 5, "FILLED"), ("BUY", "TCS", 2, "FILLED")]


def test_target_portfolio_with_existing_holdings_conflicts(client):
    response = submit(client, {"broker": "mock", "target": [{"symbol": "WIPRO", "quantity": 1}]})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PortfolioNotEmptyError"


def test_partial_sell_is_422_with_rebalance_hint(client):
    response = submit(client, {"broker": "mock", "instructions": [
        {"action": "SELL", "symbol": "INFY", "quantity": 4}]})
    assert response.status_code == 422
    assert "use REBALANCE -4" in response.json()["error"]["details"][0]


@pytest.mark.parametrize("error, status", [
    (BrokerUnavailableError("down", broker="mock"), 503),
    (BrokerAuthError("expired", broker="mock"), 401),
])
def test_holdings_read_failure_fails_closed(client, monkeypatch, error, status):
    async def fail(self):
        raise error
    monkeypatch.setattr(MockBroker, "get_holdings", fail)
    response = submit(client)
    assert response.status_code == status
    assert "id" not in response.json()  # nothing was persisted or placed
    connection = client.get(f"{BROKERS}/mock/connection").json()["status"]
    assert connection == ("EXPIRED" if status == 401 else "ACTIVE")  # a rejected session is not reused


def test_same_key_same_body_replays_without_trading_again(client):
    key = uuid.uuid4().hex
    first = submit(client, key=key).json()
    wait_finished(client, first["id"])
    again = submit(client, key=key)
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["id"] == first["id"]


def test_same_key_different_body_conflicts(client):
    key = uuid.uuid4().hex
    submit(client, key=key)
    other = {**REBALANCE, "instructions": REBALANCE["instructions"][:1]}
    assert submit(client, other, key=key).status_code == 409


def test_missing_idempotency_key_is_rejected(client):
    assert client.post(URL, json=REBALANCE).status_code == 422


def test_execution_needs_a_connected_broker(client):
    response = submit(client, {**REBALANCE, "broker": "zerodha"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BrokerNotConnectedError"


def test_brokers_endpoint_lists_all_five_plus_mock_with_connection(client):
    brokers = {b["name"]: b["connection"] for b in client.get(BROKERS).json()}
    assert set(brokers) == {"zerodha", "fyers", "angelone", "upstox", "groww", "mock"}
    assert (brokers["mock"], brokers["zerodha"]) == ("ACTIVE", None)


def test_connection_never_returns_the_token_and_can_be_removed(client):
    status = client.put(f"{BROKERS}/zerodha/connection", json={"access_token": "kite-secret"}).json()
    assert status["status"] == "ACTIVE" and "kite-secret" not in str(status)
    assert client.delete(f"{BROKERS}/zerodha/connection").status_code == 204
    assert client.get(f"{BROKERS}/zerodha/connection").status_code == 409


def test_token_past_its_expiry_is_rejected_before_trading(client):
    client.put(f"{BROKERS}/mock/connection", json={"access_token": "t", "expires_at": "2020-01-01T00:00:00Z"})
    response = submit(client)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "BrokerConnectionExpiredError"
    assert client.get(f"{BROKERS}/mock/connection").json()["status"] == "EXPIRED"
    # Reconnecting with a fresh token reactivates it.
    client.put(f"{BROKERS}/mock/connection", json={"access_token": "fresh"})
    assert submit(client).status_code == 202


def test_users_are_isolated(client):
    key = uuid.uuid4().hex
    mine = submit(client, key=key).json()["id"]
    other = {"X-User-Id": "someone-else"}
    assert client.get(f"{URL}/{mine}", headers=other).status_code == 404  # no reading others' executions
    assert client.get(f"{URL}/{mine}/events", headers=other).status_code == 404
    # The same Idempotency-Key from another user is their own key, not a replay of mine.
    client.put(f"{BROKERS}/mock/connection", json={"access_token": "t2"}, headers=other)
    theirs = client.post(URL, json=REBALANCE, headers={**other, "Idempotency-Key": key})
    assert theirs.status_code == 202 and theirs.json()["id"] != mine
    wait_finished(client, mine)


def test_missing_user_is_rejected(client):
    assert client.get(BROKERS, headers={"X-User-Id": ""}).status_code == 422


def test_finished_execution_report_is_delivered_through_the_outbox(client, monkeypatch):
    delivered = []

    class Recording(ConsoleNotifier):
        async def notify(self, event, report):
            delivered.append((event, report.id, report.state))

    monkeypatch.setattr(notification, "get_notifier", Recording)
    execution_id = submit(client).json()["id"]
    wait_finished(client, execution_id)
    for _ in range(200):
        if delivered:
            break
        time.sleep(0.01)
    assert delivered == [("execution.finished", uuid.UUID(execution_id), "COMPLETED")]
