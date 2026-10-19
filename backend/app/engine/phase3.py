"""Phase 3 · Transform: 10 Stabilise, 11 Standardise, 12 Optimise, 13 Transform, with the issue
register, trusted datasets, confidence tracking, early-warning score and dated alerts (ported from
the demo). Each stage is run, reviewed and signed off; signing off unlocks the next stage."""
from __future__ import annotations

import math
import re
from datetime import date, timedelta

from . import memo as MM
from . import ui
from .phase2 import HORIZONS, horizon_of, usd
from .reference import LABEL
from .registry import OWNER_CHOICES, meta
from .values import fmt, is_blank, validate_element

STD = {
    "stab": {"Data inventory": "Every internal and external source with volumes, refresh and sensitivity.",
             "Ownership register": "An owner and steward for every source; assign the missing ones.",
             "Critical issue resolution": "Open escalations and hard policy failures, worked to closure.",
             "Executive confidence baseline": "Confidence by domain, frozen as the baseline to measure against."},
    "std": {"Trusted datasets": "Golden datasets built from the cleaned pack and certified for use.",
            "Consistent reporting and KPIs": "One KPI catalogue and report set on certified definitions.",
            "Reduced manual effort": "Memo fields moved from manual entry to certified feeds."},
    "opt": {"Automated reporting": "Scheduled reports, with a data quality scorecard generated now.",
            "Advanced analytics": "Source error rates, financial trend and exposure analytics.",
            "Visibility": "A control tower of confidence, issues, datasets and KPIs.",
            "Cross-functional decision support": "What each function decides and the data behind it."},
    "trans": {"AI-assisted drafting": "Which memo fields AI can draft at a chosen confidence threshold.",
              "Predictive analytics": "An early-warning score with the signals that drive it.",
              "Continuous optimisation": "Drift against the baseline and the improvement cadence.",
              "Proactive decisions": "Dated alerts with the action to take before each event."},
}
PICK = {"stab": {"Quick-win tracker": "Roadmap items due in 0–3 months.", "Data council charter": "Members, decision rights and cadence."},
        "std": {"Definitions certification": "Common definitions v1.0 certified as v1.1.", "Data contracts": "Quality and timeliness terms with each provider."},
        "opt": {"Portfolio benchmark": "Data quality and risk across all borrowers.", "Self-service search": "Find any business term, its field and golden source."},
        "trans": {"Portfolio early warning": "Early-warning score for all borrowers.", "Model governance": "Model card: inputs, limits, validation and owner."}}
STEPS = [{"k": "stab", "n": "10", "t": "Stabilise", "m": "0–3 months", "h": "Stabilise: build the foundation", "hz": "Stabilise"},
         {"k": "std", "n": "11", "t": "Standardise", "m": "3–6 months", "h": "Standardise: trusted datasets and consistent reporting", "hz": "Standardise"},
         {"k": "opt", "n": "12", "t": "Optimise", "m": "6–12 months", "h": "Optimise: automation, analytics and visibility", "hz": "Optimise"},
         {"k": "trans", "n": "13", "t": "Transform", "m": "12+ months", "h": "Transform: AI, prediction and proactive decisions", "hz": "Transform"}]
STEP = {s["k"]: s for s in STEPS}
DATASETS = [["DS-01", "Obligor golden record", ["Borrower_Name", "Registration_Number", "Country", "Industry", "Beneficial_Owner", "Registry_Status"], r"registration|borrower|legal entity|lei|tax id|country|industry|owner"],
            ["DS-02", "Facility master", ["Facility_Amount", "Outstanding_Principal", "Maturity_Date"], r"facility|outstanding|maturity"],
            ["DS-03", "Financials", ["Revenue", "EBITDA"], r"revenue|ebitda|financial|capital iq|bureau"],
            ["DS-04", "Ratings and risk", ["External_Rating"], r"rating|moody"],
            ["DS-05", "Compliance screening", ["Sanctions_Screening"], r"sanction|kyc|aml"],
            ["DS-06", "ESG", ["ESG_Score"], r"esg|country risk"]]


def new_state() -> dict:
    return {"st": {s["k"]: {"sel": list(STD[s["k"]]), "extra": [], "R": None, "done": None} for s in STEPS},
            "resolved": [], "certified": [], "aiThr": 80, "baseline": None, "q": "", "plans": {}, "stamp": None}


def can(st, k) -> bool:
    i = [s["k"] for s in STEPS].index(k)
    return i == 0 or bool(st["st"][STEPS[i - 1]["k"]]["done"])


def bdays(start: date, n: int) -> date:
    d, k = start, 0
    while k < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            k += 1
    return d


