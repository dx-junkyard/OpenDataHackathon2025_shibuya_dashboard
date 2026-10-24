import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("APP_DATASETS_DIR", str(tmp_path / "datasets"))
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    from app.seed import seed

    seed()
    from app.main import app

    with TestClient(app) as c:
        yield c


def as_user(uid: int) -> dict:
    return {"X-User-Id": str(uid)}
