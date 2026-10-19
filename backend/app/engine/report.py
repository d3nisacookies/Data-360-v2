"""Source tasks (catalogue, ownership, flows, refresh) and the Phase 1 source findings report:
an executive summary shown on screen and a detailed report as HTML or Word (ported from the demo)."""
from __future__ import annotations

import re
from datetime import date

from . import confidence as CF
from .assess import DIMS, rate
from .reference import LABEL
from .registry import DOC_CATS, OWNER_CHOICES, REPORT_CATS, meta

WORD = {"high": "High", "med": "Medium", "low": "Low", "na": "—"}
SL = {"ok": "Found", "multi": "Found (several)", "conf": "Values disagree", "miss": "Not found", "indirect": "Partial match", "pending": "Requested"}
RS = {"ok": "Within cycle", "late": "Behind schedule", "mixed": "Holds stale records", "none": "No data"}


def plural(n, w):
    return f"{n} {w}{'' if n == 1 else 's'}"


def age_txt(days):
    if days is None:
        return "—"
    return f"{days} d" if days < 60 else f"{round(days / 30)} mo"


def tasks(ds, owners: dict, upload_dates: dict, ref: date) -> dict:
    """The four Source tasks across every location for this borrower."""
    locs = []
    for s in ds.sources():
        els = [e for e in ds.elements if e.source == s]
        recs = [r for r in ds.records if r.source == s]
        kind = "Internal" if els and not recs else "External" if recs and not els else "Internal / External"
        locs.append({"name": s, "kind": "Internal" if els else "External", "label": kind, "els": els, "recs": recs})
    cat, own, flow, refresh = [], [], [], []
    for l in locs:
        m = meta(l["name"], l["kind"], owners)
        rep = sum(1 for e in l["els"] if e.category in REPORT_CATS)
        doc = sum(1 for e in l["els"] if e.category in DOC_CATS)
        sys_ = len(l["els"]) - rep - doc + len(l["recs"])
        cat.append({"name": l["name"], "kind": l["label"], "system": m["system"], "sys": sys_, "rep": rep, "doc": doc, "total": sys_ + rep + doc})
        own.append({"name": l["name"], "kind": l["kind"], "owner": m["owner"], "steward": m["steward"], "assigned": m["assigned"]})
        flow.append({"name": l["name"], "steps": m["flow"], "method": m["method"]})
        if l["recs"]:
            dates = [r.as_of for r in l["recs"] if r.as_of]
            last = max(dates) if dates else None
            stale = sum(1 for r in l["recs"] if ds.is_stale(r))
        else:
            d = upload_dates.get(l["name"])
            last = date.fromisoformat(d[:10]) if d else None
            stale = 0
        age = (ref - last).days if last else None
        days = m["days"]
        status = "none" if last is None else "late" if days and age is not None and age > max(days * 1.5, days + 2) else "mixed" if stale else "ok"
        refresh.append({"name": l["name"], "cycle": m["cycle"], "last": last.isoformat() if last else None, "age": age, "stale": stale, "status": status,
                        "basis": "Newest record as-of date" if l["recs"] else "Latest upload of this source"})
    return {"cat": cat, "own": own, "flow": flow, "ref": refresh, "n": len(locs), "el": sum(c["total"] for c in cat),
            "gaps": sum(1 for o in own if not o["owner"]), "owner_choices": OWNER_CHOICES}


