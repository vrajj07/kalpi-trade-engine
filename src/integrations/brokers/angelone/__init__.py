"""Angel One SmartAPI.

Reference: the official `smartapi-python` SDK 1.5.5 (base URL, routes, headers, order
fields, error envelope). Orders need a numeric `symboltoken`, resolved from Angel's
public scrip master (see common/instruments.py).
"""
from .adapter import AngelOneBroker

__all__ = ["AngelOneBroker"]
