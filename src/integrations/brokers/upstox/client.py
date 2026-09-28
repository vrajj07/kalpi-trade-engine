"""Upstox HTTP client: endpoints (two hosts), auth, error envelope."""
from typing import Any

import httpx

from ..common.client import BaseBrokerClient
from ..errors import BrokerAuthError, BrokerError, BrokerRequestError, OrderRejectedError
from .enums import AUTH_ERRORS
from .schemas import HoldingResponse, OrderDetailsResponse, PlaceOrderRequest, PlaceOrderResponse, UpstoxEnvelope, UpstoxError


class Routes:
    # Order writes go to the HFT host; reads stay on the main API host (base_url).
    PLACE_ORDER = "https://api-hft.upstox.com/v3/order/place"
    ORDER_DETAILS = "/v2/order/details"
    HOLDINGS = "/v2/portfolio/long-term-holdings"


class UpstoxClient(BaseBrokerClient):
    broker = "upstox"
    base_url = "https://api.upstox.com"
    rate_limit = (10, 1.0)  # order APIs: 10/s, 500/min, 2000/30min

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.credentials.access_token.get_secret_value()}",
            "Accept": "application/json",
        }

    async def place_order(self, payload: PlaceOrderRequest) -> PlaceOrderResponse:
        body = await self.request("POST", Routes.PLACE_ORDER, json=payload.model_dump(mode="json", exclude_none=True))
        return self.parse(UpstoxEnvelope[PlaceOrderResponse], body, after_write=True).data

    async def order_details(self, order_id: str) -> OrderDetailsResponse:
        body = await self.request("GET", Routes.ORDER_DETAILS, params={"order_id": order_id})
        return self.parse(UpstoxEnvelope[OrderDetailsResponse], body).data

    async def holdings(self) -> list[HoldingResponse]:
        body = await self.request("GET", Routes.HOLDINGS)
        return self.parse(UpstoxEnvelope[list[HoldingResponse] | None], body).data or []

    def error_from_body(self, response: httpx.Response, body: Any) -> BrokerError | None:
        if (error := self.try_parse(UpstoxError, body)) is None:
            return None
        code, message = error.first.errorCode, error.first.message
        if code in AUTH_ERRORS:
            return BrokerAuthError(message, broker=self.broker, code=code)
        if response.status_code >= 500:
            return None
        if response.request.method == "POST":
            return OrderRejectedError(message, broker=self.broker, code=code)
        return BrokerRequestError(message, broker=self.broker, code=code)