def build(ctx: dict) -> dict:
    """ctx: borrower, facility, ref_date, ds_full, collect, seek, assess, clean, norm, owners, upload_dates."""
    c, fac, ref = ctx["borrower"], ctx.get("facility") or "", ctx["ref_date"]
    C, S, A, CL, NM = ctx.get("collect"), ctx.get("seek"), ctx.get("assess"), ctx.get("clean"), ctx.get("norm")
    T = tasks(ctx["ds_full"], ctx.get("owners") or {}, ctx.get("upload_dates") or {}, ref)
    cov = C["coverage"] if C else []
    res = S["results"] if S else []
    by = lambda *k: [r for r in res if r["status"] in k]  # noqa: E731
    actions = []
    if C:
        add_by, gap_by = {}, {}
        for v in cov:
            for s in v["addable"]:
                add_by.setdefault(s, []).append(v["output"])
            for g in v["missing"]:
                gap_by.setdefault(g, []).append(v["output"])
        for s, os_ in add_by.items():
            actions.append(["Collector scope", f"Add {s} to the Collector's named locations to complete {' and '.join(chr(34) + o + chr(34) for o in os_)}."])
        for g, os_ in gap_by.items():
            actions.append(["Data gap", f"No {g} records are held for {c}, which affects {' and '.join(chr(34) + o + chr(34) for o in os_)}. Confirm with the source owner or obtain externally."])
    for r in by("conf"):
        v = r["values"]
        actions.append(["Reconcile", f"{r['attribute']}: {len(v)} different values across {plural(len(r['locations']), 'location')}. Most frequent is \"{v[0]['value']}\" "
                                     f"({v[0]['count']} of {len(r['hits'])} sightings). Pass to Assess for an authoritative value."])
    for r in by("miss"):
        actions.append(["Missing attribute", f"{r['attribute']} is not held in any location searched." + (f" Request it from {r['suppliers'][0]}." if r.get("suppliers") else "")])
    for r in by("indirect"):
        actions.append(["Partial match", f"{r['attribute']}: {r['note'] or 'only indirect evidence found.'}"])
    for r in by("pending"):
        actions.append(["Awaiting source", f"{r['attribute']} has been requested from {', '.join(r['requested_from'])}; that source is not uploaded yet."])
    for o in T["own"]:
        if not o["owner"]:
            actions.append(["Ownership", f"Assign a business owner and data steward for {o['name']} ({o['kind'].lower()} source)."])
    for r in T["ref"]:
        if r["status"] == "late":
            actions.append(["Refresh", f"{r['name']} is behind its {r['cycle'].lower()} cycle: newest data is {age_txt(r['age'])} old."])
        if r["status"] == "mixed":
            actions.append(["Refresh", f"{r['name']} holds {plural(r['stale'], 'record')} older than {ctx['ds_full'].stale_days} days; refresh or retire them."])
    if A:
        for lvl in ("low", "med"):
            for d in A["selected"]:
                if A["dims"][d]["rating"] == lvl:
                    actions.append(["Assess", f"{d} scored {A['dims'][d]['score']}/100 ({WORD[lvl]}): {A['dims'][d]['basis']}."])
    if NM and NM["out"].get("KPIs"):
        for k in NM["out"]["KPIs"]["rows"]:
            if k[6] == "r":
                actions.append(["KPI red", f"{k[0]} is {k[5]} ({k[2]}). Owner: {k[3]}."])
    if CL:
        for e in CL["escalations"]:
            actions.append(["Escalation", f"{e['item']}: {e['why']}. Owner: {e['owner']}, due {e['due']}."])
    restricted = C["counts"]["restricted"] if C else 0
    if restricted:
        actions.append(["Access control", f"{restricted} of {C['counts']['elements']} collected elements are classified Restricted. Apply access controls and masking before use in a credit memo."])
    full = sum(1 for v in cov if v["status"] == "ok")
    ready = bool(C) and full == len(cov) and not by("conf") and not by("miss") and (not A or (A["overall"]["score"] or 0) >= 85)
    stage = ("Steps 1–4: Source, Assess, Clean and Normalise" if NM else "Steps 1–3: Source, Assess and Clean" if CL else "Steps 1–2: Source and Assess" if A else "Step 1: Source")
    B = [{"t": "title", "title": "Data360 Source Findings", "sub": c + (f" · Facility {fac}" if fac else ""),
          "meta": [["Client", c], ["Facility ID", fac or "Not specified (all facilities)"], ["Phase", f"Phase 1 · Assess & Improve · {stage}"],
                   ["Use case", "Credit Memo Acceleration and Assurance"], ["Data as at", ref.isoformat()], ["Classification", "Confidential"]]},
         {"t": "h1", "text": "1. Executive summary"}]
    probs = [x for x in [f"{len(cov) - full} of {len(cov)} required outputs are not fully covered" if full < len(cov) else "",
                         f"{plural(len(by('conf')), 'attribute')} {'has' if len(by('conf')) == 1 else 'have'} conflicting values" if by("conf") else "",
                         f"{plural(len(by('miss')), 'attribute')} {'is' if len(by('miss')) == 1 else 'are'} not held anywhere" if by("miss") else "",
                         "the Collector has not run" if not C else ""] if x]
    B.append({"t": "callout", "tone": "ok" if ready else "warn",
              "text": "Overall: decision-ready for the outputs requested. All outputs are covered and no attribute conflicts were found." if ready else
              f"Overall: not yet decision-ready. Data for {c} exists across the bank's systems and external feeds, but {', '.join(probs) or 'checks are outstanding'}. "
              "Reconciliation is needed before the data supports a credit memo."})
    CS = CF.stages(A, NM)
    if CS:
        L = CS[-1]
        B.append({"t": "battery", "pct": L["pct"], "stages": [{"label": x["label"], "pct": x["pct"]} for x in CS],
                  "label": f"Data confidence: {L['pct']}% confident · {100 - L['pct']}% not confident ({WORD[L['r']]}{', ' + L['cap'] if L['cap'] else ''}{', provisional' if L['provisional'] else ''})",
                  "note": "Average of the 7 Assess criteria. The rating cannot be High while any criterion is below 70"
                          + (". Values after Clean and Normalise are provisional until a reviewer signs off the golden record." if len(CS) > 1 else "."),
                  "breakdown": CF.breakdown(CS)})
    bul = []
    if C:
        bul.append(f"Collector: searched {plural(C['counts']['locations'], 'named location')} and found {C['counts']['elements']} data elements and {C['counts']['records']} records. "
                   f"{full} of {len(cov)} required outputs are fully covered.")
    if S:
        bul.append(f"Seeker: searched {S['locations']} locations for {plural(len(res), 'attribute')}. {len(by('ok', 'multi'))} found consistently, {len(by('conf'))} with conflicting values, "
                   f"{len(by('miss', 'indirect'))} missing or partial" + (f", {len(by('pending'))} requested from additional sources" if by("pending") else "") + ".")
    bul += [f"Catalogue: {T['n']} locations hold {T['el']} items for {c} ({sum(x['sys'] for x in T['cat'])} system data, {sum(x['rep'] for x in T['cat'])} report, {sum(x['doc'] for x in T['cat'])} document items).",
            f"Ownership: {plural(T['gaps'], 'location') + (' has' if T['gaps'] == 1 else ' have') + ' no business owner' if T['gaps'] else 'every location has a business owner'}.",
            f"Refresh: {sum(1 for r in T['ref'] if r['status'] in ('late', 'mixed'))} locations are behind their cycle or hold stale records."]
    if NM:
        bul.append("Normalise: " + ", ".join(f"{v['n']} {k.lower()}" for k, v in NM["out"].items()) + " defined (v1.0).")
    if CL:
        sm = CL["summary"]
        bul.append(f"Clean: data pack {CL['version']} with {len(CL['log'])} logged changes; " + "; ".join(v["text"].rstrip(".") for v in sm.values()) + f"; {len(CL['escalations'])} items escalated.")
    if A:
        low = sorted([d for d in A["selected"] if A["dims"][d]["score"] is not None], key=lambda d: A["dims"][d]["score"])[:2]
        bul.append(f"Assess: overall data confidence {A['overall']['score']}/100 ({WORD[A['overall']['rating']]}). Lowest: " + ", ".join(f"{d} {A['dims'][d]['score']}" for d in low) + ".")
    B += [{"t": "bullets", "items": bul}, {"t": "h2", "text": "Priority actions"}, {"t": "numbered", "items": [f"{k}: {v}" for k, v in actions] or ["None."]}]
    # 2 scope
    B += [{"t": "h1", "text": "2. Scope and method"},
          {"t": "p", "text": "Data360 used two agents. The Collector knows what to look for and where: it searched the named locations selected by the user. "
                             "The Seeker knows only the data attributes: it searched every uploaded internal source and external feed."},
          {"t": "table", "head": ["Item", "Scope"], "widths": [28, 72], "rows": [
              ["Collector locations", ", ".join(C["sources"]) if C else "Not run"], ["Outputs required", ", ".join(C["outputs"]) if C else "Not run"],
              ["Seeker attributes", ", ".join(S["attributes"]) if S else "Not run"], ["Source tasks", f"Run across all {T['n']} uploaded locations"],
              ["Assess", ", ".join(A["selected"]) if A else "Not run"], ["Data", "Files uploaded to Data360. Owners, stewards and flows are sample metadata unless assigned."]]}]
    n = 3
    if C:
        B += [{"t": "h1", "text": f"{n}. Collector findings"},
              {"t": "kpis", "items": [[C["counts"]["locations"], "Locations searched"], [C["counts"]["records"], "Records found"], [C["counts"]["elements"], "Data elements"], [restricted, "Restricted elements"]]},
              {"t": "h2", "text": f"{n}.1 Output coverage"},
              {"t": "table", "head": ["Output", "Status", "Evidence found", "Gap"], "widths": [18, 13, 41, 28],
               "rows": [[v["output"], {"ok": "Covered", "part": "Partly covered"}.get(v["status"], "Not covered"),
                         "; ".join(f"{g['label']} ({g['n']})" for g in v["groups"] if g["n"]) or "None",
                         ". ".join(x for x in [("Needs " + ", ".join(v["addable"])) if v["addable"] else "", ("Not held: " + ", ".join(v["missing"])) if v["missing"] else ""] if x) or "—"] for v in cov]},
              {"t": "h2", "text": f"{n}.2 What each location holds"},
              {"t": "table", "head": ["Location", "In scope", "Records", "Elements", "Restricted", "Main categories"], "widths": [18, 10, 10, 10, 11, 41], "num": [2, 3, 4],
               "rows": [[l["source"], "Yes" if l["in_scope"] else "No", l["records"], l["elements"], l["restricted"], ", ".join(f"{k} ({v})" for k, v in l["categories"][:3])] for l in C["locations"]]}]
        n += 1
    if S:
        B += [{"t": "h1", "text": f"{n}. Seeker findings"},
              {"t": "kpis", "items": [[len(res), "Attributes searched"], [S["locations"], "Locations searched"], [len(by("ok", "multi")), "Found, consistent"], [len(by("conf")), "Conflicting"],
                                      [len(by("miss", "indirect", "pending")), "Missing, partial or requested"]]},
              {"t": "table", "head": ["Attribute", "Result", "Most frequent value", "Values", "Found in"], "widths": [19, 14, 26, 8, 33], "num": [3],
               "rows": [[r["attribute"], SL[r["status"]], r["values"][0]["value"] if r["values"] else "—", len(r["values"]),
                         ("Requested from " + ", ".join(r["requested_from"])) if r["status"] == "pending" else ", ".join(r["locations"]) or "—"] for r in res]}]
        for r in by("conf"):
            B += [{"t": "h3", "text": r["attribute"]}, {"t": "table", "head": ["Value", "Sightings", "Locations"], "widths": [34, 12, 54], "num": [1],
                                                        "rows": [[v["value"], v["count"], ", ".join(v["locations"])] for v in r["values"]]}]
        n += 1
    B += [{"t": "h1", "text": f"{n}. Source tasks"}, {"t": "p", "text": f"The four Source tasks were run across all {T['n']} uploaded locations."},
          {"t": "h2", "text": f"{n}.1 Catalogue of sources, systems, reports and documents"},
          {"t": "table", "head": ["Location", "Type", "System", "System data", "Reports", "Documents", "Total"], "widths": [18, 11, 27, 11, 10, 11, 12], "num": [3, 4, 5, 6],
           "rows": [[x["name"], x["kind"], x["system"], x["sys"], x["rep"], x["doc"], x["total"]] for x in T["cat"]]},
          {"t": "h2", "text": f"{n}.2 Ownership"},
          {"t": "table", "head": ["Location", "Type", "Business owner", "Data steward", "Status"], "widths": [22, 12, 28, 20, 18],
           "rows": [[o["name"], o["kind"], o["owner"] or "—", o["steward"] or "—", "Owned" if o["owner"] else "No owner"] for o in T["own"]]},
          {"t": "h2", "text": f"{n}.3 Data flows"},
          {"t": "table", "head": ["Location", "Flow to the credit memo", "Transfer method"], "widths": [20, 60, 20],
           "rows": [[f["name"], " → ".join([*f["steps"], "Data360", "Credit memo"]), f["method"]] for f in T["flow"]]},
          {"t": "h2", "text": f"{n}.4 Refresh cycles"},
          {"t": "table", "head": ["Location", "Expected cycle", "Freshest data", "Age", "Stale", "Status"], "widths": [22, 20, 15, 9, 11, 23], "num": [3, 4],
           "rows": [[r["name"], r["cycle"], r["last"] or "—", age_txt(r["age"]), r["stale"], RS[r["status"]]] for r in T["ref"]]}]
    n += 1
    if A:
        B += [{"t": "h1", "text": f"{n}. Assess findings"},
              {"t": "p", "text": f"Overall data confidence is {A['overall']['score']}/100 ({WORD[A['overall']['rating']]}). High is 85 or above, Medium 60 to 84, Low below 60."},
              {"t": "table", "head": ["Criterion", "Score", "Rating", "Basis", "Issues"], "widths": [18, 8, 10, 54, 10], "num": [1, 4],
               "rows": [[d, A["dims"][d]["score"] if A["dims"][d]["score"] is not None else "—", WORD[rate(A["dims"][d]["score"])], A["dims"][d]["basis"], len(A["dims"][d]["issues"])]
                        for d in A["selected"]]}]
        for d in A["selected"]:
            iss = A["dims"][d]["issues"]
            if iss:
                B += [{"t": "h3", "text": f"{d} ({len(iss)})"}, {"t": "table", "small": True, "head": ["Issue", "Where", "Detail"], "widths": [20, 35, 45],
                                                               "rows": [[i["issue"], i["where"], i["detail"]] for i in iss[:60]]}]
        n += 1
    if CL:
        G = CL["golden"]
        B += [{"t": "h1", "text": f"{n}. Clean results"},
              {"t": "p", "text": f"Data pack {CL['version']} was produced from v1.0 (as sourced), which is retained. {len(CL['log'])} changes were logged and {len(CL['escalations'])} items escalated."},
              {"t": "table", "head": ["Action", "Result"], "widths": [28, 72], "rows": [[k, v["text"]] for k, v in CL["summary"].items()]},
              {"t": "h2", "text": f"{n}.1 Golden record"},
              {"t": "table", "head": ["Field", "Golden value", "Source", "Record", "Why this source"], "widths": [17, 21, 15, 11, 36],
               "rows": [[LABEL.get(f, f), g["display"], g["source"], g["record"], g["why"]] for f, g in G.items() if g]},
              {"t": "h2", "text": f"{n}.2 Escalated items"},
              {"t": "table", "head": ["Item", "Why", "Owner", "Due"], "widths": [28, 40, 20, 12], "rows": [[e["item"], e["why"], e["owner"], e["due"]] for e in CL["escalations"]] or [["None", "", "", ""]]}]
        n += 1
    if NM:
        B += [{"t": "h1", "text": f"{n}. Normalise: common definitions"}]
        for i, (k, o) in enumerate(NM["out"].items()):
            B += [{"t": "h2", "text": f"{n}.{i + 1} {k}"}, {"t": "p", "text": o["text"]},
                  {"t": "table", "head": o["head"], "widths": [round(100 / len(o["head"]))] * len(o["head"]), "small": True, "rows": o["rows"]}]
        n += 1
    B += [{"t": "h1", "text": f"{n}. Issues and recommended actions"},
          {"t": "table", "head": ["#", "Area", "Action"], "widths": [6, 18, 76], "rows": [[i + 1, k, v] for i, (k, v) in enumerate(actions)] or [["—", "None", ""]]},
          {"t": "h2", "text": "Next step"},
          {"t": "p", "text": f"Phase 1 data work is complete for {c}. Resolve escalations and red KPIs, then build the credit memo (step 5)." if NM else
           "Resolve the escalated items with their owners, then move to Normalise to set common definitions." if CL else
           "Take the Low and Medium criteria into Clean." if A else "Pass the conflicting values, missing attributes and stale feeds to Assess."}]
    if CL:
        B += [{"t": "pagebreak"}, {"t": "h1", "text": "Appendix. Clean audit trail"},
              {"t": "table", "small": True, "head": ["#", "Action", "Record", "Field", "Original", "New", "Reason", "Source"], "widths": [4, 14, 9, 12, 14, 14, 22, 11],
               "rows": [[l["n"], l["action"], l["record"], l["field"], l["from"], l["to"], l["reason"], l["source"]] for l in CL["log"]]}]
    B.append({"t": "p", "muted": True, "text": "Record flag is the data-quality flag a provider set on the whole external record. Values come from the files uploaded to Data360."})
    return {"blocks": B, "actions": actions, "bullets": bul, "callout": B[2], "battery": next((b for b in B if b["t"] == "battery"), None), "tasks": T,
            "file": f"Data360 Source Findings - {re.sub(r'[^\w &.-]', '', c).rstrip('.')} - {ref.isoformat()}"}
