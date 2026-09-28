"""SmartAPI HTTP client: endpoints, auth headers, error envelope."""
from typing import Any

import httpx

from ..common.client import BaseBrokerClient
from ..errors import BrokerAuthError, BrokerError, BrokerRequestError, OrderRejectedError
from .enums import AUTH_ERROR_PREFIX, TOKEN_EXCEPTION
from .schemas import AngelEnvelope, AngelError, HoldingResponse, OrderBookEntry, OrderDetailsResponse, PlaceOrderRequest, PlaceOrderResponse


class Routes:
    _PREFIX = "/rest/secure/angelbroking"
    PLACE_ORDER = f"{_PREFIX}/order/v1/placeOrder"
    ORDER_DETAILS = f"{_PREFIX}/order/v1/details/{{unique_order_id}}"
    ORDER_BOOK = f"{_PREFIX}/order/v1/getOrderBook"
    HOLDINGS = f"{_PREFIX}/portfolio/v1/getHolding"


class AngelOneClient(BaseBrokerClient):
    broker = "angelone"
    base_url = "https://apiconnect.angelone.in"
    rate_limit = (10, 1.0)  # UNVERIFIED: Angel publishes per-endpoint limits; 10/s is conservative

    def headers(self) -> dict[str, str]:
        extra = self.credentials.extra
        return {
            "Authorization": f"Bearer {self.credentials.access_token.get_secret_value()}",
            "X-PrivateKey": self.api_key,
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            # Angel requires these on every call; values identify the calling machine.
            "X-ClientLocalIP": extra.get("client_local_ip", "127.0.0.1"),
            "X-ClientPublicIP": extra.get("client_public_ip", "127.0.0.1"),
            "X-MACAddress": extra.get("mac_address", "00:00:00:00:00:00"),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def place_order(self, payload: PlaceOrderRequest) -> PlaceOrderResponse:
        body = await self.request("POST", Routes.PLACE_ORDER, json=payload.model_dump(mode="json", exclude_none=True))
        return self.parse(AngelEnvelope[PlaceOrderResponse], body, after_write=True).data

    async def order_details(self, unique_order_id: str) -> OrderDetailsResponse:
        body = await self.request("GET", Routes.ORDER_DETAILS.format(unique_order_id=unique_order_id))
        return self.parse(AngelEnvelope[OrderDetailsResponse], body).data

    async def order_book(self) -> list[OrderBookEntry]:
        body = await self.request("GET", Routes.ORDER_BOOK)
        return self.parse(AngelEnvelope[list[OrderBookEntry] | None], body).data or []

    async def holdings(self) -> list[HoldingResponse]:
        body = await self.request("GET", Routes.HOLDINGS)
        return self.parse(AngelEnvelope[list[HoldingResponse] | None], body).data or []

    def check_body(self, response: httpx.Response, body: Any) -> None:
        # Angel reports most failures as HTTP 200 with {"status": false, "errorcode": "AB...."}.
        error = self.try_parse(AngelError, body)
        if error is not None and error.failed:
            raise self.error_from_body(response, body) or BrokerRequestError(error.message, broker=self.broker)

    def error_from_body(self, response: httpx.Response, body: Any) -> BrokerError | None:
        if (error := self.try_parse(AngelError, body)) is None:
            return None
        code, message = error.code, error.message
        if code.startswith(AUTH_ERROR_PREFIX) or code == TOKEN_EXCEPTION:
            return BrokerAuthError(message, broker=self.broker, code=code)
        if code and response.status_code < 500 and response.request.method == "POST":
            return OrderRejectedError(message, broker=self.broker, code=code)
        if code and response.status_code < 500:
            return BrokerRequestError(message, broker=self.broker, code=code)
        return None
