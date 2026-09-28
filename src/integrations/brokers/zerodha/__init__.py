"""Zerodha Kite Connect v3.

Reference: kite.trade/docs/connect/v3 and the official `kiteconnect` SDK 5.2.2
(routes, headers, error envelope).
"""
from .adapter import ZerodhaBroker

__all__ = ["ZerodhaBroker"]
