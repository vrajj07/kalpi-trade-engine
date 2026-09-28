import httpx
import pytest
import respx

from src.integrations.brokers.base import BrokerCredentials, OrderRequest
from src.integrations.brokers.enums import OrderStatus, Side
from src.integrations.brokers.errors import (
    BrokerAuthError,
    BrokerRateLimitError,
    BrokerRequestError,
    BrokerUnavailableError,
    OrderRejectedError,
    OrderStateUnknownError,
)
from src.integrations.brokers.common.client import BaseBrokerClient
from src.integrations.brokers.mock import MockBroker


def creds(**extra) -> BrokerCredentials:
    return BrokerCredentials(access_token="t", api_key="k", extra=extra)


def buy(symbol="INFY", qty=1) -> OrderRequest:
    return OrderRequest(symbol=symbol, side=Side.BUY, quantity=qty)


def test_limit_order_requires_price():
    with pytest.raises(ValueError):
        OrderRequest(symbol="INFY", side=Side.BUY, quantity=1, order_type="LIMIT")


async def test_mock_fills_and_updates_holdings():
    broker = MockBroker(creds(holdings={"INFY": 2}))
    order = await broker.place_order(buy(qty=3))
    assert order.status is OrderStatus.COMPLETE
    assert (await broker.get_order(order.broker_order_id)) == order
    assert [(h.symbol, h.quantity) for h in await broker.get_holdings()] == [("INFY", 5)]


async def test_mock_rejects_oversell_and_injected_failures():
    broker = MockBroker(creds(holdings={"INFY": 1}, fail={"TCS": "unavailable"}))
    with pytest.raises(OrderRejectedError):
        await broker.place_order(OrderRequest(symbol="INFY", side=Side.SELL, quantity=2))
    with pytest.raises(BrokerUnavailableError) as exc:
        await broker.place_order(buy("TCS"))
    assert exc.value.retryable


class FakeClient(BaseBrokerClient):
    broker = "fake"
    base_url = "https://broker.test"

    def headers(self):
        return {}


@pytest.mark.parametrize(
    ("response", "method", "error", "attempts"),
    [
        (httpx.Response(401), "POST", BrokerAuthError, 1),
        (httpx.Response(429, headers={"Retry-After": "2"}), "POST", BrokerRateLimitError, 3),  # not processed
        (httpx.Response(503), "POST", BrokerUnavailableError, 3),
        (httpx.ConnectError("refused"), "POST", BrokerUnavailableError, 3),  # never sent
        (httpx.Response(502), "POST", OrderStateUnknownError, 1),  # may have gone through: never resend
        (httpx.ReadTimeout("slow"), "POST", OrderStateUnknownError, 1),
        (httpx.Response(502), "GET", BrokerUnavailableError, 3),  # reads are idempotent
        (httpx.Response(400), "GET", BrokerRequestError, 1),
    ],
)
@respx.mock
async def test_error_classification_and_retries(response, method, error, attempts):
    route = respx.route(host="broker.test")
    if isinstance(response, Exception):
        route.mock(side_effect=response)
    else:
        route.mock(return_value=response)
    client = FakeClient(creds())
    with pytest.raises(error):
        await client.request(method, "/orders")
    assert route.call_count == attempts
    await client.aclose()


@respx.mock
async def test_throttled_order_succeeds_on_retry():
    route = respx.post("https://broker.test/orders").mock(side_effect=[
        httpx.Response(429), httpx.Response(200, json={"id": "1"}),
    ])
    client = FakeClient(creds())
    assert await client.request("POST", "/orders") == {"id": "1"}
    assert route.call_count == 2
    await client.aclose()


@respx.mock
async def test_unreadable_order_response_means_unknown_state():
    client = FakeClient(creds())
    with pytest.raises(OrderStateUnknownError):
        client.parse(dict[str, int], {"id": "not-a-number"}, after_write=True)
    await client.aclose()
