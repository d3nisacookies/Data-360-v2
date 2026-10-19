"""Step 2 · Assess: score the data on seven data-quality dimensions.

Issues are detected from the data itself (cross-source comparison, golden-source
priority, type checks, dates). Provider quality flags, where a file has them, are
used as extra evidence and reported separately; nothing depends on them.
"""
from collections import defaultdict
from datetime import timedelta

from .core import Dataset, disagreements, golden, mean, pct
from .reference import CRITICAL, GOLD_PRIORITY, LABEL, REFRESH_DAYS, SECTION, VALUE_FIELDS, ELEMENT_FIELD
from .values import differs, fmt, is_blank, typed, validate_element, validate_field

DIMS = {
    "Completeness": "Is everything the credit memo needs present?",
    "Accuracy": "Do the values match the golden source?",
    "Consistency": "Do sources agree with each other?",
    "Validity": "Do values have the right format, type and units?",
    "Timeliness": "Is the data recent enough for its refresh cycle?",
    "Usage": "Is the sourced data actually used by the outputs?",
    "Business relevance": "Does the data support the credit decision being made?",
}
IMPORTANT = ["Net_Debt", "Collateral_Value", "Leverage_Covenant", "Interest_Rate", "Margin", "Industry", "Registry_Status", "ESG_Score"]
# data-dictionary elements the credit memo and its criteria use (beyond the mapped canonical fields)
MEMO_ELEMENTS = {x.lower() for x in [
    "Audit status", "Valuer", "Obligor rating", "Probability of default (PD)", "Loss given default (LGD)", "Rating model",
    "Rating date", "KYC status", "Next KYC review date", "Screening result", "Sanctions hit flag", "PEP flag", "UBO name",
    "Limit amount", "Utilisation", "Exposure at default (EAD)", "Total commitment", "Undrawn / available amount",
    "Valuation date", "Perfection status", "LTV ratio", "Headroom", "Next test date", "Covenant threshold", "ECL stage",
    "Approval authority", "Approval ID", "Approver", "Ultimate parent", "Facility type", "Facility ID", "Margin",
    "All-in rate", "Final maturity date", "Drawn amount", "Legal name", "Company registration number (UEN)",
    "Country of incorporation", "Issuer rating", "RM name", "Watchlist status", "Industry code", "ESG score"]}
SECTIONS = ["Identity", "Credit", "Financials", "Facility", "Compliance", "Security", "Covenants", "ESG"]
CAP_BELOW = 70


def rate(score):
    if score is None:
        return "na"
    return "high" if score >= 85 else "med" if score >= 60 else "low"


def _issue(kind, where, detail, **kw):
    return {"issue": kind, "where": where, "detail": detail, **kw}


def _ctx_terms(ctx: dict | None, G: dict, cleaned: bool):
    """Seeker and Collector findings that feed Completeness, Consistency and Business relevance."""
    ctx = ctx or {}
    sk, co = ctx.get("seek"), ctx.get("collect")
    t = {"attrs": None, "found": [], "missing": [], "conf": [], "resolved": [], "cov": None, "outs": []}
    if sk:
        res = sk["results"]
        t["attrs"] = len(res)
        t["found"] = [r for r in res if r["status"] in ("ok", "multi", "conf")]
        t["missing"] = [r for r in res if r["status"] in ("miss", "indirect", "pending")]
        conf = [r for r in res if r["status"] == "conf"]
        # after Clean, a conflict on a field with a golden value is settled by the survivorship rule
        t["resolved"] = [r for r in conf if cleaned and r.get("field") and G.get(r["field"])]
        t["conf"] = [r for r in conf if r not in t["resolved"]]
    if co:
        c = co["coverage"]
        t["outs"] = c
        t["cov"] = (sum(1 for x in c if x["status"] == "ok") + 0.5 * sum(1 for x in c if x["status"] == "part")) / len(c) if c else None
    return t


