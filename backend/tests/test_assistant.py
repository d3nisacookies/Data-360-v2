"""The assistant: per-client switch, redaction, server-side lookups. The model is replaced by a stub
that calls a tool and reports what it was sent, so no AI service is needed."""
import json

from app.assistant import providers as PV
from app.assistant.redact import Redactor

from .test_api import borrower_id


def test_redactor_round_trip():
    R = Redactor()
    R.add("HarbourVest", "CLIENT")
    R.add("US-REG-DE-4821937", "ID")
    s = R.text("HarbourVest registered as US-REG-DE-4821937; contact a.lee@example.com on +65 6123 4567 by 2026-10-09")
    assert "HarbourVest" not in s and "4821937" not in s and "example.com" not in s and "6123" not in s
    assert "2026-10-09" in s
    assert R.restore(s).startswith("HarbourVest registered as US-REG-DE-4821937")
    assert Redactor(enabled=False).text("HarbourVest") == "HarbourVest"


def test_switch_and_chat(client, h, monkeypatch):
    bid = borrower_id(client, h, "HarbourVest")
    st = client.get(f"/api/assistant/status?borrower_id={bid}", headers=h).json()
    assert st["enabled"] is False and st["can_toggle"] is True and st["provider"] == "ollama"
    ask = {"borrower_id": bid, "messages": [{"role": "user", "content": "Why is HarbourVest referred?"}]}
    assert client.post("/api/assistant/chat", json=ask, headers=h).status_code == 403   # off by default

    assert client.put(f"/api/assistant/clients/{bid}", json={"enabled": True}, headers=h).json()["enabled"] is True
    seen = {}

    def stub(system, messages, tools, run_tool):
        seen["system"], seen["messages"] = system, messages
        seen["overview"] = run_tool("get_overview", {})
        seen["golden"] = run_tool("get_golden_record", {})
        seen["internal"] = run_tool("search_internal_elements", {"text": "KYC"})
        return PV.Answer("[CLIENT-1] is referred because of hard policy failures.", ["get_overview"])
    monkeypatch.setattr(PV, "chat", stub)
    r = client.post("/api/assistant/chat", json=ask, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["answer"].startswith("HarbourVest is referred")          # tokens restored for the user
    sent = json.dumps(seen)
    assert "HarbourVest" not in sent                                    # never sent to the model
    assert "[CLIENT-1]" in seen["messages"][0]["content"] and "[CLIENT-1]" in seen["system"]
    assert "data_version" in seen["overview"]
    assert "Corporate Registry" in seen["golden"]
    assert "[masked: personal data]" in seen["internal"] or "matches" in seen["internal"]
    events = client.get("/api/audit", headers=h).json()
    assert any(e["action"] == "ai.ask" for e in events)


def test_provider_errors_are_readable(client, h, monkeypatch):
    bid = borrower_id(client, h, "HarbourVest")
    client.put(f"/api/assistant/clients/{bid}", json={"enabled": True}, headers=h)
    monkeypatch.setattr(PV.get_settings(), "ollama_url", "http://127.0.0.1:9")   # nothing listens there
    r = client.post("/api/assistant/chat", json={"borrower_id": bid, "messages": [{"role": "user", "content": "hi"}]}, headers=h)
    assert r.status_code == 503 and "docker compose --profile ai up -d" in r.json()["detail"]


def test_viewer_cannot_switch(client, h):
    client.post("/api/users", json={"email": "ai-viewer@example.com", "password": "viewer12345", "role": "viewer"}, headers=h)
    t = client.post("/api/auth/login", data={"username": "ai-viewer@example.com", "password": "viewer12345"}).json()["access_token"]
    bid = borrower_id(client, h, "HarbourVest")
    assert client.put(f"/api/assistant/clients/{bid}", json={"enabled": False}, headers={"Authorization": f"Bearer {t}"}).status_code == 403
