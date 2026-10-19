"""Dashboard, credit memo (step 5), Phase 2, Phase 3, fix plan, project plans, source tasks,
reports and the rules & policies setting. Screens are returned as structured sections that the
web app draws; every change goes through POST .../action and returns the refreshed screen."""
from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from .. import workspace as W
from ..db import get_db
from ..engine import confidence as CF
from ..engine import fixplan as FX
from ..engine import memo as MM
from ..engine import memo_view as MV
from ..engine import phase2 as P2
from ..engine import phase3 as P3
from ..engine import plans as PL
from ..engine import report as RP
from ..engine import ui
from ..engine.blocks import html_page, safe_name, to_docx
from ..engine.policies import ALL as ALL_RULES, catalogue, clean_selection
from ..engine.registry import OWNER_CHOICES
from ..models import Borrower, User
from ..security import can_edit, current_user

router = APIRouter(prefix="/api", tags=["workspace"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class Act(BaseModel):
    action: str
    arg: str | int | dict | list | None = None
    value: str | int | float | None = None
    step: str | None = None


def _b(db, bid) -> Borrower:
    b = db.get(Borrower, bid)
    if not b:
        raise HTTPException(404, "No such borrower")
    return b


def _file(data: bytes, name: str, mime: str) -> Response:
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{safe_name(name)}"'})


def _need_memo(ctx):
    if not ctx["p1"]["data_ready"]:
        miss = [k for k, v in ctx["p1"]["ok"].items() if not v]
        names = {"collect": "Collector", "seek": "Seeker", "assess": "Assess", "clean": "Clean", "normalise": "Normalise"}
        raise HTTPException(409, "Run " + ", ".join(names[m] for m in miss) + " first (or re-run them: newer data or runs make them out of date).")


def _p2(db, b, ctx):
    p2 = W.p2_state(db, b, ctx)
    ctx["p2"] = p2
    return p2


def _p3(db, b, ctx):
    p2 = _p2(db, b, ctx)
    p3 = W.p3_state(db, b, ctx, p2)
    ctx["n_borrowers"] = len(db.scalars(select(Borrower.id)).all())
    ctx["portfolio"] = W.portfolio(db, ctx["ref_date"])
    return p2, p3


# ================= dashboard =================
@router.get("/borrowers/{bid}/overview")
def overview(bid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    b = _b(db, bid)
    ctx = W.build_ctx(db, b)
    st = ctx["p1"]["status"]
    memo = ctx.get("memo_state")
    p2 = _p2(db, b, ctx) if memo else None
    p3 = W.p3_state(db, b, ctx, p2) if p2 else None
    G = W.gates(ctx, p2, p3)
    cl = ctx.get("clean")
    ok = ctx["p1"]["ok"]
    p1 = [{"go": "source", "n": "1", "t": "Source the data & documents", "done": ok["collect"] and ok["seek"], "part": bool(st["collect"] or st["seek"]),
           "d": "Collector and Seeker run" if ok["collect"] and ok["seek"] else "Collector run · Seeker next" if ok["collect"] else "Collector and Seeker"},
          {"go": "assess", "n": "2", "t": "Assess the data", "done": ok["assess"], "part": bool(st["assess"]), "d": "Scored on the 7 criteria" if ok["assess"] else "7 quality criteria"},
          {"go": "clean", "n": "3", "t": "Clean the data", "done": ok["clean"], "part": bool(st["clean"]),
           "d": f"{len(cl['log'])} changes · {len(cl['escalations'])} escalated" if cl else "Duplicates, errors, critical fields, conflicts"},
          {"go": "normalise", "n": "4", "t": "Normalise the data", "done": ok["normalise"], "part": bool(st["normalise"]),
           "d": "Common definitions v1.0 published" if ok["normalise"] else "Metrics, KPIs, master data, semantic layer"},
          {"go": "memo", "n": "5", "t": "Build the credit memo", "done": bool(memo and memo.get("retained")), "part": bool(memo and memo["done"]),
           "d": (f"Retained {memo['retained']['version']} · {MM.status(memo)}" if memo.get("retained") else f"{memo['done']} of 5 stages · not retained" if memo["done"]
                 else "Cleared when the memo is retained") if memo else "Cleared when the memo is retained"}]
    p2s = []
    for k in P2.ORDER:
        S = P2.STEPS[k]
        R = p2["R"][k] if p2 and G["open"][2] else None
        d = S["h"] if not R else (f"{len(R['G'])} gaps · {sum(1 for g in R['G'] if g['impact'] == 'High')} high impact" if k == "gap" else
                                   f"{len(R['R'])} recommendations · {sum(1 for r in R['R'] if r['quad'] == 'Quick win')} quick wins" if k == "rec" else
                                   f"{len(R['D'])} domains · average {round(sum(x['overall'] for x in R['D']) / len(R['D'])) if R['D'] else 0}%" if k == "conf" else
                                   f"{len(R['I'])} initiatives · {'approved' if p2.get('approved') else 'awaiting approval'}")
        p2s.append({"k": k, "n": S["n"], "t": S["h"], "d": d, "done": bool(R) and (k != "road" or bool(p2.get("approved"))), "part": bool(R)})
    p3s = []
    for i, s in enumerate(P3.STEPS):
        x = p3["st"][s["k"]] if p3 and G["open"][3] else None
        I = [y for y in p2["R"]["road"]["I"] if s["hz"] in y["hz"]] if p2 and p2["R"].get("road") and G["open"][3] else []
        d = (f"Completed {x['done']}" if x and x["done"] else "Run · not yet completed" if x and x["R"] else
             f"{len(I)} initiative{'s' if len(I) > 1 else ''} planned: {', '.join(y['name'] for y in I)}." if I else f"{s['m']}: " + ", ".join(P3.STD[s["k"]]).lower() + ".")
        p3s.append({"k": s["k"], "n": s["n"], "t": f"{s['t']} · {s['m']}", "d": d, "done": bool(x and x["done"]), "part": bool(x and x["R"])})
    S = CF.stages(ctx.get("assess"), ctx.get("norm"))
    last = S[-1] if S else None
    if G["open"][3] and p3 and p3.get("baseline"):
        kp = [(f"{P3.confidence(ctx, p3)['now']}%", "Data confidence · Phase 3"), (str(sum(1 for i in P3.issues(ctx) if i["id"] not in p3["resolved"])), "Open issues")]
    else:
        kp = [(f"{last['pct']}%" if last else "—", "Data confidence" + (f" · {last['label'].lower()}" if last else "")), (str(len(cl["escalations"])) if cl else "—", "Open escalations")]
    M = ctx.get("M")
    kp += [(MM.status(memo) if memo and memo.get("retained") else f"{M['decision']} (draft)" if M and memo["done"] else "Not started", "Credit memo", True),
           (f"{sum(1 for s in p1 if s['done'])} of 5", "Phase 1 steps done"), (f"{sum(1 for k in ('p1', 'p2', 'p3') if G[k])} of 3", "Phases cleared")]
    return {"borrower": {"id": b.id, "name": b.name, "facility_ids": b.facility_ids}, "gates": G, "kpis": [{"v": v[0], "k": v[1], "sm": len(v) > 2} for v in kp],
            "phases": [{"id": 1, "steps": p1}, {"id": 2, "steps": p2s}, {"id": 3, "steps": p3s}], "battery": battery(S), "rules_on": len(ctx["rules_on"])}


def battery(S):
    if not S:
        return None
    L = S[-1]
    return {"pct": L["pct"], "rating": L["r"], "cap": L["cap"], "provisional": L["provisional"], "stages": [{"label": x["label"], "pct": x["pct"]} for x in S],
            "breakdown": CF.breakdown(S)}


@router.get("/borrowers/{bid}/confidence")
def confidence(bid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    ctx = W.build_ctx(db, _b(db, bid), need_memo=False)
    return battery(CF.stages(ctx.get("assess"), ctx.get("norm")))


# ================= rules & policies, owners =================
@router.get("/policies")
def policies(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return {**catalogue(), "on": W.rules_on(db), "all": ALL_RULES}


@router.put("/policies")
def set_policies(body: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(can_edit)):
    on = clean_selection(body.get("on"))
    W.setting_put(db, "policies", {"on": on})
    audit.log(db, user, "policies.update", "", on=len(on))
    db.commit()
    return {"on": on}


@router.get("/owners")
def get_owners(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return {"owners": W.owners(db), "choices": OWNER_CHOICES}


@router.post("/owners")
def set_owner(body: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(can_edit)):
    src, own = str(body.get("source") or "").strip(), str(body.get("owner") or "").strip()
    if not src:
        raise HTTPException(400, "source is required")
    o = W.owners(db)
    if own:
        o[src] = own[:120]
    else:
        o.pop(src, None)
    W.setting_put(db, "source_owners", o)
    audit.log(db, user, "owner.assign", src, owner=own)
    db.commit()
    return {"owners": o}


# ================= source tasks and report =================
def _report(db, b, facility=""):
    ctx = W.build_ctx(db, b, need_memo=False)
    return RP.build({**ctx, "facility": facility, "upload_dates": W.upload_dates(db, b)})


@router.get("/borrowers/{bid}/report")
def report(bid: int, facility: str = "", db: Session = Depends(get_db), _: User = Depends(current_user)):
    R = _report(db, _b(db, bid), facility)
    return {"callout": R["callout"], "battery": R["battery"], "bullets": R["bullets"], "actions": R["actions"], "tasks": R["tasks"], "file": R["file"]}


@router.get("/borrowers/{bid}/report.docx")
def report_docx(bid: int, facility: str = "", db: Session = Depends(get_db), _: User = Depends(current_user)):
    b = _b(db, bid)
    R = _report(db, b, facility)
    return _file(to_docx(R["blocks"], R["file"], header=f"Data360 · Source findings · {b.name}"), R["file"] + ".docx", DOCX)


@router.get("/borrowers/{bid}/report.html")
def report_html(bid: int, facility: str = "", db: Session = Depends(get_db), _: User = Depends(current_user)):
    R = _report(db, _b(db, bid), facility)
    return _file(html_page(R["blocks"], R["file"]).encode(), R["file"] + ".html", "text/html")


# ================= credit memo =================
def memo_view(db, b, ctx) -> dict:
    if not ctx["p1"]["data_ready"]:
        return {"available": False, "why": "The credit memo is built from the cleaned and normalised data. Run Source, Assess, Clean and Normalise first."}
    st = ctx["memo_state"]
    M, ST = ctx["M"], ctx["ST"]
    return {"available": True, "setup": MV.setup(st), "scope": f"Builds the memo for {b.name} from the cleaned data pack v1.1 and common definitions v1.0.",
            "sections": MV.sections(M, ST, st, ctx["ref_date"], True, len(ctx["rules_on"])), "status": MM.status(st), "version": MM.version(st),
            "retained": st.get("retained"), "decision": M["decision"], "facility": st.get("facility") or ""}


@router.get("/borrowers/{bid}/memo")
def memo_get(bid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    b = _b(db, bid)
    v = memo_view(db, b, W.build_ctx(db, b))
    db.commit()
    return v


@router.post("/borrowers/{bid}/memo/action")
def memo_action(bid: int, body: Act, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    b = _b(db, bid)
    ctx = W.build_ctx(db, b)
    _need_memo(ctx)
    st = ctx["memo_state"]
    a, arg = body.action, body.arg
    locked = bool(st.get("retained"))
    if locked and a not in ("noop",):
        raise HTTPException(409, "The memo is retained and locked. Re-run Clean or Normalise to start a new version.")
    if a == "sec.toggle":
        if arg in MM.CORE:
            st["on"] = [x for x in st["on"] if x != arg] if arg in st["on"] else [*st["on"], arg]
    elif a == "sec.add":
        add = [s[0] for s in MM.SECTIONS if not s[2] and s[0] not in st["extra"]] if arg == "*" else [arg] if arg in MM.SEC and not MM.SEC[arg]["core"] else []
        st["extra"] = sorted(set(st["extra"]) | set(add), key=lambda n: [s[0] for s in MM.SECTIONS].index(n))
    elif a == "sec.remove":
        st["extra"] = [x for x in st["extra"] if x != arg]
    elif a == "run":
        fr, to = (int(arg.get("from", 1)), int(arg.get("to", 5))) if isinstance(arg, dict) else (1, 5)
        if not (1 <= fr <= to <= 5) or st["done"] < fr - 1:
            raise HTTPException(409, f"Run {MM.STAGES[fr - 2]['n']} first")
        if not MM.selected(st):
            raise HTTPException(409, "Choose at least one section")
        st["done"] = max(st["done"], to)
        st["built_at"] = W.now_txt()
        if not st["approvals"][0]["name"] and ctx["M"].get("rmName"):
            st["approvals"][0]["name"] = ctx["M"]["rmName"]
    elif a == "approval":
        i, fld, val = int(arg["i"]), arg["field"], str(arg.get("value") or "")[:300]
        if fld not in ("name", "decision", "comment") or not 0 <= i < len(st["approvals"]):
            raise HTTPException(400, "Bad approval field")
        if fld == "decision":
            if val and (val not in MM.DECISIONS or (i > 0 and not st["approvals"][i - 1]["decision"])):
                raise HTTPException(409, "The previous approver must decide first")
            st["approvals"][i]["decision"] = val
            st["approvals"][i]["date"] = ctx["ref_date"].isoformat() if val else ""
            if not val:
                for x in st["approvals"][i + 1:]:
                    x["decision"], x["date"] = "", ""
        else:
            st["approvals"][i][fld] = val
    elif a == "edit":
        k, to, why = arg.get("key"), str(arg.get("to") or "").strip(), str(arg.get("reason") or "").strip()
        if not k or k not in ctx["M"]["F"] or not to:
            raise HTTPException(400, "Choose a field and enter a new value")
        if not why:
            raise HTTPException(400, "Give a reason for the edit")
        f = ctx["M"]["F"][k]
        by = next((x["name"] for x in st["approvals"] if x["name"] and not x["decision"]), None) or st["approvals"][0]["name"] or user.name or user.email
        st["edits"].append({"key": k, "label": f"{'Control' if f['sec'] == '0' else f['sec']} · {f['label']}", "from": f["v"], "to": to[:500], "reason": why[:300],
                            "by": by, "at": W.now_txt()})
    elif a == "retain":
        if st["done"] < 5 or not st["approvals"][-1]["decision"]:
            raise HTTPException(409, "All approvers, ending with the Credit Committee, must decide first")
        M = MM.build(ctx["ds"], ctx["ds_full"], b.id, ctx["clean"], ctx["assess"], ctx["norm"], ctx["seek"], ctx["rules_on"], st, ctx["owners"])
        B = MM.blocks(M, MM.stats(M, st), st, ctx["ref_date"])
        mat = M["F"].get("4|Maturity Date", {}).get("v", "")
        yr = int(mat[:4]) + 7 if re.match(r"^\d{4}", str(mat)) else ctx["ref_date"].year + 7
        st["retained"] = {"version": "v1.0", "at": W.now_txt(), "hash": W.sha256(B), "retention": f"Credit file record; retain 7 years after final maturity (until {yr}-12-31)",
                          "legalHold": "N", "location": "Data360 · credit file", "by": user.email}
        audit.log(db, user, "memo.retain", b.name, hash=st["retained"]["hash"], decision=st["approvals"][-1]["decision"])
    else:
        raise HTTPException(400, "Unknown action")
    W.ws_put(db, b.id, "memo", st, user)
    db.commit()
    return memo_view(db, b, W.build_ctx(db, b))


def _memo_ctx(db, bid):
    b = _b(db, bid)
    ctx = W.build_ctx(db, b)
    _need_memo(ctx)
    return b, ctx


def _memo_file(ctx):
    M, st = ctx["M"], ctx["memo_state"]
    return f"Credit Memo - {re.sub(r'[^\w &.-]', '', M['c']).rstrip('.')} - {M['ref']} - {MM.version(st)}"


@router.get("/borrowers/{bid}/memo.docx")
def memo_docx(bid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    b, ctx = _memo_ctx(db, bid)
    M, st = ctx["M"], ctx["memo_state"]
    B = MM.blocks(M, ctx["ST"], st, ctx["ref_date"])
    name = _memo_file(ctx)
    return _file(to_docx(B, name, header=f"Credit Memo {M['ref']} · {M['c']} · {MM.version(st)}"), name + ".docx", DOCX)


@router.get("/borrowers/{bid}/memo.html")
def memo_html(bid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    b, ctx = _memo_ctx(db, bid)
    B = MM.blocks(ctx["M"], ctx["ST"], ctx["memo_state"], ctx["ref_date"])
    name = _memo_file(ctx)
    return _file(html_page(B, name).encode(), name + ".html", "text/html")


@router.get("/borrowers/{bid}/evidence.xlsx")
def memo_evidence(bid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    b, ctx = _memo_ctx(db, bid)
    if not ctx["memo_state"].get("retained"):
        raise HTTPException(409, "Retain the memo first")
    name = "Credit Memo Evidence Pack - " + _memo_file(ctx).replace("Credit Memo - ", "")
    return _file(MV.evidence_xlsx(ctx["M"], ctx["ST"], ctx["memo_state"], ctx["ref_date"]), name + ".xlsx", XLSX)


# ================= Phase 2 =================
def _setup(std: dict, pick: dict, sel: list, extra: list, locked=False) -> dict:
    return {"std": [{"name": k, "desc": v, "on": k in sel} for k, v in std.items()], "extra": [{"name": n, "desc": pick.get(n, "")} for n in extra],
            "pick": [n for n in pick if n not in extra], "count": f"{len(sel) + len(extra)} selected", "locked": locked}


def p2_view(db, b, ctx, k) -> dict:
    if not W.gates(ctx, None, None)["p1"]:
        return {"available": False, "why": "Phase 2 unlocks when all five Phase 1 steps are done and the credit memo is retained."}
    st = ctx["p2"]
    k = k if k in P2.STEPS and P2.can(st, k) else next((x for x in reversed(P2.ORDER) if P2.can(st, x) and st["R"][x]), "gap")
    S = P2.STEPS[k]
    why = {"rec": "Run the gap analysis first", "conf": "Prioritise recommendations first", "road": "Rate confidence first"}
    nav = [{"k": x, "n": P2.STEPS[x]["n"], "t": P2.STEPS[x]["t"], "can": bool(P2.can(st, x)), "why": why.get(x, ""), "done": bool(st["R"][x])} for x in P2.ORDER]
    scope = {"gap": f"Uses the Phase 1 results for {b.name}: sourcing, quality scores, cleaning escalations, definitions and the retained credit memo.",
             "rec": f"Builds on {len(st['R']['gap']['G']) if st['R']['gap'] else 0} gaps from step 6.", "conf": "Scores each domain from the memo values, their sources, dates and governance.",
             "road": "Groups recommendations into initiatives on the Phase 3 horizons."}[k]
    return {"available": True, "step": k, "nav": nav, "crumb": f"Step {S['n']} · {S['t']}", "h1": S["h"], "lbl": S["lbl"],
            "setup": _setup(S["std"], S["pick"], st["sel"][k], st["extra"][k]), "scope": scope, "verb": S["verb"] + (" again" if st["R"][k] else ""),
            "sections": P2.results_view(st, k, ctx), "approved": st.get("approved")}


@router.get("/borrowers/{bid}/p2")
def p2_get(bid: int, step: str = "gap", db: Session = Depends(get_db), _: User = Depends(current_user)):
    b = _b(db, bid)
    ctx = W.build_ctx(db, b)
    if ctx.get("memo_state"):
        _p2(db, b, ctx)
    v = p2_view(db, b, ctx, step)
    db.commit()
    return v


def _p2_run(st, k, ctx):
    fn = {"gap": lambda: P2.run_gap(st, ctx), "rec": lambda: P2.run_rec(st), "conf": lambda: P2.run_conf(st, ctx), "road": lambda: P2.run_road(st, ctx)}[k]
    st["R"][k] = fn()
    for x in P2.ORDER[P2.ORDER.index(k) + 1:]:
        st["R"][x] = None
    st["approved"] = None


@router.post("/borrowers/{bid}/p2/action")
def p2_action(bid: int, body: Act, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    b = _b(db, bid)
    ctx = W.build_ctx(db, b)
    if not W.gates(ctx, None, None)["p1"]:
        raise HTTPException(409, "Phase 2 is locked until Phase 1 is cleared")
    st = _p2(db, b, ctx)
    k = body.step if body.step in P2.STEPS else "gap"
    a, arg, val = body.action, body.arg, body.value
    if st.get("approved") and a not in ("run",):
        raise HTTPException(409, "The roadmap is approved. Run a step again to start a new version.")
    if a == "sel.toggle":
        s = st["sel"][k]
        if arg in P2.STEPS[k]["std"]:
            st["sel"][k] = [x for x in s if x != arg] if arg in s else [*s, arg]
    elif a == "extra.add":
        if arg in P2.STEPS[k]["pick"] and arg not in st["extra"][k]:
            st["extra"][k].append(arg)
    elif a == "extra.remove":
        st["extra"][k] = [x for x in st["extra"][k] if x != arg]
    elif a == "run":
        if not P2.can(st, k):
            raise HTTPException(409, "Run the previous step first")
        if not st["sel"][k] and not st["extra"][k]:
            raise HTTPException(409, "Choose at least one item")
        _p2_run(st, k, ctx)
        audit.log(db, user, f"p2.{k}", b.name)
    elif a in ("p2.assume", "p2.scope"):
        A = st["assume"]
        if a == "p2.scope":
            if val not in P2.SCOPES:
                raise HTTPException(400, "Unknown scope")
            A["scope"] = val
        else:
            try:
                n = max(0.0, float(val))
            except (TypeError, ValueError):
                raise HTTPException(400, "Enter a number")
            key = str(arg)
            if key.startswith("v:") and key[2:] in A["vol"][A["scope"]]:
                A["vol"][A["scope"]][key[2:]] = n
            elif key.startswith("h:") and key[2:] in A["hrs"]:
                A["hrs"][key[2:]] = n
            elif key == "scale":
                A["scale"][A["scope"]] = n
            elif key in ("rate", "escPer", "escH", "run", "costS", "costM", "costL"):
                A[key] = n
            else:
                raise HTTPException(400, "Unknown assumption")
        if st["R"]["road"]:
            st["R"]["road"] = P2.run_road(st, ctx)
        k = "road"
    elif a == "p2.approve":
        name = str(val or "").strip()
        if not st["R"]["road"]:
            raise HTTPException(409, "Build the roadmap first")
        if not name:
            raise HTTPException(400, "Enter the approver name")
        st["approved"] = {"by": name[:120], "at": W.now_txt(), "user": user.email}
        audit.log(db, user, "p2.approve", b.name, by=name)
    else:
        raise HTTPException(400, "Unknown action")
    W.ws_put(db, b.id, "p2", st, user)
    db.commit()
    return p2_view(db, b, ctx, k)


@router.get("/borrowers/{bid}/report/p2.docx")
def p2_docx(bid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    b = _b(db, bid)
    ctx = W.build_ctx(db, b)
    _need_memo(ctx)
    st = _p2(db, b, ctx)
    if not st["R"]["road"]:
        raise HTTPException(409, "Build the roadmap first")
    name = f"Data360 Phase 2 - {re.sub(r'[^\w &.-]', '', b.name).rstrip('.')} - Gaps, Confidence and Roadmap"
    return _file(to_docx(P2.blocks(st, b.name, ctx["ref_date"].isoformat()), name, header=f"Data360 · Phase 2 · {b.name}"), name + ".docx", DOCX)


# ================= Phase 3 =================
def p3_view(db, b, ctx, k) -> dict:
    p2, st = ctx.get("p2"), ctx.get("p3")
    if not st or not W.gates(ctx, p2, None)["p2"]:
        return {"available": False, "why": "Phase 3 unlocks when the Phase 2 roadmap is approved."}
    k = k if k in P3.STEP and P3.can(st, k) else next((s["k"] for s in reversed(P3.STEPS) if P3.can(st, s["k"])), "stab")
    S = P3.STEP[k]
    x = st["st"][k]
    idx = [s["k"] for s in P3.STEPS].index(k)
    nxt = P3.STEPS[idx + 1] if idx + 1 < len(P3.STEPS) else None
    I = [i for i in p2["R"]["road"]["I"] if S["hz"] in i["hz"]]
    recs = {r["id"]: r for r in p2["R"]["rec"]["R"]}
    init = (["Roadmap initiatives in this horizon: " + " · ".join(f"{i['name']} ({sum(1 for r in i['recs'] if P2.HORIZONS[P2.horizon_of(recs[r])][0] == S['hz'])} items)" for i in I)]
            if I else ["No roadmap initiatives start in this horizon."])
    out = {"available": True, "step": k, "nav": [{"k": s["k"], "n": s["n"], "t": s["t"], "can": P3.can(st, s["k"]), "done": bool(st["st"][s["k"]]["done"])} for s in P3.STEPS],
           "crumb": f"Step {S['n']} · {S['t']} · {S['m']}", "h1": S["h"], "track": P3.head_view(ctx, st), "init": init[0],
           "setup": _setup(P3.STD[k], P3.PICK[k], x["sel"], x["extra"], locked=bool(x["done"])),
           "scope": f"Uses the latest data for {b.name}: cleaned data pack v1.1, common definitions, the retained credit memo and the approved roadmap.",
           "verb": f"Run {S['t']} again" if x["R"] else f"Run {S['t']}", "done": x["done"], "sections": P3.results_view(ctx, st, k), "has_result": bool(x["R"])}
    if x["R"]:
        block = "" if x["done"] else P3.blocker(ctx, st, k)
        out["foot"] = {"hint": (f"{S['t']} completed {x['done']}." + (f" {nxt['t']} is unlocked in the stage bar above." if nxt else " Phase 3 cleared.")) if x["done"]
                       else block or f"Completing {S['t']} signs it off" + (f" and unlocks {nxt['t']}." if nxt else " and clears Phase 3."),
                       "block": block, "plan": bool(st["plans"].get(k))}
        if st["plans"].get(k):
            out["plan"] = PL.section(_plan(db, b, ctx, st, k))
    return out


def _fix(db, b, ctx, st=None):
    return FX.build(ctx["raw"], ctx["clean"], ctx.get("seek"), W.uploads_map(db, b), ctx["owners"], set((st or {}).get("resolved", [])), ctx["ref_date"])


def _plan(db, b, ctx, st, k):
    return PL.build(k, ctx, st, _fix(db, b, ctx, st))


def _p3_ctx(db, b):
    ctx = W.build_ctx(db, b)
    if ctx.get("memo_state"):
        p2, p3 = _p3(db, b, ctx)
        ctx["p3"] = p3
    return ctx


@router.get("/borrowers/{bid}/p3")
def p3_get(bid: int, step: str = "stab", db: Session = Depends(get_db), _: User = Depends(current_user)):
    b = _b(db, bid)
    ctx = _p3_ctx(db, b)
    v = p3_view(db, b, ctx, step)
    db.commit()
    return v


@router.post("/borrowers/{bid}/p3/action")
def p3_action(bid: int, body: Act, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    b = _b(db, bid)
    ctx = _p3_ctx(db, b)
    st = ctx.get("p3")
    if not st or not W.gates(ctx, ctx.get("p2"), None)["p2"]:
        raise HTTPException(409, "Phase 3 is locked until the Phase 2 roadmap is approved")
    k = body.step if body.step in P3.STEP else "stab"
    if not P3.can(st, k):
        raise HTTPException(409, "Complete the previous stage first")
    x = st["st"][k]
    a, arg, val = body.action, body.arg, body.value
    if x["done"] and a not in ("plan", "p3.q", "p3.thr", "owner"):
        raise HTTPException(409, "This stage is completed and signed off")
    ids = {i["id"] for i in P3.issues(ctx)}
    if a == "sel.toggle":
        if arg in P3.STD[k]:
            x["sel"] = [y for y in x["sel"] if y != arg] if arg in x["sel"] else [*x["sel"], arg]
    elif a == "extra.add":
        if arg in P3.PICK[k] and arg not in x["extra"]:
            x["extra"].append(arg)
    elif a == "extra.remove":
        x["extra"] = [y for y in x["extra"] if y != arg]
    elif a == "run":
        if not x["sel"] and not x["extra"]:
            raise HTTPException(409, "Choose at least one item")
        P3.run(st, k, ctx)
        audit.log(db, user, f"p3.{k}", b.name)
    elif a == "p3.resolve" and arg in ids:
        st["resolved"] = sorted(set(st["resolved"]) | {arg})
        audit.log(db, user, "p3.resolve", b.name, issue=arg)
    elif a == "p3.reopen":
        st["resolved"] = [i for i in st["resolved"] if i != arg]
    elif a == "p3.resolveAll":
        st["resolved"] = sorted(ids)
        audit.log(db, user, "p3.resolve", b.name, issue="all")
    elif a == "p3.certify":
        d = next((d for d in P3.datasets(ctx, st) if d["id"] == arg), None)
        if not d or d["status"] != "Ready":
            raise HTTPException(409, "Only a dataset with no blockers and every golden field held can be certified")
        st["certified"] = sorted(set(st["certified"]) | {arg})
        audit.log(db, user, "p3.certify", b.name, dataset=arg)
    elif a == "owner":
        o = W.owners(db)
        if val:
            o[str(arg)] = str(val)[:120]
        else:
            o.pop(str(arg), None)
        W.setting_put(db, "source_owners", o)
        ctx["owners"] = o
        audit.log(db, user, "owner.assign", str(arg), owner=val)
    elif a == "p3.thr":
        st["aiThr"] = max(60, min(95, int(float(val or 80))))
    elif a == "p3.q":
        st["q"] = str(val or "")[:120]
    elif a == "complete":
        if not x["R"]:
            raise HTTPException(409, "Run the stage first")
        block = P3.blocker(ctx, st, k)
        if block:
            raise HTTPException(409, block)
        x["done"] = W.now_txt()
        audit.log(db, user, f"p3.{k}.complete", b.name)
    elif a == "plan":
        st["plans"][k] = W.now_txt()
    else:
        raise HTTPException(400, "Unknown action")
    W.ws_put(db, b.id, "p3", st, user)
    db.commit()
    return p3_view(db, b, ctx, k)


@router.get("/borrowers/{bid}/report/p3.docx")
def p3_docx(bid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    b = _b(db, bid)
    ctx = _p3_ctx(db, b)
    if not ctx.get("p3") or not W.gates(ctx, ctx.get("p2"), None)["p2"]:
        raise HTTPException(409, "Phase 3 is locked")
    name = f"Data360 Phase 3 - {re.sub(r'[^\w &.-]', '', b.name).rstrip('.')} - Execution Status"
    return _file(to_docx(P3.blocks(ctx, ctx["p3"]), name, header=f"Data360 · Phase 3 · {b.name}"), name + ".docx", DOCX)


@router.get("/borrowers/{bid}/plan/{k}.xlsx")
def plan_xlsx(bid: int, k: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    b = _b(db, bid)
    ctx = _p3_ctx(db, b)
    if k not in P3.STEP or not ctx.get("p3") or not W.gates(ctx, ctx.get("p2"), None)["p2"]:
        raise HTTPException(409, "Phase 3 is locked")
    P = _plan(db, b, ctx, ctx["p3"], k)
    return _file(PL.xlsx(P), f"Data360 Project Plan - {P['n']} {P['t']} - {re.sub(r'[^\w &.-]', '', b.name).rstrip('.')}.xlsx", XLSX)


# ================= fix plan =================
@router.get("/borrowers/{bid}/fix")
def fix_get(bid: int, file: str | None = None, type: str = "all", db: Session = Depends(get_db), _: User = Depends(current_user)):
    b = _b(db, bid)
    ctx = W.build_ctx(db, b, need_memo=False)
    if not ctx.get("clean"):
        return {"available": False, "why": "The fix plan needs the Phase 1 Clean results. Run Source, Assess and Clean first; the plan is built from the "
                                         "cleaning audit trail, escalations, validation results and missing data."}
    p3 = W.ws_get(db, b.id, "p3")
    P = _fix(db, b, ctx, p3)
    if not P["files"]:
        return {"available": True, "empty": True, "c": b.name}
    return {"available": True, **FX.view(P, file, type if type in FX.TYPES or type == "all" else "all")}


@router.get("/borrowers/{bid}/fix.xlsx")
def fix_xlsx(bid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    b = _b(db, bid)
    ctx = W.build_ctx(db, b, need_memo=False)
    if not ctx.get("clean"):
        raise HTTPException(409, "Run Clean first")
    P = _fix(db, b, ctx, W.ws_get(db, b.id, "p3"))
    return _file(FX.xlsx(P), f"Data360 Fix Plan - {re.sub(r'[^\w &.-]', '', b.name).rstrip('.')}.xlsx", XLSX)
