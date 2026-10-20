"""Lookups the assistant can call. They run on the server, for the selected client only."""
from __future__ import annotations

import re

from ..engine import confidence as CF
from ..engine import fixplan as FX
from ..engine import memo as MM
from ..engine import phase3 as P3
from ..engine.policies import POLICY, TESTED
from ..engine.reference import LABEL, VALUE_FIELDS
from ..engine.values import is_blank, validate_element


def _trim(v, n=160):
    s = "" if v is None else str(v)
    return s if len(s) <= n else s[:n] + "…"


TOOLS = [
    {"name": "get_overview", "description": "Current state for the selected client: which steps have run, confidence by stage and criterion, open escalations, memo decision and status, which phases are cleared, active rules. Call first when unsure.",
     "schema": {"type": "object", "properties": {}}},
    {"name": "get_golden_record", "description": "The golden (agreed) value for each key field, with its source, record ID, as-of date and why that source was chosen.",
     "schema": {"type": "object", "properties": {}}},
    {"name": "search_external_records", "description": "External records (market data, ratings, registry, sanctions feed and other vendors) for the selected client, optionally filtered by source name and field names. Returns record ID, source, as-of date, provider quality flag and the fields.",
     "schema": {"type": "object", "properties": {"source": {"type": "string", "description": "Optional source name, e.g. Bloomberg"},
                                                 "fields": {"type": "array", "items": {"type": "string"}, "description": "Optional field keys, e.g. Facility_Amount, External_Rating, Sanctions_Screening"}}}},
    {"name": "search_internal_elements", "description": "Internal data-dictionary elements (loan systems, risk platforms, CRM, legal, treasury, documents) whose name, category or value contains the text. Personal data values are masked.",
     "schema": {"type": "object", "properties": {"text": {"type": "string", "description": "e.g. covenant, KYC, rating, guarantee"}, "source": {"type": "string"}}, "required": ["text"]}},
    {"name": "get_credit_memo", "description": "Credit memo results: draft decision and reason, every compliance check with result, rule ID and evidence, conditions precedent and subsequent, key ratios and risk ratings. Only after the memo has been built.",
     "schema": {"type": "object", "properties": {}}},
    {"name": "get_issues_and_fixes", "description": "Open data issues after cleaning (escalations with owner and due date) and the fix plan by uploaded file: open fixes per file and the top fixes.",
     "schema": {"type": "object", "properties": {}}},
    {"name": "get_rules", "description": "Rules and policies library: rule ID, title, requirement, regulatory or policy source, whether it is switched on and whether Data360 tests it. Optional text filter.",
     "schema": {"type": "object", "properties": {"text": {"type": "string"}}}},
    {"name": "get_phase2_and_3", "description": "Phase 2 results (gaps, recommendations, domain confidence, roadmap and business case) and Phase 3 stage status, if they have been run.",
     "schema": {"type": "object", "properties": {}}},
]


