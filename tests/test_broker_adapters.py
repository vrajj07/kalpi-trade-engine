"""Wire-level contract tests: what each adapter sends, and how it parses what comes back."""
import json
from urllib.parse import parse_qs

import pytest
import respx

from src.integrations.brokers.angelone import AngelOneBroker
from src.integrations.brokers.base import BrokerCredentials, OrderRequest
from src.integrations.brokers.enums import Exchange, OrderStatus, Side
from src.integrations.brokers.errors import (
    BrokerAuthError,
    BrokerRateLimitError,
    BrokerRequestError,
    BrokerResponseError,
    InstrumentNotFoundError,
    OrderRejectedError,
    OrderStateUnknownError,
)
from src.integrations.brokers.fyers import FyersBroker
from src.integrations.brokers.groww import GrowwBroker
from src.integrations.brokers.common.instruments import InstrumentMaster, static_instruments
from src.integrations.brokers.registry import get_adapter, supported_brokers
from src.integrations.brokers.upstox import UpstoxBroker
from src.integrations.brokers.zerodha import ZerodhaBroker

CREDS = BrokerCredentials(access_token="tok", api_key="key")
SELL_LIMIT = OrderRequest(symbol="INFY", side=Side.SELL, quantity=3, order_type="LIMIT", price="1500.5", tag="kalpi0001")
INSTRUMENTS = {(Exchange.NSE, "INFY"): "1594"}
ANGEL_INSTRUMENTS = static_instruments("angelone", INSTRUMENTS)


def sent_json(route) -> dict:
    return json.loads(route.calls.last.request.content)


def test_registry_covers_every_broker():
    assert len(supported_brokers()) == 6
    assert isinstance(get_adapter("zerodha", CREDS), ZerodhaBroker)


def test_tag_must_satisfy_all_brokers():
    with pytest.raises(ValueError):
        OrderRequest(symbol="INFY", side=Side.BUY, quantity=1, tag="has-dash")


@respx.mock
async def test_zerodha():
    place = respx.post("https://api.kite.trade/orders/regular").respond(json={"status": "success", "data": {"order_id": "Z1"}})
    respx.get("https://api.kite.trade/orders/Z1").respond(json={"status": "success", "data": [
        {"status": "OPEN PENDING"},
        {"status": "COMPLETE", "filled_quantity": 3, "average_price": 1500.5},
    ]})
    async with ZerodhaBroker(CREDS) as broker:
        assert (await broker.place_order(SELL_LIMIT)).broker_order_id == "Z1"
        form = {k: v[0] for k, v in parse_qs(place.calls.last.request.content.decode()).items()}
        assert form == {"tradingsymbol": "INFY", "exchange": "NSE", "transaction_type": "SELL", "order_type": "LIMIT",
                        "quantity": "3", "product": "CNC", "validity": "DAY", "price": "1500.5", "tag": "kalpi0001"}
        assert place.calls.last.request.headers["Authorization"] == "token key:tok"
        order = await broker.get_order("Z1")
        assert (order.status, order.filled_quantity) == (OrderStatus.COMPLETE, 3)


@respx.mock
async def test_zerodha_token_exception_is_auth_error():
    respx.post("https://api.kite.trade/orders/regular").respond(
        403, json={"status": "error", "error_type": "TokenException", "message": "Session expired"})
    async with ZerodhaBroker(CREDS) as broker:
        with pytest.raises(BrokerAuthError):
            await broker.place_order(SELL_LIMIT)


@respx.mock
async def test_fyers():
    place = respx.post("https://api-t1.fyers.in/api/v3/orders/sync").respond(json={"s": "ok", "code": 1101, "id": "F1"})
    respx.get("https://api-t1.fyers.in/api/v3/orders").respond(json={"s": "ok", "orderBook": [
        {"id": "F1", "status": 5, "filledQty": 0, "message": "RMS: insufficient holdings"}]})
    async with FyersBroker(CREDS) as broker:
        assert (await broker.place_order(SELL_LIMIT)).broker_order_id == "F1"
        body = sent_json(place)
        assert (body["symbol"], body["side"], body["type"], body["productType"], body["limitPrice"]) == \
            ("NSE:INFY-EQ", -1, 1, "CNC", 1500.5)
        assert place.calls.last.request.headers["Authorization"] == "key:tok"
        assert (await broker.get_order("F1")).status is OrderStatus.REJECTED


