from fastapi.testclient import TestClient

from src.core.config import settings
from src.main import app


def test_health() -> None:
    response = TestClient(app).get(f"{settings.api_prefix}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
