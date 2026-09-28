"""Broker endpoints: which brokers exist / are configured, and holdings."""
from fastapi import APIRouter, Depends

from src.integrations.brokers.base import Holding
from src.integrations.brokers.enums import BrokerName
from src.schemas.broker import BrokerInfo
from src.service.broker import BrokerService

router = APIRouter()


@router.get("", response_model=list[BrokerInfo])
async def list_brokers(service: BrokerService = Depends(BrokerService)) -> list[BrokerInfo]:
    return service.list_brokers()


@router.get("/{broker}/holdings", response_model=list[Holding])
async def holdings(broker: BrokerName, service: BrokerService = Depends(BrokerService)) -> list[Holding]:
    return await service.get_holdings(broker)
