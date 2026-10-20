"""Model providers. Ollama (local, free) is the default; Anthropic, AWS Bedrock and Google Vertex
are optional and configured only on the server (keys never reach the browser).

Every provider gets the same thing: a system prompt, the conversation, the tool list and a
`run_tool(name, args) -> str` callback. It loops on tool calls and returns the final text.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx

from ..config import get_settings

MAX_ROUNDS = 6


class AIError(Exception):
    """A problem the user can act on; the message is shown in the panel."""


@dataclass
class Answer:
    text: str
    tools: list[str] = field(default_factory=list)


def describe() -> dict:
    s = get_settings()
    p = (s.ai_provider or "off").lower()
    model = s.ai_model or {"ollama": "qwen2.5:7b", "anthropic": "claude-sonnet-5-5"}.get(p, "")
    label = {"ollama": "Local model (Ollama)", "anthropic": "Anthropic API", "bedrock": f"AWS Bedrock · {s.aws_region}",
             "vertex": f"Google Vertex AI · {s.vertex_region}", "off": "Turned off"}.get(p, p)
    missing = ""
    if p == "anthropic" and not s.anthropic_api_key:
        missing = "Set ANTHROPIC_API_KEY in .env"
    if p in ("bedrock", "vertex") and not s.ai_model:
        missing = "Set AI_MODEL in .env to the model ID enabled in your cloud account"
    if p == "vertex" and not s.vertex_project:
        missing = "Set VERTEX_PROJECT in .env"
    return {"provider": p, "model": model, "label": label, "configured": p != "off" and not missing, "missing": missing,
            "local": p == "ollama", "redaction": s.ai_redact}


def chat(system: str, messages: list[dict], tools: list[dict], run_tool) -> Answer:
    d = describe()
    if d["provider"] == "off":
        raise AIError("The assistant is turned off on this server (AI_PROVIDER=off).")
    if not d["configured"]:
        raise AIError(d["missing"])
    if d["provider"] == "ollama":
        return _ollama(d["model"], system, messages, tools, run_tool)
    return _anthropic_family(d["provider"], d["model"], system, messages, tools, run_tool)


# ---------------- Ollama ----------------
def _ollama(model, system, messages, tools, run_tool, use_tools=True) -> Answer:
    s = get_settings()
    url = s.ollama_url.rstrip("/") + "/api/chat"
    msgs = [{"role": "system", "content": system}, *messages]
    spec = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["schema"]}} for t in tools]
    used = []
    for _ in range(MAX_ROUNDS):
        body = {"model": model, "messages": msgs, "stream": False, "options": {"temperature": 0.2, "num_ctx": 16384}}
        if use_tools and spec:
            body["tools"] = spec
        try:
            r = httpx.post(url, json=body, timeout=s.ai_timeout)
        except httpx.ConnectError:
            raise AIError(f"Can't reach the local model at {s.ollama_url}. Start it with: docker compose --profile ai up -d")
        except httpx.TimeoutException:
            raise AIError("The local model took too long to answer. Try a shorter question, or a smaller model (AI_MODEL).")
        if r.status_code == 404 and "not found" in r.text:
            raise AIError(f"The model {model} is not downloaded yet. Run: docker compose exec ollama ollama pull {model}")
        if r.status_code == 400 and "does not support tools" in r.text and use_tools:
            raise _NoTools()
        if r.status_code >= 300:
            raise AIError(f"The local model returned an error ({r.status_code}): {r.text[:200]}")
        m = r.json().get("message") or {}
        calls = m.get("tool_calls") or []
        if not calls:
            return Answer(m.get("content") or "(No answer.)", used)
        msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": calls})
        for c in calls:
            fn = c.get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            used.append(fn.get("name", ""))
            msgs.append({"role": "tool", "tool_name": fn.get("name", ""), "content": run_tool(fn.get("name", ""), args)})
    return Answer("I looked up several things but could not finish the answer. Please ask a narrower question.", used)


class _NoTools(Exception):
    pass


# ---------------- Anthropic, Bedrock, Vertex ----------------
def _client(provider):
    s = get_settings()
    try:
        import anthropic
    except ImportError:  # pragma: no cover
        raise AIError("The anthropic package is not installed on the server.")
    if provider == "anthropic":
        return anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=s.ai_timeout)
    if provider == "bedrock":
        return anthropic.AnthropicBedrock(aws_region=s.aws_region, timeout=s.ai_timeout)  # credentials from the standard AWS chain
    if provider == "vertex":
        return anthropic.AnthropicVertex(project_id=s.vertex_project, region=s.vertex_region, timeout=s.ai_timeout)  # Google application default credentials
    raise AIError(f"Unknown AI_PROVIDER {provider}")


def _anthropic_family(provider, model, system, messages, tools, run_tool) -> Answer:
    import anthropic
    client = _client(provider)
    spec = [{"name": t["name"], "description": t["description"], "input_schema": t["schema"]} for t in tools]
    msgs = [dict(m) for m in messages]
    used = []
    for _ in range(MAX_ROUNDS):
        try:
            r = client.messages.create(model=model, max_tokens=1500, system=system, tools=spec, messages=msgs)
        except anthropic.AuthenticationError:
            raise AIError("The AI provider rejected the credentials configured on the server.")
        except anthropic.NotFoundError:
            raise AIError(f"The model {model} is not available for this account or region. Check AI_MODEL.")
        except anthropic.APIConnectionError:
            raise AIError("Can't reach the AI provider from the server. Check the network and region settings.")
        except anthropic.APIStatusError as e:
            raise AIError(f"The AI provider returned an error ({e.status_code}).")
        text = "\n".join(b.text for b in r.content if b.type == "text")
        if r.stop_reason != "tool_use":
            return Answer(text or "(No answer.)", used)
        msgs.append({"role": "assistant", "content": [b.model_dump() for b in r.content]})
        results = []
        for b in r.content:
            if b.type == "tool_use":
                used.append(b.name)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": run_tool(b.name, b.input or {})})
        msgs.append({"role": "user", "content": results})
    return Answer("I looked up several things but could not finish the answer. Please ask a narrower question.", used)


def chat_with_fallback(system, messages, tools, run_tool, dump) -> Answer:
    """Ollama models without tool support get the data in the prompt instead."""
    try:
        return chat(system, messages, tools, run_tool)
    except _NoTools:
        d = describe()
        return _ollama(d["model"], system + "\n\nDATA (current state, already redacted):\n" + dump(), messages, [], run_tool, use_tools=False)
