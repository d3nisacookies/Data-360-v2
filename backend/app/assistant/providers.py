"""Model providers: OpenRouter, OpenAI (or any OpenAI-compatible service), Anthropic, AWS Bedrock
and Google Vertex. All are configured only on the server; keys never reach the browser.

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


def provider_name() -> str:
    s = get_settings()
    p = (s.ai_provider or "off").strip().lower()
    if p == "auto":
        return ("openrouter" if s.openrouter_api_key else "openai" if s.openai_api_key
                else "anthropic" if s.anthropic_api_key else "openrouter")
    return p


def describe() -> dict:
    s = get_settings()
    p = provider_name()
    model = s.ai_model or {"openrouter": "openrouter/free", "openai": "gpt-5-mini", "anthropic": "claude-sonnet-5-5"}.get(p, "")
    openai_label = "OpenAI API" if "api.openai.com" in s.openai_base_url else f"OpenAI-compatible API ({httpx.URL(s.openai_base_url).host})"
    label = {"openrouter": "OpenRouter", "openai": openai_label, "anthropic": "Anthropic API", "bedrock": f"AWS Bedrock · {s.aws_region}",
             "vertex": f"Google Vertex AI · {s.vertex_region}", "off": "Turned off"}.get(p, p)
    missing = ""
    if p == "openrouter" and not s.openrouter_api_key:
        missing = "Set OPENROUTER_API_KEY in .env"
    if p == "openai" and not s.openai_api_key:
        missing = "Set OPENAI_API_KEY in .env"
    if p == "anthropic" and not s.anthropic_api_key:
        missing = "Set ANTHROPIC_API_KEY in .env"
    if p in ("bedrock", "vertex") and not s.ai_model:
        missing = "Set AI_MODEL in .env to the model ID enabled in your cloud account"
    if p == "vertex" and not s.vertex_project:
        missing = "Set VERTEX_PROJECT in .env"
    return {"provider": p, "model": model, "label": label, "configured": p != "off" and not missing, "missing": missing,
            "redaction": s.ai_redact}


def chat(system: str, messages: list[dict], tools: list[dict], run_tool) -> Answer:
    d = describe()
    if d["provider"] == "off":
        raise AIError("The assistant is turned off on this server (AI_PROVIDER=off).")
    if not d["configured"]:
        raise AIError(d["missing"])
    if d["provider"] == "openai":
        return _openai(d["model"], system, messages, tools, run_tool)
    if d["provider"] == "openrouter":
        return _openai(d["model"], system, messages, tools, run_tool, openrouter=True)
    return _anthropic_family(d["provider"], d["model"], system, messages, tools, run_tool)


# ---------------- OpenAI (and OpenAI-compatible services) ----------------
OPENROUTER_URL = "https://openrouter.ai/api/v1"


def _json(r):
    try:
        return r.json()
    except ValueError:
        return None


def _err_text(j) -> str:
    """The error message from an OpenAI-style body, whatever shape it comes in."""
    if not isinstance(j, dict) or not j.get("error"):
        return ""
    e = j["error"]
    if isinstance(e, dict):
        msg = e.get("message") or e.get("code") or "the model returned an error"
        meta = e.get("metadata") or {}
        raw = meta.get("raw") if isinstance(meta, dict) else None
        return f"{msg} ({str(raw)[:120]})" if raw else str(msg)
    return str(e)


def _content_text(c) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, list):  # some models return content parts
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in c)
    return ""


def _openai(model, system, messages, tools, run_tool, openrouter=False) -> Answer:
    s = get_settings()
    base, key, name, env = ((OPENROUTER_URL, s.openrouter_api_key, "OpenRouter", "OPENROUTER_API_KEY") if openrouter
                            else (s.openai_base_url, s.openai_api_key, "OpenAI", "OPENAI_API_KEY"))
    url = base.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {key}"}
    if openrouter:
        headers.update({"HTTP-Referer": "https://github.com/d3nisacookies/Data-360-v2", "X-Title": "Data360"})
    msgs = [{"role": "system", "content": system}, *messages]
    spec = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["schema"]}} for t in tools]
    used = []
    for _ in range(MAX_ROUNDS):
        body = {"model": model, "messages": msgs}
        if spec:
            body["tools"] = spec
        try:
            r = httpx.post(url, json=body, headers=headers, timeout=s.ai_timeout)
        except httpx.ConnectError:
            raise AIError(f"Can't reach {name} ({base}) from the server. Check the network.")
        except httpx.TimeoutException:
            raise AIError("The AI service took too long to answer. Try again.")
        except httpx.HTTPError as e:
            raise AIError(f"The connection to {name} failed ({e.__class__.__name__}). Try again.")
        j = _json(r)
        err = _err_text(j)
        if r.status_code >= 300:
            if r.status_code == 401:
                raise AIError(f"The {name} key was rejected. Check {env} in .env.")
            if r.status_code == 402:
                raise AIError(f"The {name} account has no credit for {model}. Use a free model, or add credit.")
            if r.status_code == 429:
                raise AIError(f"{name} rate limit reached" + (" (free models have a daily limit)" if openrouter and model.endswith("free") else "")
                              + ". Try again later. " + err[:160])
            if r.status_code == 404:
                raise AIError(f"The model {model} is not available for this key. Set AI_MODEL in .env.")
            raise AIError(f"The AI service returned an error ({r.status_code}). {err[:200]}")
        if not isinstance(j, dict):
            raise AIError(f"{name} sent a reply Data360 could not read. Try again.")
        if err:  # OpenRouter can return 200 with an error from the upstream model
            raise AIError(f"{name}: {err[:200]}. Try again; with openrouter/free another model may answer.")
        choices = j.get("choices") or [{}]
        m = (choices[0] if isinstance(choices[0], dict) else {}).get("message") or {}
        calls = [c for c in (m.get("tool_calls") or []) if isinstance(c, dict)]
        content = _content_text(m.get("content"))
        if not calls:
            return Answer(content or "(No answer. Try asking again.)", used)
        msgs.append({"role": "assistant", "content": content, "tool_calls": calls})
        for c in calls:
            fn = c.get("function") or {}
            raw = fn.get("arguments")
            if isinstance(raw, dict):
                args = raw
            else:
                try:
                    args = json.loads(raw or "{}")
                except (TypeError, ValueError):
                    args = {}
                if not isinstance(args, dict):
                    args = {}
            used.append(fn.get("name", ""))
            msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": run_tool(fn.get("name", ""), args)})
    return Answer("I looked up several things but could not finish the answer. Please ask a narrower question.", used)


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
