"""Upstox: v3 order placement, v2 order details and holdings.

Reference: the official `upstox-python-sdk` 2.30.0 (hosts, routes, request/response models).
Orders need an ISIN-based `instrument_key` (e.g. NSE_EQ|INE009A01021), resolved from
Upstox's public instrument master (see common/instruments.py).
"""
from .adapter import UpstoxBroker

__all__ = ["UpstoxBroker"]
