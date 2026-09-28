"""Symbol -> broker instrument id, for brokers that don't accept plain trading symbols.

AngelOne needs a numeric `symboltoken`, Upstox an ISIN-based `instrument_key`. Both
publish a public instrument master file; it is downloaded once per process on first use.

Known limitation: the index is never refreshed, so symbols listed after startup are not
found until restart. Production would reload it daily (masters are regenerated each day).
"""
import asyncio
import gzip
import json
from collections.abc import Awaitable, Callable

import httpx

from ..enums import Exchange
from ..errors import BrokerUnavailableError, InstrumentNotFoundError

InstrumentIndex = dict[tuple[Exchange, str], str]


class InstrumentMaster:
    def __init__(self, broker: str, loader: Callable[[], Awaitable[InstrumentIndex]]) -> None:
        self._broker = broker
        self._loader = loader
        self._index: InstrumentIndex | None = None
        self._lock = asyncio.Lock()

    async def resolve(self, exchange: Exchange, symbol: str) -> str:
        if self._index is None:
            async with self._lock:  # one download even if many orders arrive at once
                if self._index is None:
                    self._index = await self._load()
        try:
            return self._index[(exchange, symbol)]
        except KeyError:
            raise InstrumentNotFoundError(
                f"{exchange}:{symbol} not found in {self._broker} instrument master", broker=self._broker
            ) from None

    async def _load(self) -> InstrumentIndex:
        try:
            return await self._loader()
        except (httpx.HTTPError, ValueError) as exc:
            raise BrokerUnavailableError(
                f"Could not load {self._broker} instrument master: {exc}", broker=self._broker
            ) from exc


def static_instruments(broker: str, index: InstrumentIndex) -> InstrumentMaster:
    """Fixed index, for tests or a pre-seeded deployment."""

    async def loader() -> InstrumentIndex:
        return index

    return InstrumentMaster(broker, loader)


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


async def load_angelone_index() -> InstrumentIndex:
    rows = json.loads(await _download(
        "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    ))
    index: InstrumentIndex = {}
    for row in rows:
        # NSE equities are listed as "INFY-EQ"; BSE equities as plain "INFY".
        if row["exch_seg"] == "NSE" and row["symbol"] == f"{row['name']}-EQ":
            index[(Exchange.NSE, row["name"])] = row["token"]
        elif row["exch_seg"] == "BSE" and row["symbol"] == row["name"] and not row["instrumenttype"]:
            index[(Exchange.BSE, row["name"])] = row["token"]
    return index


async def load_upstox_index() -> InstrumentIndex:
    index: InstrumentIndex = {}
    for exchange in (Exchange.NSE, Exchange.BSE):
        raw = await _download(f"https://assets.upstox.com/market-quote/instruments/exchange/{exchange}.json.gz")
        for row in json.loads(gzip.decompress(raw)):
            if row.get("segment") == f"{exchange}_EQ":
                index[(exchange, row["trading_symbol"])] = row["instrument_key"]
    return index
