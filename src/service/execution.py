"""Execution use cases: submit (idempotent), fetch, audit trail.

Idempotency: the client sends an Idempotency-Key per intent. The same key with the same body
returns the existing execution (resuming it if a crash interrupted it); the same key with a
different body is a conflict. A new key is a new execution, even for an identical body.
"""
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.dao.execution import ExecutionDAO
from src.integrations.brokers.errors import BrokerAuthError, BrokerError
from src.integrations.brokers.registry import get_adapter
from src.modules.broker import BrokerModule
from src.modules.broker.exceptions import BrokerConnectionExpiredError, BrokerModuleError
from src.models import Execution, ExecutionEvent
from src.modules.execution import ExecutionModule
from src.modules.execution.exceptions import (
    ExecutionModuleError,
    ExecutionNotFoundError,
    HoldingsUnavailableError,
)
from src.modules.execution.validators import ExecutionValidator
from src.schemas.execution import ExecutionCreate
from src.utils.exceptions import InternalServerError

logger = logging.getLogger(__name__)


class ExecutionService:
    def __init__(self, db: AsyncSession) -> None:
        self.dao = ExecutionDAO(db)
        self.validator = ExecutionValidator()
        self.execution_module = ExecutionModule(db)
        self.broker_module = BrokerModule(db)

    async def submit(self, user_id: str, idempotency_key: str, request: ExecutionCreate) -> tuple[Execution, bool]:
        """Returns (execution, replayed)."""
        try:
            fingerprint = self.execution_module.fingerprint(request)
            execution = await self.dao.get_by_idempotency_key(user_id, idempotency_key)
            created = False
            if execution is None:
                # A replay is not re-checked against holdings: its own fills have changed them.
                self.validator.validate(request)
                credentials = await self.broker_module.credentials(user_id, request.broker)
                try:
                    async with get_adapter(request.broker, credentials) as adapter:
                        holdings = await adapter.get_holdings()
                except BrokerAuthError as exc:
                    await self.broker_module.mark_expired(user_id, request.broker)
                    raise BrokerConnectionExpiredError(request.broker) from exc
                except BrokerError as exc:  # fail closed: an unchecked request is not placed
                    raise HoldingsUnavailableError(request.broker, exc.message) from exc
                self.validator.validate_against_holdings(request, holdings)
                execution, created = await self.execution_module.create(user_id, idempotency_key, request,
                                                                        fingerprint)
            self.validator.validate_replay(execution, fingerprint)
            await self.execution_module.start(execution)  # new, or resume one a restart interrupted
            return execution, not created
        except ExecutionModuleError as exc:
            await self.dao.rollback()
            logger.warning("Execution submission refused: %s", exc.message)
            raise ExecutionModuleError.to_http_exception(exc) from exc
        except BrokerModuleError as exc:
            await self.dao.rollback()
            logger.warning("Execution submission refused: %s", exc.message)
            raise BrokerModuleError.to_http_exception(exc) from exc
        except Exception as exc:
            await self.dao.rollback()
            logger.exception("Unexpected error submitting execution")
            raise InternalServerError("An unexpected error occurred while submitting the execution") from exc

    async def get(self, user_id: str, execution_id: uuid.UUID) -> Execution:
        try:
            execution = await self.dao.get_by_id(execution_id)
            # Another user's execution is "not found", not "forbidden": no existence oracle.
            if execution is None or execution.user_id != user_id:
                raise ExecutionNotFoundError(execution_id)
            return execution
        except ExecutionModuleError as exc:
            raise ExecutionModuleError.to_http_exception(exc) from exc

    async def list_events(self, user_id: str, execution_id: uuid.UUID) -> list[ExecutionEvent]:
        await self.get(user_id, execution_id)  # 404 for an unknown (or another user's) execution
        return await self.dao.list_events(execution_id)
