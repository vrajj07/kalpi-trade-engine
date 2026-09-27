from fastapi import APIRouter

from .brokers import router as brokers_router
from .executions import router as executions_router
from .health import router as health_router

router = APIRouter()

router.include_router(health_router, tags=["health"])
router.include_router(brokers_router, prefix="/brokers", tags=["brokers"])
router.include_router(executions_router, prefix="/executions", tags=["executions"])
