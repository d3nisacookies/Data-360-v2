import os
import tempfile
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://data360:data360@localhost:5432/data360_test")
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="d360-")
os.environ["REFERENCE_DATE"] = "2026-10-09"
os.environ["JWT_SECRET"] = "test-secret-that-is-at-least-32-bytes-long"
os.environ["ADMIN_EMAIL"] = "admin@example.com"
os.environ["ADMIN_PASSWORD"] = "admin12345"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

SAMPLES = Path(__file__).resolve().parents[2] / "seed" / "sample-files"


@pytest.fixture(scope="session")
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def token(client):
    r = client.post("/api/auth/login", data={"username": "admin@example.com", "password": "admin12345"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def h(token):
    return {"Authorization": f"Bearer {token}"}


def upload(client, h, *paths, **form):
    files = [("files", (p.name, p.read_bytes())) for p in paths]
    r = client.post("/api/uploads", files=files, data={k: str(v) for k, v in form.items()}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()
