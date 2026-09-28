"""Fyers API v3.

Reference: the official `fyers-apiv3` SDK 3.1.18 (base URL, routes, auth header, order
fields and codes). Order status codes and auth error codes come from the Fyers v3 docs;
they are not encoded in the SDK (see mappers.STATUS and client.AUTH_CODES).
"""
from .adapter import FyersBroker

__all__ = ["FyersBroker"]
