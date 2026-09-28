"""DAO for the notification outbox."""
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import NotificationOutbox
from src.models.notification.enums import NotificationStatus
from src.utils.database import DatabaseService


class NotificationDAO:
    def __init__(self, db: AsyncSession, auto_commit: bool = True) -> None:
        self.db_service = DatabaseService(db=db, auto_commit=auto_commit)

    async def claim_due(self, now: datetime, limit: int, lease_until: datetime) -> list[NotificationOutbox]:
        """Claims up to `limit` due rows and commits the claim before anything is delivered, so no
        transaction (or row lock) is held across a slow HTTP call. The claim is a lease: each row is
        pushed out to `lease_until`, and counts one attempt, so a relay that dies mid-delivery leaves
        it to be retried once the lease runs out."""
        rows = await self.db_service.filter(
            NotificationOutbox, status=NotificationStatus.PENDING,
            conditions=[NotificationOutbox.next_attempt_at <= now],
            order_by=NotificationOutbox.next_attempt_at, limit=limit, skip_locked=True,
        )
        for row in rows:
            row.attempts += 1
            row.next_attempt_at = lease_until
        # Commit even when nothing was claimed, to end the read transaction: a rollback would
        # expire every object in the session, and an expired object cannot lazy-load under asyncio.
        await self.db_service.commit()
        return rows

    async def list_for_execution(self, execution_id: uuid.UUID) -> list[NotificationOutbox]:
        return await self.db_service.filter(NotificationOutbox, execution_id=execution_id)

    async def save(self) -> None:
        await self.db_service.commit()