def score_dims(ds: Dataset, G: dict | None = None, ctx: dict | None = None, cleaned: bool = False) -> dict:
    G = G if G is not None else golden(ds)
    recs = ds.live()
    els = ds.live_elements()
    out = {}

    # ---- Completeness
    crit_have = [f for f in CRITICAL if G.get(f)]
    imp_have = [f for f in IMPORTANT if G.get(f)]
    incomplete = {}
    for r in recs:
        if r.flag == "INCOMPLETE":
            incomplete[r.key] = (r, "Flagged incomplete by the provider")
        for f, srcs in GOLD_PRIORITY.items():
            if r.source in srcs and is_blank(r.fields.get(f)) and G.get(f):
                where = "another record" if G[f]["source"] == r.source else G[f]["source"]
                incomplete[r.key] = (r, f"{LABEL[f]} blank in a golden-source record; value held in {where}")
    T = _ctx_terms(ctx, G, cleaned)
    issues = [_issue("Critical field missing", LABEL[f], "Not held in any source", field=f) for f in CRITICAL if not G.get(f)]
    issues += [_issue("Attribute missing" if r["status"] == "miss" else "Attribute only partly found" if r["status"] == "indirect" else "Attribute requested",
                      r["attribute"], "Requested from " + ", ".join(r["requested_from"]) if r["status"] == "pending" else (r.get("note") or "Not held in any source"))
               for r in T["missing"]]
    issues += [_issue("Field missing", LABEL[f], "Not held in any source", field=f) for f in IMPORTANT if not G.get(f)]
    issues += [_issue("Incomplete record", f"{r.source} · {r.rid}", why, key=r.key) for r, why in incomplete.values()]
    out["Completeness"] = {
        "score": pct(mean([len(crit_have) / len(CRITICAL), len(imp_have) / len(IMPORTANT), 1 - len(incomplete) / len(recs) if recs else None,
                           len(T["found"]) / T["attrs"] if T["attrs"] else None])),
        "basis": f"{len(crit_have)} of {len(CRITICAL)} critical fields and {len(imp_have)} of {len(IMPORTANT)} supporting fields held · "
                 f"{len(incomplete)} of {len(recs)} records incomplete"
                 + (f" · {len(T['found'])} of {T['attrs']} Seeker attributes found" if T["attrs"] else " · Seeker not run"),
        "issues": issues}

    # ---- Accuracy: disagreement with a golden-source value
    wrong = {}
    for r in recs:
        bad = [f for f in disagreements(ds, G, r) if G[f]["rule"] == "golden-source"]
        if bad and r.status not in ("CORRECTED", "RECONCILED"):
            wrong[r.key] = (r, bad)
        elif r.flag == "WRONG" and not r.status:
            wrong[r.key] = (r, [])
    out["Accuracy"] = {
        "score": pct(1 - len(wrong) / len(recs)) if recs else None,
        "basis": f"{len(wrong)} of {len(recs)} records disagree with the golden source"
                 + (f" ({sum(1 for r, b in wrong.values() if r.flag == 'WRONG')} also flagged wrong by the provider)" if any(r.flag == "WRONG" for r, _ in wrong.values()) else ""),
        "issues": [_issue("Wrong value", f"{r.source} · {r.rid}",
                          "; ".join(f"{LABEL[f]} {fmt(f, r.fields.get(f))} vs golden {G[f]['display']} ({G[f]['source']})" for f in bad)
                          or "Flagged wrong by the provider; no field differs from the golden record", key=r.key)
                   for r, bad in wrong.values()]}

    # ---- Consistency: fields where sources disagree (measured against the golden value)
    spread, multi = [], 0
    for f in VALUE_FIELDS:
        held = [r for r in recs if typed(f, r.fields.get(f)) is not None]
        if len({r.source for r in held}) < 2 or not G.get(f):
            continue
        multi += 1
        off = defaultdict(set)
        for r in held:
            if r.key != G[f]["key"] and differs(f, r.fields[f], G[f]["value"]):
                off[fmt(f, r.fields[f])].add(r.source)
        if off:
            spread.append((f, off))
    inc_flag = [r for r in recs if r.flag == "INCONSISTENT" and not r.status]
    out["Consistency"] = {
        "score": pct(mean([1 - len(spread) / multi if multi else None, 1 - len(inc_flag) / len(recs) if recs else None,
                           1 - len(T["conf"]) / len(T["found"]) if T["found"] else None])),
        "basis": f"{len(spread)} of {multi} fields held by two or more sources have conflicting values · {len(inc_flag)} records flagged inconsistent"
                 + (f" · {len(T['conf'])} of {len(T['found'])} Seeker attributes have values that disagree" if T["found"] else "")
                 + (f" ({len(T['resolved'])} settled by the golden source in Clean)" if T["resolved"] else ""),
        "issues": [_issue("Conflicting values", LABEL[f], f"Golden {G[f]['display']} ({G[f]['source']}) vs "
                          + "; ".join(f"{v} ({', '.join(sorted(s))})" for v, s in list(off.items())[:6]), field=f)
                   for f, off in spread]
                  + [_issue("Inconsistent record", f"{r.source} · {r.rid}", "Flagged inconsistent by the provider", key=r.key) for r in inc_flag]
                  + [_issue("Attribute values disagree", r["attribute"], "; ".join(f"{v['value']} ({', '.join(v['locations'])})" for v in r["values"][:5])) for r in T["conf"]]}

    # ---- Validity
    checked, bad = 0, []
    for r in recs:
        for f in VALUE_FIELDS:
            v = r.fields.get(f)
            if is_blank(v):
                continue
            checked += 1
            why = validate_field(f, v)
            if why:
                bad.append(_issue("Invalid value", f"{r.source} · {r.rid} · {LABEL[f]}", f'"{v}": {why}', key=r.key))
    for e in els:
        checked += 1
        why = validate_element(e.dtype, e.value)
        if why:
            bad.append(_issue("Invalid value", f"{e.source} · {e.element}", f'"{e.value or ""}": {why}', element=e.key))
    out["Validity"] = {"score": pct(1 - len(bad) / checked) if checked else None,
                       "basis": f"{checked - len(bad)} of {checked} values have a valid format for their type", "issues": bad}

    # ---- Timeliness
    dated = [r for r in recs if r.as_of]
    stale = [r for r in recs if ds.is_stale(r)]
    newest = {}
    for r in dated:
        newest[r.source] = max(newest.get(r.source, r.as_of), r.as_of)
    late = [(s, d) for s, d in newest.items() if s in REFRESH_DAYS and (ds.ref_date - d) > timedelta(days=max(REFRESH_DAYS[s] * 2, 7))]
    out["Timeliness"] = {
        "score": pct(mean([1 - len(stale) / len(recs) if recs else None, 1 - len(late) / len(newest) if newest else None])),
        "basis": f"{len(stale)} of {len(recs)} records older than {ds.stale_days} days or flagged stale · "
                 f"{len(late)} of {len(newest)} feeds behind their refresh cycle (reference date {ds.ref_date.isoformat()})",
        "issues": [_issue("Feed behind cycle", s, f"Newest data {(ds.ref_date - d).days} days old against a {REFRESH_DAYS[s]}-day cycle") for s, d in late]
                  + [_issue("Stale record", f"{r.source} · {r.rid}", f"As of {r.as_of or 'unknown'}" + (" · flagged stale" if r.flag == "STALE" else ""), key=r.key) for r in stale]}

    # ---- Usage: does each source feed the golden record or the memo?
    used = set()
    for f, g in G.items():
        if g:
            used.update(g["support"])
            used.add(g["source"])
    for e in els:
        if (e.canonical or e.element.lower() in MEMO_ELEMENTS) and not validate_element(e.dtype, e.value):
            used.add(e.source)
    srcs = ds.sources()
    idle = [s for s in srcs if s not in used]
    out["Usage"] = {"score": pct(1 - len(idle) / len(srcs)) if srcs else None,
                    "basis": f"{len(srcs) - len(idle)} of {len(srcs)} sources feed the golden record or a credit-memo element",
                    "issues": [_issue("Not used", s, "Data sourced but not used by the golden record or any credit-memo element") for s in idle]}

    # ---- Business relevance: credit-memo sections supported
    sec = {s: [f for f in VALUE_FIELDS if SECTION.get(f) == s] for s in SECTIONS}
    sec = {s: fs for s, fs in sec.items() if fs}
    full = [s for s, fs in sec.items() if all(G.get(f) for f in fs)]
    part = [s for s, fs in sec.items() if s not in full and any(G.get(f) for f in fs)]
    out["Business relevance"] = {
        "score": pct(mean([(len(full) + 0.5 * len(part)) / len(sec), len(crit_have) / len(CRITICAL), T["cov"]])),
        "basis": f"{len(full)} of {len(sec)} credit-memo sections fully supported, {len(part)} partly"
                 + (f" · {sum(1 for x in T['outs'] if x['status'] == 'ok')} of {len(T['outs'])} Collector outputs fully covered" if T["outs"] else " · Collector not run"),
        "issues": [_issue("Section not fully supported", s, "Missing: " + ", ".join(LABEL[f] for f in fs if not G.get(f)))
                   for s, fs in sec.items() if s not in full]
                  + [_issue("Output not fully covered", x["output"], f"{x['hit']} of {x['total']} evidence groups found"
                            + (f"; missing {', '.join(x['missing'][:4])}" if x["missing"] else ""))
                     for x in T["outs"] if x["status"] != "ok"]}
    return out


