"""Groww Trade API.

Reference: the official `growwapi` SDK 1.5.0 (base URL, routes, headers, order fields,
FAILURE envelope, status enum from its protobuf definitions). Field names of the order
detail payload follow the REST docs; the SDK passes that payload through untyped.
"""
from .adapter import GrowwBroker

__all__ = ["GrowwBroker"]
