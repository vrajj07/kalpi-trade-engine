"""Broker endpoints: which brokers exist, the user's connections, and holdings."""
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import UserId
from src.core.database import get_db
from src.integrations.brokers.base import Holding
from src.integrations.brokers.enums import BrokerName
from src.schemas.broker import BrokerConnect, BrokerConnectionStatus, BrokerInfo
from src.service.broker import BrokerService

router = APIRouter()


def get_broker_service(session: AsyncSession = Depends(get_db)) -> BrokerService:
    return BrokerService(session)


@router.get("", response_model=list[BrokerInfo])
async def list_brokers(user_id: UserId, service: BrokerService = Depends(get_broker_service)) -> list[BrokerInfo]:
    return await service.list_brokers(user_id)


@router.put("/{broker}/connection", response_model=BrokerConnectionStatus)
async def connect_broker(broker: BrokerName, body: BrokerConnect, user_id: UserId,
                         service: BrokerService = Depends(get_broker_service)) -> BrokerConnectionStatus:
    """Stores (or replaces) the session from the user's broker login. Tokens expire, most daily:
    reconnect when a request answers 401 BrokerConnectionExpiredError."""
    return BrokerConnectionStatus.model_validate(await service.connect(user_id, broker, body))


@router.get("/{broker}/connection", response_model=BrokerConnectionStatus)
async def get_connection(broker: BrokerName, user_id: UserId,
                         service: BrokerService = Depends(get_broker_service)) -> BrokerConnectionStatus:
    return BrokerConnectionStatus.model_validate(await service.get_connection(user_id, broker))


@router.delete("/{broker}/connection", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_broker(broker: BrokerName, user_id: UserId,
                            service: BrokerService = Depends(get_broker_service)) -> Response:
    await service.disconnect(user_id, broker)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{broker}/holdings", response_model=list[Holding])
async def holdings(broker: BrokerName, user_id: UserId,
                   service: BrokerService = Depends(get_broker_service)) -> list[Holding]:
    return await service.get_holdings(user_id, broker)