# ---------------- shared views of the data ----------------
def sources(ctx):
    full, owners, cl = ctx["ds_full"], ctx.get("owners") or {}, ctx["clean"]
    by_action = {}
    for l in cl["log"]:
        by_action.setdefault(l["action"], set()).add(l["record"])
    internal = []
    for s in sorted({e.source for e in full.elements}):
        rows = [e for e in full.elements if e.source == s]
        sens = {}
        for e in rows:
            t = (e.sensitivity or "Internal").split(" – ")[0]
            sens[t] = sens.get(t, 0) + 1
        m = meta(s, "Internal", owners)
        internal.append({"key": s, "name": s, "kind": "Internal", "n": len(rows), "valid": sum(1 for e in rows if not validate_element(e.dtype, e.value)),
                         "refresh": m["cycle"], "method": m["method"], "owner": m["owner"], "steward": m["steward"], "sens": sens})
    external = []
    cleaned = ctx["ds"]
    for s in sorted({r.source for r in cleaned.records}):
        recs = [r for r in cleaned.records if r.source == s]
        m = meta(s, "External", owners)
        rids = {r.rid for r in recs}
        external.append({"key": s, "name": s, "kind": "External", "n": len(recs), "kept": sum(1 for r in recs if not r.removed),
                         "validated": sum(1 for r in recs if not r.removed and (r.status or r.flag in ("", "VALIDATED"))),
                         "wrong": len(rids & by_action.get("Correct errors", set())), "incon": len(rids & by_action.get("Reconcile conflicting records", set())),
                         "stale": sum(1 for r in recs if cleaned.is_stale(r)), "incomplete": sum(1 for r in recs if r.flag == "INCOMPLETE"),
                         "refresh": m["cycle"], "method": m["method"], "owner": m["owner"], "steward": m["steward"]})
    return {"int": internal, "ext": external}


def issues(ctx):
    M, cl = ctx["M"], ctx["clean"]
    out = []
    for i, e in enumerate(cl["escalations"]):
        sev = "Critical" if re.search("sanction", e["item"], re.I) else "High" if re.search("registration|facility amount|outstanding|maturity", e["item"], re.I) else "Medium"
        out.append({"id": f"ISS-{i + 1:02d}", "t": e["item"], "why": e["why"], "owner": e["owner"], "due": e["due"], "sev": sev, "src": "Clean escalation"})
    hard = [x for x in M["CH"] if x["result"] == "Fail" and x["hard"]]
    for i, x in enumerate(hard):
        out.append({"id": f"POL-{i + 1:02d}", "t": x["check"], "why": x["evidence"],
                    "owner": "Financial Crime Compliance" if x["area"] in ("Sanctions", "KYC & AML") else "Legal" if x["area"] == "Legal" else "Credit Risk Management",
                    "due": bdays(ctx["ref_date"], 10).isoformat(), "sev": "Critical", "src": "Credit memo hard failure"})
    return out


def datasets(ctx, st):
    G = ctx["clean"]["golden"]
    open_ = [i for i in issues(ctx) if i["id"] not in st["resolved"]]
    out = []
    for id_, name, fields, rx in DATASETS:
        vals = [[LABEL.get(f, f), G[f]["display"] if G.get(f) else "Not held", f"{G[f]['source']} ({G[f]['record']})" if G.get(f) else "—"] for f in fields]
        block = [i for i in open_ if re.search(rx, i["t"], re.I) or re.search(rx, i["why"], re.I)]
        held = sum(1 for v in vals if v[1] != "Not held")
        status = "Certified" if id_ in st["certified"] else "Blocked" if block else "Incomplete" if held < len(fields) else "Ready"
        out.append({"id": id_, "name": name, "fields": fields, "vals": vals, "held": held, "block": [b["id"] for b in block], "status": status})
    return out


def confidence(ctx, st):
    p2 = ctx["p2"]
    D, T = p2["R"]["conf"]["D"], p2["R"]["road"]["target"]
    base = round(sum(d["overall"] for d in D) / len(D)) if D else 0
    tgt = round(sum(t["to"] for t in T) / len(T)) if T else 0
    I = issues(ctx)
    crit = sum(1 for i in I if i["id"] in st["resolved"]) / len(I) if I else 0
    cert = len(st["certified"]) / len(DATASETS)
    g = 0.4 * crit + 0.3 * cert + (0.2 if st["st"]["opt"]["done"] else 0) + (0.1 if st["st"]["trans"]["done"] else 0)
    by = []
    for d in D:
        t = next((x for x in T if x["d"] == d["d"]), {"to": d["overall"]})
        by.append({"d": d["d"], "base": d["overall"], "now": round(d["overall"] + (t["to"] - d["overall"]) * g), "to": t["to"]})
    return {"base": base, "tgt": tgt, "now": round(base + (tgt - base) * g), "g": g, "byDom": by}


def _num(s):
    m = re.search(r"-?\d+(\.\d+)?", str(s or "").replace(",", ""))
    return float(m.group(0)) if m else None


