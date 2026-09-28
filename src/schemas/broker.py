from pydantic import BaseModel

from src.integrations.brokers.enums import BrokerName


class BrokerInfo(BaseModel):
    name: BrokerName
    configured: bool
