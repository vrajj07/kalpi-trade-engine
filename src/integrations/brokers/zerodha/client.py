"""Kite HTTP client: endpoints, auth, error envelope."""
from typing import Any

import httpx

from ..common.client import BaseBrokerClient
from ..errors import BrokerAuthError, BrokerError, BrokerRequestError, BrokerUnavailableError, OrderRejectedError
from .enums import ErrorType, Variety
from .schemas import HoldingResponse, KiteEnvelope, KiteError, OrderHistoryEntry, PlaceOrderRequest, PlaceOrderResponse


class Routes:
    PLACE_ORDER = f"/orders/{Variety.REGULAR}"
    ORDER_HISTORY = "/orders/{order_id}"
    HOLDINGS = "/portfolio/holdings"


class ZerodhaClient(BaseBrokerClient):
    broker = "zerodha"
    base_url = "https://api.kite.trade"
    rate_limit = (10, 1.0)  # order placement: 10/s (also 400/min, 5000/day)

    def headers(self) -> dict[str, str]:
        token = self.credentials.access_token.get_secret_value()
        return {"X-Kite-Version": "3", "Authorization": f"token {self.api_key}:{token}"}

    async def place_order(self, payload: PlaceOrderRequest) -> PlaceOrderResponse:
        # Kite takes form-encoded bodies, not JSON.
        body = await self.request("POST", Routes.PLACE_ORDER, data=payload.model_dump(mode="json", exclude_none=True))
        return self.parse(KiteEnvelope[PlaceOrderResponse], body, after_write=True).data

    async def order_history(self, order_id: str) -> list[OrderHistoryEntry]:
        body = await self.request("GET", Routes.ORDER_HISTORY.format(order_id=order_id))
        return self.parse(KiteEnvelope[list[OrderHistoryEntry]], body).data  # oldest first

    async def holdings(self) -> list[HoldingResponse]:
        body = await self.request("GET", Routes.HOLDINGS)
        return self.parse(KiteEnvelope[list[HoldingResponse]], body).data

    def error_from_body(self, response: httpx.Response, body: Any) -> BrokerError | None:
        if (error := self.try_parse(KiteError, body)) is None:
            return None
        message, error_type = error.message, error.error_type
        if error_type in (ErrorType.TOKEN, ErrorType.PERMISSION):
            return BrokerAuthError(message, broker=self.broker, code=error_type)
        if error_type in (ErrorType.ORDER, ErrorType.INPUT):
            return OrderRejectedError(message, broker=self.broker, code=error_type)
        if error_type == ErrorType.NETWORK and response.status_code == 503:
            return BrokerUnavailableError(message, broker=self.broker, code=error_type)
        if response.status_code < 500:
            return BrokerRequestError(message, broker=self.broker, code=error_type)
        return None  # 5xx: let the base decide (unknown state for POST)
