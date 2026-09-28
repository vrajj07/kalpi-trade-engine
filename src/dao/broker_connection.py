"""DAO for users' broker connections."""
from sqlalchemy.ext.asyncio import AsyncSession

from src.integrations.brokers.enums import BrokerName
from src.models import BrokerConnection
from src.utils.database import DatabaseService


class BrokerConnectionDAO:
    def __init__(self, db: AsyncSession, auto_commit: bool = True) -> None:
        self.db_service = DatabaseService(db=db, auto_commit=auto_commit)

    async def get(self, user_id: str, broker: BrokerName) -> BrokerConnection | None:
        rows = await self.db_service.filter(BrokerConnection, user_id=user_id, broker=broker, limit=1)
        return rows[0] if rows else None

    async def list_for_user(self, user_id: str) -> list[BrokerConnection]:
        return await self.db_service.filter(BrokerConnection, user_id=user_id)

    async def create(self, connection: BrokerConnection) -> BrokerConnection:
        return await self.db_service.add(connection)

    async def delete(self, connection: BrokerConnection) -> None:
        await self.db_service.delete(connection)

    async def save(self) -> None:
        await self.db_service.commit()

    async def refresh(self, connection: BrokerConnection) -> BrokerConnection:
        return await self.db_service.refresh(connection)
