import time
import uuid

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from src.core.config import settings
from src.integrations.brokers import registry
from src.core.config.mock import MockConfig
from src.main import app
from src.modules.notification.base import WebhookNotifier
from src.schemas.execution import ExecutionReport

URL = f"{settings.api_prefix}/executions"
REBALANCE = {"broker": "mock", "instructions": [
    {"action": "SELL", "symbol": "INFY", "quantity": 10},
    {"action": "REBALANCE", "symbol": "TCS", "quantity": 2},
    {"action": "BUY", "symbol": "WIPRO", "quantity": 3},
]}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(registry, "mock_config", MockConfig(holdings={"INFY": 10, "TCS": 5}))
    with TestClient(app) as c:  # runs the lifespan: creates tables
        yield c


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


def test_unconfigured_broker_is_rejected_before_anything_is_stored(client):
    response = submit(client, {**REBALANCE, "broker": "zerodha"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UnconfiguredBrokerError"


def test_brokers_endpoint_lists_all_five_plus_mock(client):
    brokers = {b["name"]: b["configured"] for b in client.get(f"{settings.api_prefix}/brokers").json()}
    assert set(brokers) == {"zerodha", "fyers", "angelone", "upstox", "groww", "mock"}
    assert brokers["mock"] is True


@respx.mock
async def test_webhook_retries_then_delivers_report():
    route = respx.post("https://hooks.test/kalpi").mock(side_effect=[httpx.Response(500), httpx.Response(200)])
    report = ExecutionReport.model_validate({
        "id": uuid.uuid4(), "broker": "mock", "state": "COMPLETED", "reason": None, "created_at": None,
        "expires_at": "2026-09-28T10:00:00Z", "finished_at": None, "orders": []})
    async with httpx.AsyncClient() as http:
        await WebhookNotifier("https://hooks.test/kalpi", http).notify(report)
    assert route.call_count == 2
