"""Notification models: the transactional outbox of reports waiting to be delivered."""
from .outbox import NotificationOutbox

__all__ = ["NotificationOutbox"]
