"""Reset (runs last: it clears what the other tests built)."""
from .test_api import borrower_id


def test_reset_one_client(client, h):
    bid = borrower_id(client, h, "Meridian Renewables Limited")
    assert client.post(f"/api/borrowers/{bid}/assess", json={}, headers=h).status_code == 200
    other = borrower_id(client, h, "HarbourVest")
    client.post(f"/api/borrowers/{other}/assess", json={}, headers=h)
    out = client.post(f"/api/borrowers/{bid}/reset", headers=h).json()
    assert out["runs"] >= 1
    rows = {b["id"]: b for b in client.get("/api/borrowers", headers=h).json()}
    assert rows[bid]["confidence"] is None and all(v is None for v in rows[bid]["steps"].values())
    assert rows[other]["confidence"] is not None                     # other clients untouched
    assert client.get(f"/api/borrowers/{bid}/overview", headers=h).json()["gates"]["p1"] is False


def test_viewer_cannot_reset(client, h):
    t = client.post("/api/auth/login", data={"username": "ai-viewer@example.com", "password": "viewer12345"}).json()["access_token"]
    assert client.post("/api/reset", json={}, headers={"Authorization": f"Bearer {t}"}).status_code == 403


def test_reset_everything(client, h):
    out = client.post("/api/reset", json={}, headers=h).json()
    rows = client.get("/api/borrowers", headers=h).json()
    assert rows and all(b["confidence"] is None for b in rows)          # files kept, results gone
    out = client.post("/api/reset", json={"uploads": True, "settings": True}, headers=h).json()
    assert out["uploads"] >= 1
    assert client.get("/api/borrowers", headers=h).json() == [] and client.get("/api/uploads", headers=h).json() == []
    assert any(e["action"] == "reset.all" for e in client.get("/api/audit", headers=h).json())