@respx.mock
async def test_fyers_error_inside_http_200():
    respx.post("https://api-t1.fyers.in/api/v3/orders/sync").respond(json={"s": "error", "code": -16, "message": "bad token"})
    async with FyersBroker(CREDS) as broker:
        with pytest.raises(BrokerAuthError):
            await broker.place_order(SELL_LIMIT)


async def test_fyers_bse_unsupported():
    async with FyersBroker(CREDS) as broker:
        with pytest.raises(InstrumentNotFoundError):
            await broker.place_order(OrderRequest(symbol="INFY", exchange="BSE", side=Side.BUY, quantity=1))


@respx.mock
async def test_angelone():
    base = "https://apiconnect.angelone.in/rest/secure/angelbroking"
    place = respx.post(f"{base}/order/v1/placeOrder").respond(
        json={"status": True, "message": "SUCCESS", "data": {"orderid": "A1", "uniqueorderid": "uuid-1"}})
    respx.get(f"{base}/order/v1/details/uuid-1").respond(
        json={"status": True, "data": {"orderstatus": "complete", "filledshares": "3", "averageprice": 1500.5}})
    async with AngelOneBroker(CREDS, instruments=ANGEL_INSTRUMENTS) as broker:
        assert (await broker.place_order(SELL_LIMIT)).broker_order_id == "uuid-1"
        body = sent_json(place)
        assert (body["tradingsymbol"], body["symboltoken"], body["producttype"], body["ordertag"]) == \
            ("INFY-EQ", "1594", "DELIVERY", "kalpi0001")
        assert place.calls.last.request.headers["X-PrivateKey"] == "key"
        order = await broker.get_order("uuid-1")
        assert (order.status, order.filled_quantity) == (OrderStatus.COMPLETE, 3)


@respx.mock
async def test_angelone_rejection_inside_http_200():
    respx.post(url__regex=r".*/placeOrder").respond(json={"status": False, "message": "Invalid qty", "errorcode": "AB1011"})
    async with AngelOneBroker(CREDS, instruments=ANGEL_INSTRUMENTS) as broker:
        with pytest.raises(OrderRejectedError):
            await broker.place_order(SELL_LIMIT)


@respx.mock
async def test_angelone_token_failure_envelope_is_an_auth_error():
    # Token failures use a different envelope: "success" and camelCase "errorCode".
    respx.get(url__regex=r".*/getHolding").respond(
        json={"success": False, "message": "Invalid Token", "errorCode": "AG8001", "data": ""})
    async with AngelOneBroker(CREDS, instruments=ANGEL_INSTRUMENTS) as broker:
        with pytest.raises(BrokerAuthError):
            await broker.get_holdings()


@respx.mock
async def test_unexpected_response_shape_keeps_validation_details_out_of_the_message():
    respx.get(url__regex=r".*/getHolding").respond(json={"status": True, "data": "not-a-list"})
    async with AngelOneBroker(CREDS, instruments=ANGEL_INSTRUMENTS) as broker:
        with pytest.raises(BrokerResponseError) as exc:
            await broker.get_holdings()
    assert exc.value.message == "Unexpected response from angelone"


@respx.mock
async def test_upstox_uses_hft_host_for_orders():
    place = respx.post("https://api-hft.upstox.com/v3/order/place").respond(
        json={"status": "success", "data": {"order_ids": ["U1"]}})
    respx.get("https://api.upstox.com/v2/order/details", params={"order_id": "U1"}).respond(
        json={"status": "success", "data": {"status": "open", "filled_quantity": 0}})
    async with UpstoxBroker(CREDS, instruments=static_instruments("upstox", {(Exchange.NSE, "INFY"): "NSE_EQ|INE009A01021"})) as broker:
        assert (await broker.place_order(SELL_LIMIT)).broker_order_id == "U1"
        body = sent_json(place)
        assert (body["instrument_token"], body["product"], body["slice"]) == ("NSE_EQ|INE009A01021", "D", False)
        assert (await broker.get_order("U1")).status is OrderStatus.OPEN


@respx.mock
async def test_groww():
    place = respx.post("https://api.groww.in/v1/order/create").respond(
        json={"status": "SUCCESS", "payload": {"groww_order_id": "G1", "order_status": "ACKED"}})
    respx.get("https://api.groww.in/v1/order/detail/G1").respond(
        json={"status": "SUCCESS", "payload": {"order_status": "EXECUTED", "filled_quantity": 3, "average_fill_price": 1500.5}})
    async with GrowwBroker(CREDS) as broker:
        placed = await broker.place_order(SELL_LIMIT)
        assert (placed.broker_order_id, placed.status) == ("G1", OrderStatus.OPEN)
        body = sent_json(place)
        assert (body["trading_symbol"], body["segment"], body["product"], body["order_reference_id"]) == \
            ("INFY", "CASH", "CNC", "kalpi0001")
        assert (await broker.get_order("G1")).status is OrderStatus.COMPLETE


