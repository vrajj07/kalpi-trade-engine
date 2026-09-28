"""Fyers HTTP client: endpoints, auth, error envelope."""
from typing import Any

import httpx

from ..common.client import BaseBrokerClient
from ..errors import BrokerAuthError, BrokerError, BrokerRequestError, OrderRejectedError
from .enums import AUTH_ERRORS
from .schemas import FyersStatus, HoldingsResponse, OrderBookResponse, OrderResponse, PlaceOrderRequest, PlaceOrderResponse


class Routes:
    PLACE_ORDER = "/orders/sync"
    ORDER_BOOK = "/orders"
    HOLDINGS = "/holdings"


class FyersClient(BaseBrokerClient):
    broker = "fyers"
    base_url = "https://api-t1.fyers.in/api/v3"
    rate_limit = (10, 1.0)  # 10/s, 200/min

    def headers(self) -> dict[str, str]:
        # "<app_id>:<access_token>" — no "Bearer" prefix.
        token = self.credentials.access_token.get_secret_value()
        return {"Authorization": f"{self.api_key}:{token}", "version": "3"}

    async def place_order(self, payload: PlaceOrderRequest) -> PlaceOrderResponse:
        body = await self.request("POST", Routes.PLACE_ORDER, json=payload.model_dump(mode="json", exclude_none=True))
        return self.parse(PlaceOrderResponse, body, after_write=True)

    async def get_order(self, order_id: str) -> OrderResponse:
        body = await self.request("GET", Routes.ORDER_BOOK, params={"id": order_id})
        matches = [o for o in self.parse(OrderBookResponse, body).orderBook if o.id == order_id]
        if not matches:
            raise BrokerRequestError(f"Order {order_id} not found", broker=self.broker)
        return matches[0]

    async def holdings(self) -> HoldingsResponse:
        return self.parse(HoldingsResponse, await self.request("GET", Routes.HOLDINGS))

    def check_body(self, response: httpx.Response, body: Any) -> None:
        # Fyers can report failure inside an HTTP 200 as {"s": "error", "code": -N, ...}.
        status = self.try_parse(FyersStatus, body)
        if status is not None and not status.ok:
            raise self.error_from_body(response, body) or BrokerRequestError(status.message, broker=self.broker)

    def error_from_body(self, response: httpx.Response, body: Any) -> BrokerError | None:
        status = self.try_parse(FyersStatus, body)
        if status is None or status.code is None:
            return None
        code, message = status.code, status.message
        if code in AUTH_ERRORS:
            return BrokerAuthError(message, broker=self.broker, code=str(code))
        if response.status_code < 500 and response.request.method == "POST":
            return OrderRejectedError(message, broker=self.broker, code=str(code))
        return None
