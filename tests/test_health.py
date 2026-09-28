from fastapi.testclient import TestClient

from src.core.config import settings
from src.main import app


def test_health() -> None:
    response = TestClient(app).get(f"{settings.api_prefix}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_demo_ui_is_served() -> None:
    response = TestClient(app).get("/ui/")
    assert response.status_code == 200
    assert "Kalpi Trade Engine" in response.text
