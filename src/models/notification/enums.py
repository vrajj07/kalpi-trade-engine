from enum import StrEnum


class NotificationEvent(StrEnum):
    EXECUTION_FINISHED = "execution.finished"


class NotificationStatus(StrEnum):
    PENDING = "PENDING"  # waiting for its first or next attempt
    SENT = "SENT"
    FAILED = "FAILED"    # terminal response or attempts exhausted (the dead-letter state)
