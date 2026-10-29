"""Folder scan: build the planted test folder, scan it through the API, score it against the answer key."""
import importlib.util
import json
from pathlib import Path

from app.config import get_settings

SEED = Path(__file__).resolve().parents[2] / "seed"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SEED / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_scan_finds_what_was_planted(client, h, tmp_path, monkeypatch):
    make, scorer = _load("make_scan_test"), _load("score_scan")
    folder, key_path = tmp_path / "scan-test", tmp_path / "scan-test-answer-key.json"
    key = make.build(folder, key_path)
    assert not (folder / key_path.name).exists()                    # the answer key stays outside the folder

    monkeypatch.setattr(get_settings(), "scan_root", str(tmp_path / "missing"))
    assert client.get("/api/scan", headers=h).json()["available"] is False
    assert client.post("/api/scan", headers=h).status_code == 409

    monkeypatch.setattr(get_settings(), "scan_root", str(folder))
    st = client.get("/api/scan", headers=h).json()
    assert st["available"] is True and st["last"] is None or st["last"]

    rep = client.post("/api/scan", headers=h)
    assert rep.status_code == 200, rep.text
    rep = rep.json()
    s = scorer.score(key, rep)
    failed = [(r["path"], r["expect"], r["got"], r["note"]) for r in s["rows"] if not r["ok"]]
    assert not failed, json.dumps(failed, indent=1)
    assert s["passed"], s
    assert "Kestrel Shipping Pte. Ltd." in rep["borrowers"]
    # the report is kept for the screen and the scorecard; loaded files remember where they were found
    assert client.get("/api/scan", headers=h).json()["last"]["found"] == rep["found"]
    ups = client.get("/api/uploads", headers=h).json()
    assert any(u["source_path"] and u["source_path"].endswith("Kestrel Shipping - lender export.csv") for u in ups)
    # nothing half-mapped is left behind by the scan
    assert not [u for u in ups if u["source_path"] and u["status"] != "ingested"]

    # a second scan finds the same files and loads nothing new
    again = client.post("/api/scan", headers=h).json()
    assert again["counts"]["loaded"] == 0 and again["counts"]["duplicate"] == rep["counts"]["loaded"] + rep["counts"]["duplicate"]


def test_viewer_cannot_scan(client, h):
    client.post("/api/users", json={"email": "scan-viewer@example.com", "password": "viewer12345", "role": "viewer"}, headers=h)
    t = client.post("/api/auth/login", data={"username": "scan-viewer@example.com", "password": "viewer12345"}).json()["access_token"]
    assert client.post("/api/scan", headers={"Authorization": f"Bearer {t}"}).status_code == 403
