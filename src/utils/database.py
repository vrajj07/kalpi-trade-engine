"""Generic database operations shared by every DAO.

DAOs describe *what* they need (a row by key, rows matching filters); this module owns *how*
it is queried and when the transaction commits, so query idioms live in one place.
"""
from collections.abc import Sequence
from typing import Any, TypeVar

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm.interfaces import ORMOption

T = TypeVar("T", bound=DeclarativeBase)


class DatabaseService:
    def __init__(self, db: AsyncSession, auto_commit: bool = True) -> None:
        """auto_commit: commit after each write; otherwise flush and let the caller commit."""
        self.db = db
        self.auto_commit = auto_commit

    async def get_by_id(self, model: type[T], record_id: Any, options: Sequence[ORMOption] = ()) -> T | None:
        return await self.db.get(model, record_id, options=options)

    async def get_by_field(self, model: type[T], field_name: str, value: Any,
                           options: Sequence[ORMOption] = ()) -> T | None:
        """One row by a unique field; raises MultipleResultsFound if the field is not unique."""
        stmt = select(model).where(self._column(model, field_name) == value).options(*options)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def filter(self, model: type[T], *, order_by: Any = None, limit: int | None = None,
                     options: Sequence[ORMOption] = (), conditions: Sequence[ColumnElement[bool]] = (),
                     skip_locked: bool = False, **filters: Any) -> list[T]:
        """Rows matching every filter: a list/tuple/set value means IN, anything else equality.

        conditions: extra expressions the keyword filters cannot say (e.g. a range).
        skip_locked: lock the rows for this transaction, skipping rows another transaction has
        locked (FOR UPDATE SKIP LOCKED), so concurrent workers claim disjoint rows. SQLite has no
        row locks and ignores it.
        """
        stmt = select(model).options(*options).where(*conditions)
        if skip_locked:
            stmt = stmt.with_for_update(skip_locked=True)
        for field_name, value in filters.items():
            column = self._column(model, field_name)
            stmt = stmt.where(column.in_(value) if isinstance(value, list | tuple | set) else column == value)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list((await self.db.scalars(stmt)).all())

    async def create(self, model: type[T], **fields: Any) -> T:
        return await self.add(model(**fields))

    async def add(self, instance: T) -> T:
        """Persist a built instance, including related objects attached to it (cascade)."""
        self.db.add(instance)
        await self._write()
        return instance

    async def delete(self, instance: T) -> None:
        await self.db.delete(instance)
        await self._write()

    async def refresh(self, instance: T) -> T:
        """Reload server-generated values (e.g. an onupdate timestamp) that a write expired."""
        await self.db.refresh(instance)
        return instance

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()

    async def _write(self) -> None:
        if self.auto_commit:
            await self.db.commit()
        else:
            await self.db.flush()

    @staticmethod
    def _column(model: type[T], field_name: str) -> Any:
        column = getattr(model, field_name, None)
        if column is None:
            raise ValueError(f"Field '{field_name}' does not exist on {model.__name__}")
        return column
