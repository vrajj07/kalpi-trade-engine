"""Groww HTTP client: endpoints, auth, error envelope."""
import uuid
from typing import Any

import httpx

from ..common.client import BaseBrokerClient
from ..errors import BrokerAuthError, BrokerError, BrokerRateLimitError, BrokerRequestError, OrderRejectedError
from .enums import ErrorCode, Segment
from .schemas import GrowwEnvelope, GrowwError, HoldingsResponse, OrderDetailsResponse, PlaceOrderRequest, PlaceOrderResponse


class Routes:
    PLACE_ORDER = "/order/create"
    ORDER_DETAILS = "/order/detail/{order_id}"
    HOLDINGS = "/holdings/user"


class GrowwClient(BaseBrokerClient):
    broker = "groww"
    base_url = "https://api.groww.in/v1"
    rate_limit = (10, 1.0)  # orders: 10/s, 250/min

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.credentials.access_token.get_secret_value()}",
            "Accept": "application/json",
            "x-api-version": "1.0",
            "x-request-id": str(uuid.uuid4()),
        }

    async def place_order(self, payload: PlaceOrderRequest) -> PlaceOrderResponse:
        body = await self.request("POST", Routes.PLACE_ORDER, json=payload.model_dump(mode="json", exclude_none=True))
        return self.parse(GrowwEnvelope[PlaceOrderResponse], body, after_write=True).payload

    async def order_details(self, order_id: str) -> OrderDetailsResponse:
        body = await self.request("GET", Routes.ORDER_DETAILS.format(order_id=order_id), params={"segment": Segment.CASH.value})
        return self.parse(GrowwEnvelope[OrderDetailsResponse], body).payload

    async def holdings(self) -> HoldingsResponse:
        body = await self.request("GET", Routes.HOLDINGS)
        return self.parse(GrowwEnvelope[HoldingsResponse | None], body).payload or HoldingsResponse()

    def check_body(self, response: httpx.Response, body: Any) -> None:
        error = self.try_parse(GrowwError, body)
        if error is not None and error.status == "FAILURE":
            raise self.error_from_body(response, body) or BrokerRequestError(error.error.message, broker=self.broker)

    def error_from_body(self, response: httpx.Response, body: Any) -> BrokerError | None:
        if (error := self.try_parse(GrowwError, body)) is None:
            return None
        code, message = error.error.code, error.error.message
        if code == ErrorCode.UNAUTHORISED:
            return BrokerAuthError(message, broker=self.broker, code=code)
        if code == ErrorCode.THROTTLED:
            return BrokerRateLimitError(message, broker=self.broker, code=code)
        if response.status_code >= 500:
            return None
        if response.request.method == "POST":
            return OrderRejectedError(message, broker=self.broker, code=code)
        return BrokerRequestError(message, broker=self.broker, code=code)