def early_warning(ds_full, M=None):
    els = [e for e in ds_full.elements if not validate_element(e.dtype, e.value)]

    def ints(el):
        el = el.lower()
        return [str(e.value) for e in els if e.element.strip().lower() == el]
    ob = ints("Obligor rating")
    obl = _num(ob[0]) if ob else None
    ecl3 = any("3" in v for v in ints("ECL stage"))
    dpd = max([0] + [_num(v) or 0 for v in ints("Days past due")])
    dist = sum(1 for v in ints("Distress indicator") if re.search("missed|default|layoff", v, re.I))
    sent = [x for x in (_num(v) for v in ints("Sentiment score")) if x is not None]
    s_avg = sum(sent) / len(sent) if sent else 0
    restr = any(v.startswith("Y") for v in ints("Restructuring flag"))
    ch11 = len(ints("Proceeding type"))
    ews = ints("Covenant breached")
    pm = sum(1 for v in ints("Screening result") if re.search("potential|match", v, re.I) and not re.search("no match", v, re.I))
    F = [["Internal rating weaker than grade 6", 0.9 if obl is not None and obl >= 7 else 0.4 if obl is not None and obl >= 6 else 0, "not held" if obl is None else f"grade {ob[0]}"],
         ["Credit-impaired (IFRS 9 stage 3)", 1.1 if ecl3 else 0, ", ".join(ints("ECL stage")) or "not held"],
         ["Days past due", 1.5 if dpd >= 90 else 0.6 if dpd > 0 else 0, f"{dpd:g} days"],
         ["Restructuring or insolvency proceeding", (0.6 if restr else 0) + (0.8 if ch11 else 0), ", ".join(x for x in ["restructured" if restr else None, "Chapter 11 / proceeding" if ch11 else None] if x) or "none"],
         ["Adverse news", min(0.9, dist * 0.2) + (0.3 if s_avg < -0.5 else 0), f"{dist} distress items, sentiment {s_avg:.2f}"],
         ["Early-warning covenant alert", 0.5 if ews else 0, ", ".join(ews) if ews else "none"],
         ["Sanctions potential match", 0.3 if pm else 0, f"{pm} open" if pm else "none"]]
    if M and M.get("carry") is not None:
        F.append(["Pricing below cost of funds", 0.2 if M["carry"] < 0 else 0, f"{M['carry']} bps carry"])
    z = -3 + sum(f[1] for f in F)
    p = 1 / (1 + math.exp(-z))
    return {"F": F, "p": p, "score": round(p * 100), "band": "Red" if p >= 0.5 else "Amber" if p >= 0.2 else "Green"}


def alerts(ctx):
    M, ref = ctx["M"], ctx["ref_date"]
    els = [e for e in ctx["ds_full"].elements if not validate_element(e.dtype, e.value)]

    def ints(el):
        el = el.lower()
        return [str(e.value) for e in els if e.element.strip().lower() == el]
    A = []

    def add(d, t, act, owner):
        if not re.match(r"^\d{4}-\d{2}-\d{2}", d or ""):
            return
        d = d[:10]
        try:
            dd = date.fromisoformat(d)
        except ValueError:
            return
        A.append({"date": d, "d": (dd - ref).days, "t": t, "act": act, "owner": owner})
    for v in ints("Standstill period"):
        add((v.split(" to ")[1] if " to " in v else "").strip(), f"Standstill ends ({v})", "Agree extension or restructuring terms with lenders before expiry", "Credit Risk Management")
    for v in ints("Next KYC review date"):
        add(v, "KYC periodic review due", "Start refresh 60 days ahead", "KYC Operations")
    for v in ints("Guarantee expiry"):
        add(v, "Guarantee expires", "Renew or replace the guarantee before expiry", "Loan operations")
    for v in ints("Availability period end"):
        add(v, "Availability period ends", "Confirm undrawn commitment is cancelled or extended", "Relationship manager")
    for v in ints("License expiry"):
        add(v, "Licence expires", "Obtain renewed licence copy", "Legal")
    mat = M["F"].get("4|Maturity Date", {}).get("v")
    if mat:
        add(mat, "Facility matures", "Open refinancing discussion 12 months before maturity", "Relationship manager")
    for v in sorted(ints("Valuation date"))[-1:]:
        try:
            nx = date.fromisoformat(v[:10])
            add(nx.replace(year=nx.year + 1).isoformat(), "Annual revaluation due", "Order a full (not desktop) valuation", "Credit Risk Management")
        except ValueError:
            pass
    for r in M["COV"]:
        if r["status"] in ("Conflict", "Breach"):
            add((ref + timedelta(days=14)).isoformat(), f"{r['name']} covenant {r['status'].lower()}", "Confirm the test result with the borrower's compliance certificate", "Credit Risk Management")
    return sorted(A, key=lambda a: a["date"])


def run(st, k, ctx):
    R = {"on": st["st"][k]["sel"] + st["st"][k]["extra"]}
    if k == "stab" and not st.get("baseline"):
        C = confidence(ctx, st)
        st["baseline"] = {"at": ctx["ref_date"].isoformat(), **C, "p1": ctx["M"]["last"].get("pct")}
    if k == "trans":
        R["ew"] = early_warning(ctx["ds_full"], ctx["M"])
        if "Portfolio early warning" in R["on"] and ctx.get("portfolio"):
            R["port"] = [{"b": name, **early_warning(ds)} for name, ds in ctx["portfolio"]()]
    if k == "opt" and "Portfolio benchmark" in R["on"] and ctx.get("portfolio"):
        bench = []
        for name, ds in ctx["portfolio"]():
            recs = ds.records
            bench.append({"b": name, "n": len(recs), "ok": sum(1 for r in recs if r.flag in ("", "VALIDATED")), "wrong": sum(1 for r in recs if r.flag == "WRONG"),
                          "stale": sum(1 for r in recs if ds.is_stale(r)), "pm": sum(1 for r in recs if re.search("potential", str(r.fields.get("Sanctions_Screening", "")), re.I)),
                          "ew": early_warning(ds)})
        R["bench"] = bench
    st["st"][k]["R"] = R


