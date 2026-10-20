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
    assert st["enabled"] is False and st["can_toggle"] is True and st["provider"] == "openrouter"
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


def test_missing_key_is_explained(client, h):
    bid = borrower_id(client, h, "HarbourVest")
    client.put(f"/api/assistant/clients/{bid}", json={"enabled": True}, headers=h)
    st = client.get(f"/api/assistant/status?borrower_id={bid}", headers=h).json()
    assert st["configured"] is False and "OPENROUTER_API_KEY" in st["missing"]
    r = client.post("/api/assistant/chat", json={"borrower_id": bid, "messages": [{"role": "user", "content": "hi"}]}, headers=h)
    assert r.status_code == 503 and "OPENROUTER_API_KEY" in r.json()["detail"]


def test_viewer_cannot_switch(client, h):
    client.post("/api/users", json={"email": "ai-viewer@example.com", "password": "viewer12345", "role": "viewer"}, headers=h)
    t = client.post("/api/auth/login", data={"username": "ai-viewer@example.com", "password": "viewer12345"}).json()["access_token"]
    bid = borrower_id(client, h, "HarbourVest")
    assert client.put(f"/api/assistant/clients/{bid}", json={"enabled": False}, headers={"Authorization": f"Bearer {t}"}).status_code == 403


def test_openai_provider_tool_round_trip(client, h, monkeypatch):
    """OpenAI chat-completions format: one tool call, then the answer. The key goes in a header, never to the browser."""
    import httpx
    s = PV.get_settings()
    monkeypatch.setattr(s, "ai_provider", "auto")
    monkeypatch.setattr(s, "openai_api_key", "sk-test-not-real")
    bid = borrower_id(client, h, "HarbourVest")
    client.put(f"/api/assistant/clients/{bid}", json={"enabled": True}, headers=h)
    st = client.get(f"/api/assistant/status?borrower_id={bid}", headers=h).json()
    assert st["provider"] == "openai" and st["model"] == "gpt-5-mini" and "sk-test" not in json.dumps(st)
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "body": json, "headers": headers})
        tool_msgs = [m for m in json["messages"] if m["role"] == "tool"]
        if not tool_msgs:
            msg = {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "get_overview", "arguments": "{}"}}]}
        else:
            assert tool_msgs[0]["tool_call_id"] == "call_1"
            msg = {"role": "assistant", "content": "Client " + __import__("json").loads(tool_msgs[0]["content"])["client"]}
        return httpx.Response(200, json={"choices": [{"message": msg}]})
    monkeypatch.setattr(PV.httpx, "post", fake_post)
    r = client.post("/api/assistant/chat", json={"borrower_id": bid, "messages": [{"role": "user", "content": "What did HarbourVest get?"}]}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["answer"] == "Client HarbourVest" and r.json()["tools"] == ["get_overview"]
    assert calls[0]["url"] == "https://api.openai.com/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-test-not-real"
    assert calls[0]["body"]["tools"][0]["type"] == "function"
    assert "HarbourVest" not in __import__("json").dumps([c["body"] for c in calls])

    def bad_key(url, json=None, headers=None, timeout=None):
        return httpx.Response(401, json={"error": {"message": "Incorrect API key"}})
    monkeypatch.setattr(PV.httpx, "post", bad_key)
    r = client.post("/api/assistant/chat", json={"borrower_id": bid, "messages": [{"role": "user", "content": "hi"}]}, headers=h)
    assert r.status_code == 503 and "OPENAI_API_KEY" in r.json()["detail"]


def test_openrouter_is_picked_from_its_key(client, h, monkeypatch):
    import httpx
    s = PV.get_settings()
    monkeypatch.setattr(s, "ai_provider", "auto")
    monkeypatch.setattr(s, "openrouter_api_key", "sk-or-test")
    bid = borrower_id(client, h, "HarbourVest")
    client.put(f"/api/assistant/clients/{bid}", json={"enabled": True}, headers=h)
    st = client.get(f"/api/assistant/status?borrower_id={bid}", headers=h).json()
    assert st["provider"] == "openrouter" and st["model"] == "openrouter/free" and st["configured"]
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, headers=headers, model=json["model"])
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "Hello [CLIENT-1]"}}]})
    monkeypatch.setattr(PV.httpx, "post", fake_post)
    r = client.post("/api/assistant/chat", json={"borrower_id": bid, "messages": [{"role": "user", "content": "hi"}]}, headers=h)
    assert r.json()["answer"] == "Hello HarbourVest"
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions" and seen["model"] == "openrouter/free"
    assert seen["headers"]["Authorization"] == "Bearer sk-or-test" and seen["headers"]["X-Title"] == "Data360"

    monkeypatch.setattr(PV.httpx, "post", lambda *a, **k: httpx.Response(429, json={"error": {"message": "Rate limit exceeded: free-models-per-day"}}))
    r = client.post("/api/assistant/chat", json={"borrower_id": bid, "messages": [{"role": "user", "content": "hi"}]}, headers=h)
    assert r.status_code == 503 and "daily limit" in r.json()["detail"]