@respx.mock
async def test_groww_throttle_code_is_retryable():
    respx.post("https://api.groww.in/v1/order/create").respond(
        400, json={"status": "FAILURE", "error": {"code": "GA003", "message": "Unable to serve request currently"}})
    async with GrowwBroker(CREDS) as broker:
        with pytest.raises(BrokerRateLimitError):
            await broker.place_order(SELL_LIMIT)


async def test_instrument_master_loads_once_and_reports_missing_symbols():
    loads = 0

    async def loader():
        nonlocal loads
        loads += 1
        return INSTRUMENTS

    master = InstrumentMaster("test", loader)
    assert await master.resolve(Exchange.NSE, "INFY") == "1594"
    with pytest.raises(InstrumentNotFoundError):
        await master.resolve(Exchange.NSE, "NOPE")
    assert loads == 1


@respx.mock
async def test_accepted_order_with_broken_envelope_is_unknown_state():
    # HTTP 200 but no "data": the order may exist and we cannot read its id.
    respx.post("https://api.kite.trade/orders/regular").respond(json={"status": "success"})
    async with ZerodhaBroker(CREDS) as broker:
        with pytest.raises(OrderStateUnknownError):
            await broker.place_order(SELL_LIMIT)


@respx.mock
async def test_malformed_error_body_still_maps_cleanly():
    respx.get("https://api.upstox.com/v2/order/details").respond(400, json={"errors": "not-a-list"})
    async with UpstoxBroker(CREDS) as broker:
        with pytest.raises(BrokerRequestError):
            await broker.get_order("U1")


@pytest.mark.parametrize(("broker", "url", "body"), [
    (ZerodhaBroker, "https://api.kite.trade/orders", {"status": "success", "data": [
        {"order_id": "1", "tag": "other0001", "status": "COMPLETE"},
        {"order_id": "2", "tag": "kalpi0001", "status": "COMPLETE", "filled_quantity": 3}]}),
    (FyersBroker, "https://api-t1.fyers.in/api/v3/orders", {"s": "ok", "code": 200, "message": "", "orderBook": [
        {"id": "2", "orderTag": "2:kalpi0001", "status": 2, "filledQty": 3}]}),
    (AngelOneBroker, "https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/getOrderBook",
     {"status": True, "message": "SUCCESS", "errorcode": "", "data": [
         {"uniqueorderid": "2", "ordertag": "kalpi0001", "orderstatus": "complete", "filledshares": 3}]}),
    (UpstoxBroker, "https://api.upstox.com/v2/order/retrieve-all", {"status": "success", "data": [
        {"order_id": "2", "tag": "kalpi0001", "status": "complete", "filled_quantity": 3}]}),
    (GrowwBroker, "https://api.groww.in/v1/order/status/reference/kalpi0001", {"status": "SUCCESS", "payload": {
        "groww_order_id": "2", "order_status": "EXECUTED", "filled_quantity": 3}}),
])
@respx.mock
async def test_find_order_by_tag(broker, url, body):
    respx.get(url).mock(return_value=respx.MockResponse(200, json=body))
    async with broker(CREDS) as adapter:
        found = await adapter.find_order("kalpi0001")
    assert (found.broker_order_id, found.status, found.filled_quantity) == ("2", OrderStatus.COMPLETE, 3)


@respx.mock
async def test_find_order_returns_none_when_tag_absent():
    respx.get("https://api.kite.trade/orders").mock(return_value=respx.MockResponse(200, json={
        "status": "success", "data": [{"order_id": "1", "tag": "other0001", "status": "OPEN"}]}))
    respx.get("https://api.groww.in/v1/order/status/reference/kalpi0001").mock(return_value=respx.MockResponse(
        404, json={"status": "FAILURE", "error": {"code": "GA004", "message": "Order not found"}}))
    async with ZerodhaBroker(CREDS) as zerodha, GrowwBroker(CREDS) as groww:
        assert await zerodha.find_order("kalpi0001") is None
        assert await groww.find_order("kalpi0001") is None