# ---------------- views ----------------
def head_view(ctx, st):
    C, I = confidence(ctx, st), issues(ctx)
    r = sum(1 for i in I if i["id"] in st["resolved"])
    cl = ctx["clean"]
    return {"type": "ptrack", "items": [
        {"label": "Confidence", "value": f"{C['now']}%", "sub": f"baseline {C['base']}% · target {C['tgt']}%", "pct": C["now"]},
        {"label": "Critical and open issues resolved", "value": f"{r} of {len(I)}", "pct": r / len(I) * 100 if I else 0},
        {"label": "Datasets certified", "value": f"{len(st['certified'])} of {len(DATASETS)}", "pct": len(st["certified"]) / len(DATASETS) * 100},
        {"label": "Data in use", "value": "Cleaned pack v1.1 · definitions " + ("v1.1 certified" if st["st"]["std"]["done"] else "v1.0"), "small": True,
         "sub": f"{cl['kept']} of {cl['total']} external records kept · {ctx['borrower']}"}]}


def results_view(ctx, st, k) -> list[dict]:
    R = st["st"][k]["R"]
    if not R:
        return []
    on = set(R["on"])
    M, out = ctx["M"], []
    done = bool(st["st"][k]["done"])
    owners = ctx.get("owners") or {}
    sec = ui.section
    if k == "stab":
        S = sources(ctx)
        allv = S["int"] + S["ext"]
        if "Data inventory" in on:
            rows = [[ui.bold(x["name"]), ui.hint("Internal"), f"{x['n']} elements", ui.bar(x["valid"] / x["n"] * 100 if x["n"] else 0, "", f"{x['valid']} usable"), ui.hint(x["refresh"]),
                     ui.hint(x["method"]), ui.hint(", ".join(f"{t} {n}" for t, n in sorted(x["sens"].items(), key=lambda y: -y[1])[:2]))] for x in S["int"]]
            rows += [[ui.bold(x["name"]), ui.hint("External"), f"{x['n']} records", ui.bar(x["validated"] / x["n"] * 100 if x["n"] else 0, "", f"{x['validated']} validated after Clean"),
                      ui.hint(x["refresh"]), ui.hint(x["method"]), ui.hint("Licensed")] for x in S["ext"]]
            out.append(sec("Data inventory", f"{len(S['int'])} internal systems · {len(S['ext'])} external feeds",
                           [ui.table(["Source", "Type", "Volume", "Quality", "Refresh", "Method", "Sensitivity"], rows, num=[2])]))
        if "Ownership register" in on:
            miss = [x for x in allv if not x["owner"]]
            rows = []
            for x in allv:
                assigned = owners.get(x["key"])
                cell = x["owner"] if x["owner"] and not assigned else ui.select("owner", x["key"], OWNER_CHOICES, assigned or "", "Assign owner…", disabled=done)
                rows.append([ui.bold(x["name"], x["kind"]), cell, ui.hint(x["steward"] or "To be named"), ui.chip("ok", "Owned") if x["owner"] else ui.chip("bad", "No owner")])
            out.append(sec("Ownership register", f"{len(allv) - len(miss)} of {len(allv)} sources owned", [ui.table(["Source", "Owner", "Steward", "Status"], rows)]))
        if "Critical issue resolution" in on:
            I = issues(ctx)
            open_ = [i for i in I if i["id"] not in st["resolved"]]
            crit = sum(1 for i in open_ if i["sev"] == "Critical")
            rows, cls = [], []
            for i in I:
                r = i["id"] in st["resolved"]
                cls.append("done" if r else "")
                status = [ui.chip("ok", "Resolved")] + ([] if done else [ui.btn("Reopen", "p3.reopen", i["id"])]) if r else [ui.btn("Mark resolved", "p3.resolve", i["id"])]
                rows.append([ui.mono(i["id"]), ui.bold(i["t"], f"{i['why']} · {i['src']}"), ui.chip("bad" if i["sev"] == "Critical" else "warn" if i["sev"] == "High" else "idle", i["sev"]),
                             ui.hint(i["owner"]), ui.mono(i["due"]), {"t": "group", "items": status}])
            out.append(sec("Critical issue resolution", f"{len(I) - len(open_)} of {len(I)} resolved · {crit} critical open",
                           [ui.table(["ID", "Issue", "Severity", "Owner", "Due", "Status"], rows, row_class=cls)],
                           foot={"hint": "\"Mark resolved\" records that the owner closed the issue. Resolving issues raises confidence and unblocks datasets in Standardise.",
                                 "buttons": [ui.btn("Resolve all", "p3.resolveAll", None, confirm="Mark every open issue resolved?")] if open_ and not done else []}))
        if "Executive confidence baseline" in on and st.get("baseline"):
            B = st["baseline"]
            C = confidence(ctx, st)
            out.append(sec("Executive confidence baseline", f"Frozen {B['at']}",
                           [ui.headline(f"Baseline **{B['base']}%** across {len(B['byDom'])} domains (Phase 1 overall {B['p1']}%). Roadmap target **{B['tgt']}%**."),
                            ui.table(["Domain", "Baseline", "Now", "Target", "Progress"],
                                     [[ui.bold(d["d"]), f"{d['base']}%", ui.bold(f"{d['now']}%"), f"{d['to']}%", ui.uplift(d["base"], d["now"], "ph3")] for d in C["byDom"]], num=[1, 2, 3])]))
        if "Quick-win tracker" in on:
            recs = {r["id"]: r for r in ctx["p2"]["R"]["rec"]["R"]}
            rows = [[ui.mono(rid), recs[rid]["t"], i["name"], recs[rid]["owner"], ui.mono((ctx["ref_date"] + timedelta(days=90)).isoformat())]
                    for i in ctx["p2"]["R"]["road"]["I"] if "Stabilise" in i["hz"] for rid in i["recs"] if horizon_of(recs[rid]) == 0]
            out.append(sec("Quick-win tracker", f"{len(rows)} items due in 0–3 months", [ui.table(["ID", "Item", "Initiative", "Owner", "Due"], rows)]))
        if "Data council charter" in on:
            out.append(sec("Data council charter", "Draft", [ui.table(["Item", "Detail"], [["Chair", "Chief Data Officer"], ["Members", "Credit Risk Management, KYC Operations, Financial Crime Compliance, Market Data Services, Technology, Data Governance Office"],
                                                                                           ["Decision rights", "Certify definitions and datasets; assign owners; approve data quality thresholds; prioritise the roadmap"],
                                                                                           ["Cadence", "Monthly; ad hoc for critical issues"], ["Inputs", "Confidence baseline, issue register, KPI scorecard"]])]))
    if k == "std":
        DS = datasets(ctx, st)
        if "Trusted datasets" in on:
            cards = []
            for d in DS:
                tone = "high" if d["status"] == "Certified" else "med" if d["status"] == "Ready" else "low"
                b = None
                if d["status"] != "Certified":
                    b = ui.btn("Resolve blockers in Stabilise" if d["status"] == "Blocked" else "Missing golden fields" if d["status"] == "Incomplete" else "Certify dataset",
                               "p3.certify", d["id"], disabled=not (d["status"] == "Ready" and not done))
                cards.append({"title": d["name"], "rate": tone, "chip": ["ok" if d["status"] == "Certified" else "info" if d["status"] == "Ready" else "bad", d["status"]],
                              "hint": f"{d['id']} · {d['held']} of {len(d['fields'])} golden fields held" + (f" · blocked by {', '.join(d['block'])}" if d["block"] else ""),
                              "details": {"label": "Contents", "head": ["Field", "Golden value", "Source"], "rows": d["vals"]}, "btn": b})
            out.append(sec("Trusted datasets", f"{sum(1 for d in DS if d['status'] == 'Certified')} of {len(DS)} certified", [{"type": "cards", "items": cards}]))
        if "Consistent reporting and KPIs" in on:
            K = (ctx["norm"] or {}).get("out", {}).get("KPIs", {}).get("rows", [])
            out.append(sec("Consistent reporting and KPIs", f"{len(K)} KPIs · 4 standard reports", [
                ui.table(["KPI", "Definition", "Owner", "Frequency", "Current", "Status"], [[ui.bold(r[0]), ui.hint(r[1]), ui.hint(r[3]), ui.hint(r[4]), ui.mono(r[5]), ui.chip(*ui.RAGC[r[6]])] for r in K]),
                ui.h3("Standard report set"),
                ui.table(["Report", "Frequency", "Audience", "Built from"], [["Credit memo pack", "On demand", "Credit Committee", "DS-01 to DS-06"], ["Data quality scorecard", "Weekly", "Data council", "Cleaned data pack, issue register"],
                                                                             ["Escalation report", "Daily", "Data owners", "Issue register"], ["Portfolio KPI pack", "Monthly", "CRO, Head of Credit", "KPI catalogue, DS-02, DS-04"]], flat=False)]))
        if "Reduced manual effort" in on:
            ST = ctx["ST"]
            cert_secs = {"DS-01": ["2"], "DS-02": ["4"], "DS-03": ["5"], "DS-04": ["6"], "DS-05": ["12"], "DS-06": ["13"]}
            fs = MM.fields_in(M, ["0", *MM.selected(ctx["memo_state"])])
            freed = sum(1 for f in fs if f["kind"] in ("manual", "missing") and f["sec"] != "1" and any(i in st["certified"] and f["sec"] in ss for i, ss in cert_secs.items()))
            RD = ctx["p2"]["R"]["road"]
            auto_after = round((ST["auto"] + freed) / ST["total"] * 100) if ST["total"] else 0
            h_std = round(RD["hNow"] * (1 - RD["autoShare"] * (0.3 + 0.4 * len(st["certified"]) / len(DATASETS))) * 10) / 10
            out.append(sec("Reduced manual effort", "Memo fields and hours", [
                ui.kpis([(f"{ST['pctAuto']}% → {auto_after}%", "Memo fields filled automatically"), (freed, "Fields moved to certified feeds"),
                         (f"{RD['hNow']} → {h_std} h", "Average hours per memo"), (f"{round((RD['hNow'] - h_std) * RD['V']['n']):,} h", f"Hours saved a year ({RD['V']['n']} memos)")]),
                ui.hint_block("Fields count as freed only when the dataset that would supply them is certified. Certify more datasets to move more fields.")]))
        if "Definitions certification" in on:
            out.append(sec("Definitions certification", "v1.0 → v1.1", [ui.table(["Definition set", "Items", "Status"],
                                                                               [[k2, str(o["n"]), "Certified v1.1" if done else "Certified v1.1 on completing Standardise"] for k2, o in (ctx["norm"] or {}).get("out", {}).items()])]))
        if "Data contracts" in on:
            S = sources(ctx)
            out.append(sec("Data contracts", f"{len(S['ext'])} providers", [ui.table(["Provider", "Timeliness term", "Quality term", "Error rate today"],
                                                                                       [[x["name"], "By 07:00 each business day" if x["refresh"] == "Daily" else f"Within 5 days of {x['refresh'].lower()} cycle",
                                                                                         "Wrong or inconsistent records < 2%", f"{round((x['wrong'] + x['incon']) / x['n'] * 100)}%" if x["n"] else "—"] for x in S["ext"]])]))
    if k == "opt":
        S, C, I = sources(ctx), confidence(ctx, st), issues(ctx)
        open_ = [i for i in I if i["id"] not in st["resolved"]]
        K = (ctx["norm"] or {}).get("out", {}).get("KPIs", {}).get("rows", [])
        ref = ctx["ref_date"]
        if "Automated reporting" in on:
            out.append(sec("Automated reporting", "4 reports scheduled", [
                ui.table(["Report", "Schedule", "Next run", "Delivered to"], [["Escalation report", "Daily 07:30", (ref + timedelta(days=1)).isoformat(), "Data owners"],
                                                                              ["Data quality scorecard", "Mondays 08:00", (ref + timedelta(days=3)).isoformat(), "Data council"],
                                                                              ["Portfolio KPI pack", "1st business day monthly", (ref + timedelta(days=23)).isoformat(), "CRO, Head of Credit"],
                                                                              ["Credit memo pack", "On memo request", "On demand", "Credit Committee"]]),
                ui.h3("Data quality scorecard · generated now from the cleaned pack"),
                ui.table(["Feed", "Records", "Validated", "Corrected", "Reconciled", "Stale", "Owner"],
                         [[ui.bold(x["name"]), x["n"], x["validated"], x["wrong"], x["incon"], x["stale"], ui.hint(x["owner"] or "No owner")] for x in S["ext"]], num=[1, 2, 3, 4, 5], flat=False)]))
        if "Advanced analytics" in on:
            ext = sorted([{**x, "err": round((x["wrong"] + x["incon"] + x["stale"]) / x["n"] * 100) if x["n"] else 0} for x in S["ext"]], key=lambda x: -x["err"])
            out.append(sec("Advanced analytics", "On the cleaned and normalised data", [
                ui.h3("Source error rate before cleaning"),
                {"type": "bars", "items": [{"label": x["name"], "pct": x["err"] * 2, "tone": "bad" if x["err"] >= 30 else "warn" if x["err"] >= 15 else "ok", "value": f"{x['err']}%"} for x in ext]},
                ui.hint_block("Records corrected, reconciled or stale as a share of each feed. Bars are scaled ×2 for readability."),
                ui.h3("Financial trend (golden record)"),
                ui.table(["Metric", *[("Current" if i == len(M["mLabels"]) - 1 else m) for i, m in enumerate(M["mLabels"])], "Trend"], [[r[0], *r[1], r[2]] for r in M["finRows"]],
                         num=list(range(1, len(M["mLabels"]) + 1)), flat=False),
                ui.h3("Covenant headroom"),
                {"type": "bars", "items": [{"label": r["name"], "pct": r["head"] * 100, "tone": "bad" if r["head"] < 0.1 else "warn" if r["head"] < 0.25 else "ok", "value": r["headTxt"]}
                                           for r in M["COV"] if r["head"] is not None]}]))
        if "Visibility" in on:
            owned = sum(1 for x in S["ext"] + S["int"] if x["owner"])
            blocks = [ui.kpis([(f"{C['now']}%", f"Confidence (target {C['tgt']}%)"), (len(open_), f"Open issues ({sum(1 for i in open_ if i['sev'] == 'Critical')} critical)"),
                               (f"{len(st['certified'])}/{len(DATASETS)}", "Datasets certified"),
                               (f"{sum(1 for r in K if r[6] == 'g')}·{sum(1 for r in K if r[6] == 'a')}·{sum(1 for r in K if r[6] == 'r')}", "KPIs green · amber · red"),
                               (f"{owned}/{len(S['ext']) + len(S['int'])}", "Sources owned")], five=True)]
            if open_:
                blocks += [ui.h3("Open issues by due date"), ui.table(["ID", "Issue", "Severity", "Owner", "Due", "Days"],
                                                                      [[ui.mono(i["id"]), i["t"], i["sev"], i["owner"], ui.mono(i["due"]), (date.fromisoformat(i["due"]) - ref).days]
                                                                       for i in sorted(open_, key=lambda i: i["due"])], num=[5], flat=False)]
            else:
                blocks.append(ui.hint_block("No open issues."))
            out.append(sec("Visibility", "Control tower", blocks))
        if "Cross-functional decision support" in on:
            ew = early_warning(ctx["ds_full"], M)
            dom = {d["d"]: d["now"] for d in C["byDom"]}
            fac_fail = sum(1 for f in M["critFail"] if f in ("Facility_Amount", "Outstanding_Principal", "Maturity_Date"))
            out.append(sec("Cross-functional decision support", "Decisions and the data behind them", [ui.table(["Function", "Decision", "Data used", "Confidence"], [
                ["Credit", f"Memo decision: {M['decision']}", "DS-01 to DS-06, compliance checks", f"{dom.get('Financials', '—')}%"],
                ["Risk", f"Rating {M['F']['6|Internal Rating']['v']}; early warning {ew['band']} ({ew['score']}%)", "DS-04, Risk platforms, news", f"{dom.get('Ratings & risk', '—')}%"],
                ["Compliance", f"Sanctions and KYC: {sum(1 for x in M['CH'] if x['area'] in ('Sanctions', 'KYC & AML') and x['result'] == 'Fail')} failed checks", "DS-05, Legal, CRM", f"{dom.get('Compliance', '—')}%"],
                ["Treasury", M["F"]["10|Treasury Assessment"]["v"], "Treasury systems, Bloomberg", "—"],
                ["Operations", f"Reconcile facility terms ({fac_fail} fields differ)", "DS-02, Loan systems", f"{dom.get('Facility', '—')}%"]])]))
        if "Portfolio benchmark" in on and R.get("bench"):
            rows = [[ui.bold(b["b"]), b["n"], ui.bar(b["ok"] / b["n"] * 100 if b["n"] else 0, "", f"{round(b['ok'] / b['n'] * 100) if b['n'] else 0}%"), b["wrong"], b["stale"], b["pm"],
                     {"t": "group", "items": [ui.chip(*ui.RAGC["r" if b["ew"]["band"] == "Red" else "a" if b["ew"]["band"] == "Amber" else "g"]), ui.hint(f"{b['ew']['score']}%")]}] for b in R["bench"]]
            out.append(sec("Portfolio benchmark", f"{len(R['bench'])} borrowers", [ui.table(["Borrower", "Records", "Validated", "Flagged wrong", "Stale", "Sanctions potential", "Early warning"], rows, num=[1, 3, 4, 5],
                                                                                           row_class=["tot" if b["b"] == ctx["borrower"] else "" for b in R["bench"]])]))
        if "Self-service search" in on:
            T = (ctx["norm"] or {}).get("out", {}).get("Semantic layer", {})
            q = (st.get("q") or "").strip().lower()
            hits = [r for r in T.get("rows", []) if not q or q in " ".join(map(str, r)).lower()]
            out.append(sec("Self-service search", "Semantic layer", [{"type": "search", "action": "p3.q", "value": st.get("q") or "", "placeholder": "Try: UEN, debt/EBITDA, UBO, drawn"},
                                                                     ui.table(T.get("head", ["Business term"]), hits) if hits else ui.hint_block("No matching term.")]))
    if k == "trans":
        if "AI-assisted drafting" in on:
            out.append(sec("AI-assisted drafting", "Confidence threshold", [{"type": "range", "action": "p3.thr", "label": "Minimum confidence for AI to draft a field", "min": 60, "max": 95, "step": 5, "value": st["aiThr"]},
                                                                             *ai_blocks(ctx, st)]))
        if "Predictive analytics" in on:
            E = R["ew"]
            out.append(sec("Predictive analytics", f"Early-warning score for {ctx['borrower']}", [
                {"type": "decision", "tone": "bad" if E["band"] == "Red" else "" if E["band"] == "Amber" else "ok", "label": "Probability of downgrade or default in 12 months (illustrative model)", "value": f"{E['score']}% · {E['band']}"},
                ui.h3("What drives the score"),
                {"type": "bars", "items": [{"label": f[0], "sub": f[2], "pct": f[1] / 1.5 * 100, "tone": "bad" if f[1] >= 0.8 else "warn" if f[1] > 0 else "ok", "value": f"+{f[1]:.1f}" if f[1] else "0"} for f in E["F"]]},
                ui.hint_block("Weights are set by hand, not fitted to default history. A production model needs calibration and independent validation.")]))
        if "Continuous optimisation" in on:
            B, C = st.get("baseline") or confidence(ctx, st), confidence(ctx, st)
            I = issues(ctx)
            out.append(sec("Continuous optimisation", "Drift and cadence", [
                ui.table(["Measure", "Baseline", "Now", "Change"], [["Overall confidence", f"{B['base']}%", f"{C['now']}%", f"{C['now'] - B['base']:+d}"], ["Open issues", len(I), sum(1 for i in I if i["id"] not in st["resolved"]), ""],
                                                                   ["Datasets certified", "0", len(st["certified"]), ""], ["Reviewer edits fed back", "—", len(ctx["memo_state"].get("edits") or []), "Used to retune field confidence"]], num=[1, 2, 3]),
                ui.h3("Improvement cadence"),
                ui.table(["Activity", "Frequency", "Owner"], [["Data quality rules re-run and drift check", "Weekly", "Data Governance Office"], ["Confidence scores refreshed against the baseline", "Monthly", "Data council"],
                                                              ["Early-warning model back-tested", "Quarterly", "Credit Risk Management"], ["Definitions reviewed and re-certified", "Every 6 months", "Data council"],
                                                              ["Roadmap re-prioritised", "Every 6 months", "Chief Data Officer"]], flat=False)]))
        if "Proactive decisions" in on:
            A = alerts(ctx)
            rows = [[ui.mono(a["date"]), ui.chip("bad", f"{-a['d']} d overdue") if a["d"] < 0 else ui.chip("warn", f"in {a['d']} d") if a["d"] <= 90 else ui.chip("idle", f"in {round(a['d'] / 30)} mo"),
                     ui.bold(a["t"]), a["act"], ui.hint(a["owner"])] for a in A]
            out.append(sec("Proactive decisions", f"{len(A)} dated alerts", [ui.table(["Date", "When", "Event", "Action", "Owner"], rows)]))
        if "Portfolio early warning" in on and R.get("port"):
            out.append(sec("Portfolio early warning", f"{len(R['port'])} borrowers", [{"type": "bars", "items": [
                {"label": b["b"], "sub": ", ".join(f[0].lower() for f in sorted([f for f in b["F"] if f[1] > 0], key=lambda f: -f[1])[:2]) or "no adverse signals",
                 "pct": b["score"], "tone": "bad" if b["band"] == "Red" else "warn" if b["band"] == "Amber" else "ok", "value": f"{b['score']}%"} for b in sorted(R["port"], key=lambda b: -b["p"])]}]))
        if "Model governance" in on:
            out.append(sec("Model governance", "Model card", [ui.table(["Item", "Detail"], [["Model", "Early-warning score v0.1 (logistic, hand-set weights)"],
                                                                                         ["Inputs", "Internal rating, IFRS 9 stage, days past due, restructuring, news distress and sentiment, covenant alerts, sanctions matches, pricing"],
                                                                                         ["Limits", "Not fitted to default history; single point in time"], ["Validation", "Not validated; needs independent model validation before use"],
                                                                                         ["Owner", "Credit Risk Management"], ["Review", "Quarterly back-test"]])]))
    return out


