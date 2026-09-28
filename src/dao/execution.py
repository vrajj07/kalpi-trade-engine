"""DAO for executions and their orders."""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Execution, ExecutionEvent
from src.utils.database import DatabaseService


class ExecutionDAO:
    def __init__(self, db: AsyncSession, auto_commit: bool = True) -> None:
        self.db_service = DatabaseService(db=db, auto_commit=auto_commit)

    async def get_by_id(self, execution_id: uuid.UUID) -> Execution | None:
        return await self.db_service.get_by_id(Execution, execution_id)

    async def get_by_idempotency_key(self, key: str) -> Execution | None:
        return await self.db_service.get_by_field(Execution, "idempotency_key", key)

    async def list_events(self, execution_id: uuid.UUID) -> list[ExecutionEvent]:
        return await self.db_service.filter(ExecutionEvent, execution_id=execution_id, order_by=ExecutionEvent.id)

    async def create(self, execution: Execution) -> Execution:
        """Inserts the execution with its planned orders in one transaction."""
        return await self.db_service.add(execution)

    async def save(self) -> None:
        """Commit changes made to loaded executions (the executor mutates rows in place)."""
        await self.db_service.commit()

    async def rollback(self) -> None:
        await self.db_service.rollback()