def run(name: str, args: dict, ctx: dict, extra: dict):
    """ctx: workspace.build_ctx result. extra: p2, p3, fix (callable), rules_on."""
    args = args or {}
    ds = ctx.get("ds") or ctx["raw"]
    if name == "get_overview":
        st = ctx["p1"]["status"]
        S = CF.stages(ctx.get("assess"), ctx.get("norm"))
        memo = ctx.get("memo_state")
        p2, p3 = extra.get("p2"), extra.get("p3")
        return {"client": ctx["borrower"], "data_as_at": ctx["ref_date"].isoformat(), "data_version": ds.version,
                "phase1_steps": {k: ("not run" if not v else "out of date: " + (v.get("stale_reason") or "") if v["stale"] else "done") for k, v in st.items()},
                "confidence": [{"stage": x["label"], "pct": x["pct"], "criteria": x["dims"]} for x in S] if S else "Run Source and Assess first",
                "open_escalations": len(ctx["clean"]["escalations"]) if ctx.get("clean") else None,
                "credit_memo": ({"stages_done": memo["done"], "draft_decision": ctx["M"]["decision"] if memo["done"] else None, "status": MM.status(memo),
                                 "retained": bool(memo.get("retained"))} if memo else "Not available until Source, Assess, Clean and Normalise are current"),
                "phase2": ("roadmap approved" if p2 and p2.get("approved") else "in progress" if p2 and any(p2["R"].values()) else "not started"),
                "phase3": ({s["t"]: ("completed" if p3["st"][s["k"]]["done"] else "run" if p3["st"][s["k"]]["R"] else "not run") for s in P3.STEPS} if p3 else "locked"),
                "active_rules": f"{len(extra.get('rules_on') or [])} of {len(POLICY)}"}
    if name == "get_golden_record":
        G = (ctx.get("clean") or {}).get("golden") or (ctx.get("assess") or {}).get("golden")
        if not G:
            return "No golden record yet: run Assess or Clean."
        return {LABEL.get(f, f): ({"value": g["display"], "source": g["source"], "record": g["record"], "as_of": g["as_of"], "why": g["why"]} if g else None) for f, g in G.items()}
    if name == "search_external_records":
        src = str(args.get("source") or "").lower()
        fs = [f for f in (args.get("fields") or []) if f in VALUE_FIELDS] or ["Facility_Amount", "Outstanding_Principal", "Maturity_Date", "External_Rating", "Revenue", "EBITDA", "Sanctions_Screening", "ESG_Score"]
        rows = [r for r in ds.records if not r.removed and (not src or src in r.source.lower())][:40]
        return {"field_keys": VALUE_FIELDS, "records": [{"id": r.rid, "source": r.source, "as_of": r.as_of.isoformat() if r.as_of else None, "flag": r.flag or None,
                                                         **{f: r.fields.get(f) for f in fs if not is_blank(r.fields.get(f))}} for r in rows]}
    if name == "search_internal_elements":
        q = str(args.get("text") or "").lower()
        src = str(args.get("source") or "").lower()
        out = []
        for e in ds.elements:
            if e.removed or (src and src not in e.source.lower()):
                continue
            if q and q not in " ".join([e.category or "", e.label or "", e.element, str(e.value or "")]).lower():
                continue
            personal = "personal" in (e.sensitivity or "").lower()
            out.append({"id": e.key.split(":", 1)[-1], "source": e.source, "element": e.element, "value": "[masked: personal data]" if personal else _trim(e.value),
                        "issue": validate_element(e.dtype, e.value) or None})
        return {"matches": len(out), "elements": out[:60]}
    if name == "get_credit_memo":
        memo = ctx.get("memo_state")
        if not memo or not memo["done"]:
            return "The credit memo has not been built yet (Phase 1, step 5)."
        M = ctx["M"]
        return {"decision": M["decision"], "why": M["decWhy"], "status": MM.status(memo), "version": MM.version(memo), "net_leverage": M["levTxt"], "ltv": M["ltvTxt"],
                "pricing_carry_bps": M["carry"], "checks": [{"rule": x["rule"], "area": x["area"], "check": x["check"], "result": x["result"], "hard": x["hard"], "evidence": _trim(x["evidence"], 220)} for x in M["CH"]],
                "switched_off": [x["check"] for x in M["CHoff"]], "conditions_precedent": M["CP"], "conditions_subsequent": M["CS"],
                "risk_ratings": [{"area": r["area"], "rag": r["rag"], "why": r["txt"]} for r in M["RAG"]],
                "covenants": [{"name": r["name"], "threshold": r["thrTxt"], "actual": r["actTxt"], "headroom": r["headTxt"], "status": r["status"]} for r in M["COV"]]}
    if name == "get_issues_and_fixes":
        if not ctx.get("clean"):
            return "Clean has not run yet."
        P = extra["fix"]()
        return {"escalations": [{"item": e["item"], "why": _trim(e["why"]), "owner": e["owner"], "due": e["due"]} for e in ctx["clean"]["escalations"]],
                "files": [{"file": f["name"], "open": len(f["open"]), "worst": f["worst"],
                           "top": [f"{x['field']}: {_trim(x['from'], 40)} → {_trim(x['to'], 50)} ({x['sev']}, {FX.TYPES[x['type']].lower()})" for x in f["open"][:4]]}
                          for f in (P["files"] if P else [])]}
    if name == "get_rules":
        q = str(args.get("text") or "").lower()
        on = set(extra.get("rules_on") or [])
        return [{"id": r["id"], "group": r["g"], "title": r["t"], "requirement": r["d"], "source": r["src"], "active": r["id"] in on, "tested": r["id"] in TESTED}
                for r in POLICY.values() if not q or q in " ".join([r["id"], r["t"], r["d"], r["src"], r["g"]]).lower()][:40]
    if name == "get_phase2_and_3":
        p2, p3 = extra.get("p2"), extra.get("p3")
        if not p2:
            return "Phase 2 is locked until the credit memo is retained."
        R = p2["R"]
        return {"gaps": [f"{g['id']} [{g['impact']}] {g['gap']}" for g in R["gap"]["G"]] if R["gap"] else "not run",
                "recommendations": [f"{r['id']} {r['quad']}: {r['t']}" for r in R["rec"]["R"]] if R["rec"] else "not run",
                "domain_confidence": [{"domain": d["d"], "overall": d["overall"], "rating": d["rate"], "scores": d["S"]} for d in R["conf"]["D"]] if R["conf"] else "not run",
                "roadmap": {"initiatives": [f"{i['name']} ({i['start']}-{i['end']} months)" for i in R["road"]["I"]], "investment_usd": R["road"]["invTot"],
                            "annual_net_benefit_usd": R["road"]["annual"], "payback_months": R["road"]["payback"], "approved": p2.get("approved"),
                            "note": "Business case uses editable, illustrative assumptions"} if R["road"] else "not run",
                "phase3": {s["t"]: ("completed" if p3["st"][s["k"]]["done"] else "run" if p3["st"][s["k"]]["R"] else "not run") for s in P3.STEPS} if p3 else "locked"}
    return f"Unknown tool {name}"


def safe_name(s: str) -> str:
    return re.sub(r"[^a-z_]", "", s.lower())