def ai_blocks(ctx, st):
    thr = st["aiThr"]
    fs = MM.fields_in(ctx["M"], ["0", *MM.selected(ctx["memo_state"])])
    auto = [f for f in fs if f["kind"] in MM.AUTO_KINDS]
    ai = [f for f in auto if MM.CONF_N.get(f["conf"], 60) >= thr]
    ST = ctx["ST"]
    return [ui.kpis([(len(ai), f"AI drafts (confidence ≥ {thr})", "ok"), (len(auto) - len(ai), "AI suggests, human confirms", "warn"),
                     (ST["manual"] + ST["edited"], "Human writes"), (len(ST["missing"]), "No data yet")]),
            ui.notes(["Every AI-drafted value keeps its source tag and is listed for reviewer sign-off in 5.5.",
                      "Recommendations, approval decisions and compliance outcomes are never drafted by AI.",
                      f"Below {thr}, AI may suggest a value but a human must confirm it."])]


def blocker(ctx, st, k) -> str:
    crit = sum(1 for i in issues(ctx) if i["sev"] == "Critical" and i["id"] not in st["resolved"])
    need = [d for d in ("DS-01", "DS-02") if d not in st["certified"]]
    if k == "stab" and crit:
        return f"Resolve the {crit} critical issue{'s' if crit > 1 else ''} first."
    if k == "std" and need:
        return f"Certify {' and '.join(need)} first."
    return ""


