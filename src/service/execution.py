"""Execution use cases: submit (idempotent), fetch, audit trail.

Idempotency: the client sends an Idempotency-Key per intent. The same key with the same body
returns the existing execution (resuming it if a crash interrupted it); the same key with a
different body is a conflict. A new key is a new execution, even for an identical body.
"""
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.dao.execution import ExecutionDAO
from src.models import Execution, ExecutionEvent
from src.modules.execution import ExecutionModule
from src.modules.execution.exceptions import ExecutionModuleError, ExecutionNotFoundError
from src.modules.execution.validators import ExecutionValidator
from src.schemas.execution import ExecutionCreate
from src.utils.exceptions import InternalServerError

logger = logging.getLogger(__name__)


class ExecutionService:
    def __init__(self, db: AsyncSession) -> None:
        self.dao = ExecutionDAO(db)
        self.validator = ExecutionValidator()
        self.execution_module = ExecutionModule(db)

    async def submit(self, idempotency_key: str, request: ExecutionCreate) -> tuple[Execution, bool]:
        """Returns (execution, replayed)."""
        try:
            fingerprint = self.execution_module.fingerprint(request)
            execution = await self.dao.get_by_idempotency_key(idempotency_key)
            created = False
            if execution is None:
                self.validator.validate(request)
                execution, created = await self.execution_module.create(idempotency_key, request, fingerprint)
            self.validator.validate_replay(execution, fingerprint)
            await self.execution_module.start(execution)  # new, or resume one a restart interrupted
            return execution, not created
        except ExecutionModuleError as exc:
            await self.dao.rollback()
            logger.warning("Execution submission refused: %s", exc.message)
            raise ExecutionModuleError.to_http_exception(exc) from exc
        except Exception as exc:
            await self.dao.rollback()
            logger.exception("Unexpected error submitting execution")
            raise InternalServerError("An unexpected error occurred while submitting the execution") from exc

    async def get(self, execution_id: uuid.UUID) -> Execution:
        try:
            if (execution := await self.dao.get_by_id(execution_id)) is None:
                raise ExecutionNotFoundError(execution_id)
            return execution
        except ExecutionModuleError as exc:
            raise ExecutionModuleError.to_http_exception(exc) from exc

    async def list_events(self, execution_id: uuid.UUID) -> list[ExecutionEvent]:
        try:
            if await self.dao.get_by_id(execution_id) is None:  # 404, not an empty history
                raise ExecutionNotFoundError(execution_id)
            return await self.dao.list_events(execution_id)
        except ExecutionModuleError as exc:
            raise ExecutionModuleError.to_http_exception(exc) from exc
