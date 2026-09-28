"""In-memory broker for demos and tests (no wire protocol, so no client/builder/schemas)."""
from .adapter import MockBroker

__all__ = ["MockBroker"]