def blocks(ctx, st) -> list[dict]:
    C, I, DS = confidence(ctx, st), issues(ctx), datasets(ctx, st)
    c, ref = ctx["borrower"], ctx["ref_date"].isoformat()
    ew = early_warning(ctx["ds_full"], ctx["M"])
    return [{"t": "title", "kicker": "Data360 · Phase 3 · Transform", "title": "Execution status", "sub": c,
             "meta": [["Client", c], ["Date", ref], ["Confidence", f"{C['now']}% (baseline {C['base']}%, target {C['tgt']}%)"],
                      ["Issues resolved", f"{sum(1 for i in I if i['id'] in st['resolved'])} of {len(I)}"], ["Datasets certified", f"{len(st['certified'])} of {len(DS)}"],
                      ["Stages complete", ", ".join(f"{s['n']} {s['t']}" for s in STEPS if st["st"][s["k"]]["done"]) or "None"]]},
            {"t": "h1", "text": "Confidence by domain"}, {"t": "table", "head": ["Domain", "Baseline", "Now", "Target"], "widths": [40, 20, 20, 20], "num": [1, 2, 3],
                                                         "rows": [[d["d"], f"{d['base']}%", f"{d['now']}%", f"{d['to']}%"] for d in C["byDom"]]},
            {"t": "h1", "text": "10. Stabilise · issue register"}, {"t": "table", "head": ["ID", "Issue", "Severity", "Owner", "Status"], "widths": [10, 46, 12, 18, 14], "small": True,
                                                                   "rows": [[i["id"], i["t"], i["sev"], i["owner"], "Resolved" if i["id"] in st["resolved"] else "Open"] for i in I]},
            {"t": "h1", "text": "11. Standardise · trusted datasets"}, {"t": "table", "head": ["ID", "Dataset", "Golden fields", "Status"], "widths": [10, 40, 25, 25],
                                                                       "rows": [[d["id"], d["name"], f"{d['held']} of {len(d['fields'])}", d["status"]] for d in DS]},
            {"t": "h1", "text": "13. Transform · early warning"}, {"t": "p", "text": f"Illustrative probability of downgrade or default in 12 months: {ew['score']}% ({ew['band']})."},
            {"t": "table", "head": ["Signal", "Value", "Weight"], "widths": [40, 40, 20], "rows": [[f[0], f[2], f"{f[1]:.1f}"] for f in ew["F"]]},
            {"t": "h2", "text": "Proactive alerts"}, {"t": "table", "head": ["Date", "Event", "Action", "Owner"], "widths": [14, 28, 40, 18], "small": True,
                                                       "rows": [[a["date"], a["t"], a["act"], a["owner"]] for a in alerts(ctx)]}]
