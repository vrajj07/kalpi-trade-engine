from fastapi import APIRouter, Depends

from src.core.auth import authenticate_request

from .brokers import router as brokers_router
from .executions import router as executions_router
from .health import router as health_router

router = APIRouter()
# Authenticated by default: every router but health requires the gateway's user.
authenticated = [Depends(authenticate_request)]

router.include_router(health_router, tags=["health"])
router.include_router(brokers_router, prefix="/brokers", tags=["brokers"], dependencies=authenticated)
router.include_router(executions_router, prefix="/executions", tags=["executions"], dependencies=authenticated)