def overall(dims: dict, selected: list[str]) -> dict:
    vals = [dims[d]["score"] for d in selected if dims[d]["score"] is not None]
    score = round(sum(vals) / len(vals)) if vals else None
    r = rate(score)
    weak = sorted([d for d in selected if dims[d]["score"] is not None and dims[d]["score"] < CAP_BELOW], key=lambda d: dims[d]["score"])
    cap = ""
    if r == "high" and weak:
        r, cap = "med", f"Capped at Medium by {weak[0]} ({dims[weak[0]]['score']})"
    return {"score": score, "rating": r, "cap": cap}


def assess(raw: Dataset, cleaned: Dataset | None, selected: list[str] | None = None, ctx: dict | None = None) -> dict:
    selected = [d for d in (selected or list(DIMS)) if d in DIMS] or list(DIMS)
    stages = []
    G0 = golden(raw)
    d0 = score_dims(raw, G0, ctx)
    stages.append({"key": "sourced", "label": "As sourced", "version": raw.version, "dims": {k: d0[k]["score"] for k in DIMS}, **overall(d0, selected)})
    current, Gc = d0, G0
    if cleaned is not None:
        Gc = golden(cleaned)
        current = score_dims(cleaned, Gc, ctx, cleaned=True)
        stages.append({"key": "cleaned", "label": "After Clean", "version": cleaned.version, "dims": {k: current[k]["score"] for k in DIMS}, **overall(current, selected)})
    ds = cleaned or raw
    flags = defaultdict(int)
    for r in raw.records:
        if r.flag:
            flags[r.flag] += 1
    return {
        "borrower": raw.borrower, "version": ds.version, "selected": selected, "ref_date": raw.ref_date.isoformat(),
        "overall": overall(current, selected), "stages": stages,
        "dims": {k: {**v, "rating": rate(v["score"]), "question": DIMS[k], "before": d0[k]["score"] if cleaned is not None else None}
                 for k, v in current.items()},
        "counts": {"records": len(ds.live()), "elements": len(ds.live_elements()), "sources": len(ds.sources()),
                   "removed": len(raw.records) - len(ds.live())},
        "provider_flags": dict(flags),
        "golden": Gc,
        "inputs": {"collector": bool((ctx or {}).get("collect")), "seeker": bool((ctx or {}).get("seek")),
                   "scope": (ctx or {}).get("collect", {}).get("sources") if (ctx or {}).get("collect") else None},
    }
