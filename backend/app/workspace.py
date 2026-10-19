"""Per-borrower working state (credit memo, Phase 2, Phase 3), global settings, and the shared
context each later step is built from. Each state carries a stamp of what it was built on; when
the inputs change (new Clean/Normalise run, memo re-retained, roadmap re-approved) it starts over."""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from .engine import memo as MM
from .engine import phase2 as P2
from .engine import phase3 as P3
from .engine.policies import ALL as ALL_RULES, clean_selection
from .models import Borrower, Setting, Upload, Workspace
from .services import current_dataset, latest_run, load_dataset, ref_date, step_status, uploads_for

FACTORY = {"memo": MM.new_state, "p2": P2.new_state, "p3": P3.new_state}


def now_txt() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


# ---------------- storage ----------------
def ws_get(db: Session, bid: int, key: str) -> dict:
    row = db.scalar(select(Workspace).where(Workspace.borrower_id == bid, Workspace.key == key))
    return copy.deepcopy(row.data) if row and row.data else FACTORY[key]()


def ws_put(db: Session, bid: int, key: str, data: dict, user=None) -> None:
    row = db.scalar(select(Workspace).where(Workspace.borrower_id == bid, Workspace.key == key))
    if not row:
        row = Workspace(borrower_id=bid, key=key, data={})
        db.add(row)
    row.data = json.loads(json.dumps(data, default=str))
    row.updated_by = user.id if user else None
    flag_modified(row, "data")
    db.flush()


def setting_get(db: Session, key: str, default):
    s = db.scalar(select(Setting).where(Setting.key == key))
    return copy.deepcopy(s.value) if s else default


def setting_put(db: Session, key: str, value) -> None:
    s = db.scalar(select(Setting).where(Setting.key == key))
    if not s:
        s = Setting(key=key, value={})
        db.add(s)
    s.value = value
    flag_modified(s, "value")
    db.flush()


def owners(db) -> dict:
    return setting_get(db, "source_owners", {})


def rules_on(db) -> list[str]:
    v = setting_get(db, "policies", None)
    return clean_selection(v["on"]) if v and "on" in v else list(ALL_RULES)


# ---------------- context ----------------
class Ctx(dict):
    """Everything the later steps need for one borrower. Missing prerequisites leave keys unset."""


def p1_status(db: Session, b: Borrower) -> dict:
    s = step_status(db, b)
    ok = {k: bool(s[k]) and not s[k]["stale"] for k in s}
    return {"status": s, "ok": ok, "data_ready": all(ok.values())}


def build_ctx(db: Session, b: Borrower, need_memo: bool = True) -> Ctx:
    ref = ref_date()
    st = p1_status(db, b)
    ctx = Ctx(borrower=b.name, borrower_id=b.id, ref_date=ref, p1=st, owners=owners(db), rules_on=rules_on(db))
    raw, cleaned, cr = current_dataset(db, b, ref)
    ctx["raw"] = raw
    ctx["ds_full"] = load_dataset(db, b, ref)
    for s in ("collect", "seek", "assess", "normalise"):
        r = latest_run(db, b.id, s)
        ctx[{"normalise": "norm"}.get(s, s)] = r.result if r and st["ok"][s] else None
        ctx[s + "_run"] = r.id if r else None
    ctx["clean"] = cr.result if cleaned is not None and st["ok"]["clean"] else None
    ctx["clean_run"] = cr.id if cr else None
    ctx["ds"] = cleaned if ctx["clean"] else None
    ctx["stale"] = sum(1 for r in cleaned.live() if cleaned.is_stale(r)) if cleaned is not None else 0
    if not need_memo or not st["data_ready"]:
        return ctx
    memo = memo_state(db, b, ctx)
    ctx["memo_state"] = memo
    ctx["M"] = MM.build(ctx["ds"], ctx["ds_full"], b.id, ctx["clean"], ctx["assess"], ctx["norm"], ctx["seek"], ctx["rules_on"], memo, ctx["owners"])
    ctx["ST"] = MM.stats(ctx["M"], memo)
    return ctx


def memo_stamp(ctx) -> str:
    return f"{ctx['clean_run']}:{ctx['assess_run']}:{ctx['normalise_run']}"


def memo_state(db, b, ctx) -> dict:
    st = ws_get(db, b.id, "memo")
    stamp = memo_stamp(ctx)
    if st.get("stamp") != stamp:
        fresh = MM.new_state()
        fresh.update(on=st.get("on", fresh["on"]), extra=st.get("extra", []), stamp=stamp)
        st = fresh
        ws_put(db, b.id, "memo", st)
    return st


def p2_state(db, b, ctx) -> dict:
    st = ws_get(db, b.id, "p2")
    R = ctx["memo_state"].get("retained") if ctx.get("memo_state") else None
    stamp = R["hash"] if R else None
    if st.get("stamp") != stamp:
        fresh = P2.new_state()
        fresh["assume"] = st.get("assume", fresh["assume"])
        fresh["stamp"] = stamp
        st = fresh
        ws_put(db, b.id, "p2", st)
    return st


def p3_state(db, b, ctx, p2: dict) -> dict:
    st = ws_get(db, b.id, "p3")
    stamp = (p2.get("approved") or {}).get("at")
    if st.get("stamp") != stamp:
        st = P3.new_state()
        st["stamp"] = stamp
        ws_put(db, b.id, "p3", st)
    return st


def gates(ctx, p2: dict | None, p3: dict | None) -> dict:
    p1 = bool(ctx.get("memo_state", {}).get("retained")) and ctx["p1"]["data_ready"]
    p2c = bool(p1 and p2 and p2.get("approved") and p2["R"].get("road"))
    p3c = bool(p2c and p3 and all(p3["st"][s["k"]]["done"] for s in P3.STEPS))
    return {"p1": p1, "p2": p2c, "p3": p3c, "open": {1: True, 2: p1, 3: p2c}}


def portfolio(db: Session, ref):
    def f():
        out = []
        for x in db.scalars(select(Borrower).order_by(Borrower.name)).all():
            out.append((x.name, load_dataset(db, x, ref)))
        return out
    return f


def upload_dates(db: Session, b: Borrower) -> dict:
    """Latest upload date per source (internal sources have no as-of date of their own)."""
    from .models import Observation
    rows = db.execute(select(Observation.source, Upload.created_at).join(Upload, Upload.id == Observation.upload_id)
                      .where(Observation.borrower_id == b.id).distinct()).all()
    out = {}
    for s, at in rows:
        d = at.date().isoformat()
        out[s] = max(out.get(s, d), d)
    return out


def uploads_map(db: Session, b: Borrower) -> dict:
    out = {}
    for u in uploads_for(db, b.id):
        fmt = (u.detected_format or "").lower()
        out[u.id] = {"name": u.filename, "folder": "Data dictionary (internal)" if "dict" in fmt else "Records (external)"}
    return out


def sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()
