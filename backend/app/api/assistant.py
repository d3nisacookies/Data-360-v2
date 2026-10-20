"""Assistant endpoints: status, the per-client switch, and chat."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import audit
from .. import workspace as W
from ..assistant import providers as PV
from ..assistant import redact as RD
from ..assistant import tools as TL
from ..db import get_db
from ..engine import fixplan as FX
from ..models import Borrower, User
from ..security import current_user, is_admin

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class Msg(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    borrower_id: int
    messages: list[Msg] = Field(min_length=1, max_length=24)


def enabled_for(db, bid: int) -> bool:
    return bool(W.setting_get(db, "ai_clients", {}).get(str(bid)))


@router.get("/status")
def status(borrower_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d = PV.describe()
    b = db.get(Borrower, borrower_id) if borrower_id else None
    return {**d, "borrower": {"id": b.id, "name": b.name} if b else None, "enabled": bool(b and enabled_for(db, b.id)),
            "can_toggle": user.role == "admin"}


@router.put("/clients/{bid}")
def toggle(bid: int, body: dict, db: Session = Depends(get_db), user: User = Depends(is_admin)):
    b = db.get(Borrower, bid)
    if not b:
        raise HTTPException(404, "No such borrower")
    on = bool(body.get("enabled"))
    m = W.setting_get(db, "ai_clients", {})
    m[str(bid)] = on
    W.setting_put(db, "ai_clients", m)
    audit.log(db, user, "ai.switch", b.name, enabled=on)
    db.commit()
    return {"enabled": on}


def instructions(name_token: str, ref: str, redacted: bool) -> str:
    return f"""You are the Data360 assistant. Data360 checks and fixes the data behind credit memos at a bank's corporate lending desk.
You are helping with one client, {name_token}. Data as at {ref}.
{"Names, identifiers and personal details are replaced by tokens such as [CLIENT-1], [ID-2] or [PERSON-1]. Use the tokens exactly as given; never guess what they stand for." if redacted else ""}
How to answer:
- Questions about this client's data, confidence, issues, the credit memo, rules or the roadmap: use the tools to look up facts first and never invent numbers. Cite record or element IDs and sources (e.g. "Bloomberg EXT-07-12"). If a step has not been run yet, say which step to run.
- General credit, risk and regulatory questions (e.g. IFRS 9 staging, covenants, MAS notices, BCBS 239): answer briefly from general knowledge and say that specifics and the bank's own thresholds should be confirmed against current sources and bank policy.
- You support analysis; you do not approve credit or give investment advice. Credit decisions stay with the approvers.
- Be concise: lead with the answer, then up to 5 short bullets. Plain text; use "- " for bullets and **bold** sparingly. No tables."""


@router.post("/chat")
def chat(body: ChatIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    b = db.get(Borrower, body.borrower_id)
    if not b:
        raise HTTPException(404, "No such borrower")
    if not enabled_for(db, b.id):
        raise HTTPException(403, f"The assistant is switched off for {b.name}. An administrator can switch it on.")
    if body.messages[-1].role != "user":
        raise HTTPException(400, "The last message must be the user's question")
    d = PV.describe()
    t0 = time.time()
    ctx = W.build_ctx(db, b)
    extra = {"rules_on": ctx["rules_on"], "p2": None, "p3": None}
    extra["fix"] = lambda: FX.build(ctx["raw"], ctx["clean"], ctx.get("seek"), W.uploads_map(db, b), ctx["owners"],
                                    set((extra["p3"] or {}).get("resolved", [])), ctx["ref_date"]) if ctx.get("clean") else None
    if ctx.get("memo_state"):
        extra["p2"] = ctx["p2"] = W.p2_state(db, b, ctx)
        if W.gates(ctx, extra["p2"], None)["p2"]:
            extra["p3"] = W.p3_state(db, b, ctx, extra["p2"])
    R = RD.for_borrower(db, b, ctx["ds_full"], enabled=d["redaction"])

    def run_tool(name, args):
        args = {k: (R.restore(v) if isinstance(v, str) else v) for k, v in (args or {}).items()}
        try:
            out = TL.run(name, args, ctx, extra)
        except Exception as e:  # noqa: BLE001 - report to the model, keep the chat going
            out = f"Lookup failed: {e.__class__.__name__}"
        return R.obj(out)[:30000]

    msgs = [{"role": m.role, "content": R.text(m.content)} for m in body.messages[-12:]]
    system = R.text(instructions("[CLIENT-1]" if d["redaction"] else b.name, ctx["ref_date"].isoformat(), d["redaction"]))
    try:
        ans = PV.chat(system, msgs, TL.TOOLS, run_tool)
    except PV.AIError as e:
        raise HTTPException(503, str(e))
    audit.log(db, user, "ai.ask", b.name, provider=d["provider"], model=d["model"], redacted=d["redaction"], tools=ans.tools,
              seconds=round(time.time() - t0, 1), question_chars=len(body.messages[-1].content))
    db.commit()
    return {"answer": R.restore(ans.text), "tools": ans.tools, "provider": d["label"], "model": d["model"], "redacted": d["redaction"]}
