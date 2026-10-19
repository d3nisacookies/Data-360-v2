"""Step 3 · Clean: remove duplicates, correct errors, validate critical fields, reconcile conflicts.

Produces an audit trail (every change: original, new, reason, source), escalations with
owners and due dates, and a `changes` set that turns the sourced data into v1.1 (cleaned).
"""
from datetime import date, timedelta

from .core import Dataset, apply_changes, disagreements, golden
from .reference import CRITICAL, DEFAULT_OWNER, LABEL, OWNER, VALUE_FIELDS
from .values import differs, fmt, is_blank, norm_text, typed

ACTIONS = {
    "Remove duplicates": "Drop repeated records so each fact is counted once.",
    "Correct errors": "Replace values that disagree with the golden source with the golden value.",
    "Validate critical information": "Check identity, rating, facility and sanctions fields against the golden record.",
    "Reconcile conflicting records": "Decide one value where sources disagree, and record why.",
}
BY = "Data360 Clean (automated)"


def business_days(start: date, n: int) -> str:
    d, k = start, 0
    while k < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            k += 1
    return d.isoformat()


def clean(raw: Dataset, selected: list[str] | None = None, user: str = BY, ctx: dict | None = None, extra: list[str] | None = None) -> dict:
    selected = [a for a in (selected or list(ACTIONS)) if a in ACTIONS] or list(ACTIONS)
    ds = apply_changes(raw, {})
    ds.version = raw.version
    log, esc = [], []
    changes = {"removed": [], "removed_elements": [], "set": [], "status": {}}
    summary = {}

    def add(action, where, field, frm, to, reason, source):
        log.append({"n": len(log) + 1, "action": action, "record": where, "field": field, "from": frm, "to": to,
                    "reason": reason, "source": source, "by": user})

    def escalate(item, why, owner, days):
        if not any(e["item"] == item for e in esc):
            esc.append({"item": item, "why": why, "owner": owner, "due": business_days(ds.ref_date, days)})

    # 1 · duplicates: same source, same values -> keep the latest
    if "Remove duplicates" in selected:
        groups = {}
        for r in ds.live():
            sig = (r.source, tuple(str(typed(f, r.fields.get(f))) for f in VALUE_FIELDS))
            groups.setdefault(sig, []).append(r)
        n_rec = 0
        for g in groups.values():
            if len(g) < 2:
                continue
            g.sort(key=lambda r: str(r.as_of or ""), reverse=True)
            for r in g[1:]:
                r.removed = True
                n_rec += 1
                changes["removed"].append(r.key)
                add("Remove duplicates", r.rid, "Whole record", f"{r.source} · as of {r.as_of or 'unknown'}", "Removed (superseded)",
                    f"Same values as {g[0].rid} (as of {g[0].as_of or 'unknown'}); latest kept", r.source)
        seen, n_el = {}, 0
        for e in ds.live_elements():
            if e.dtype in ("Boolean", "Code", "Number") or is_blank(e.value):
                continue
            k = (e.source, e.category, e.element, norm_text(e.value))
            if k in seen:
                e.removed = True
                n_el += 1
                changes["removed_elements"].append(e.key)
                add("Remove duplicates", e.key.split(":")[1], e.element, e.value, "Removed (duplicate)", f"Same value already held in {seen[k]}", e.source)
            else:
                seen[k] = e.key.split(":")[1]
        summary["Remove duplicates"] = {"n": n_rec + n_el, "text": f"{n_rec} duplicate records and {n_el} duplicate internal values removed; {len(ds.live())} records kept."}

    G = golden(ds)

    # 2 · errors: values that disagree with a golden-source value
    if "Correct errors" in selected:
        fixed, flagged_only = 0, 0
        for r in ds.live():
            bad = [f for f in disagreements(ds, G, r) if G[f]["rule"] == "golden-source"]
            if not bad:
                if r.flag == "WRONG":
                    flagged_only += 1
                    escalate(f"{r.source} record {r.rid}", "Flagged wrong by the provider but no field differs from the golden record", "Data owner · " + r.source, 5)
                continue
            for f in bad:
                fixed += 1
                add("Correct errors", r.rid, LABEL[f], fmt(f, r.fields.get(f)), G[f]["display"],
                    f"Disagrees with the golden source {G[f]['source']} ({G[f]['record']}); golden value applied", r.source)
                r.fields[f] = G[f]["value"]
                changes["set"].append({"key": r.key, "field": f, "to": G[f]["value"]})
            r.status = "CORRECTED"
            changes["status"][r.key] = "CORRECTED"
        summary["Correct errors"] = {"n": fixed, "text": f"{fixed} wrong values corrected to the golden source"
                                     + (f"; {flagged_only} provider-flagged records escalated because no field differed" if flagged_only else "") + "."}

    # 3 · reconcile: remaining disagreements with consensus values
    if "Reconcile conflicting records" in selected:
        n, decisions = 0, {}
        for r in ds.live():
            bad = disagreements(ds, G, r)
            if not bad:
                if r.flag == "INCONSISTENT" and not r.status:
                    r.status = "RECONCILED"
                    changes["status"][r.key] = "RECONCILED"
                continue
            for f in bad:
                n += 1
                d = decisions.setdefault(f, {"field": LABEL[f], "chosen": G[f]["display"], "why": G[f]["why"], "replaced": set()})
                d["replaced"].add(fmt(f, r.fields.get(f)))
                add("Reconcile conflicting records", r.rid, LABEL[f], fmt(f, r.fields.get(f)), G[f]["display"],
                    f"Conflicts with {G[f]['source']}; {G[f]['why'].lower()}", r.source)
                r.fields[f] = G[f]["value"]
                changes["set"].append({"key": r.key, "field": f, "to": G[f]["value"]})
            if not r.status:
                r.status = "RECONCILED"
                changes["status"][r.key] = "RECONCILED"
        dec = [{**d, "replaced": sorted(d["replaced"])} for d in decisions.values()]
        summary["Reconcile conflicting records"] = {"n": n, "decisions": dec,
                                                    "text": f"{n} values aligned to the golden record across {len(dec)} fields."}

    # 4 · validate critical fields (after corrections), including internal systems
    if "Validate critical information" in selected:
        rows = []
        for f in CRITICAL:
            g = G.get(f)
            if not g:
                rows.append({"key": f, "field": LABEL[f], "status": "Not available", "golden": None, "source": None, "detail": "No value in any source"})
                escalate(f"Obtain {LABEL[f]} for {ds.borrower}", "Critical field not held in any source", OWNER.get(f, "Relationship manager"), 10)
                continue
            ext_bad = [r for r in ds.live() if differs(f, r.fields.get(f), g["value"])]
            int_vals = [e for e in ds.live_elements() if e.canonical == f and not is_blank(e.value)]
            int_bad = [e for e in int_vals if differs(f, e.value, g["value"])]
            held = len([r for r in ds.live() if not is_blank(r.fields.get(f))]) + len(int_vals)
            ok = not ext_bad and not int_bad
            rows.append({"key": f, "field": LABEL[f], "status": "Validated" if ok else "Failed", "golden": g["display"], "source": g["source"],
                         "detail": f"{held} values agree" if ok else f"{len(ext_bad)} record and {len(int_bad)} internal values disagree ("
                                   + ", ".join(sorted({r.source for r in ext_bad} | {e.source for e in int_bad})) + ")"})
            if not ok:
                escalate(f"{LABEL[f]} for {ds.borrower}",
                         f"{len(ext_bad) + len(int_bad)} value(s) disagree with golden {g['display']}: "
                         + "; ".join(f"{e.source} {e.value}" for e in int_bad[:3]),
                         OWNER.get(f, DEFAULT_OWNER), 3)
        summary["Validate critical information"] = {"n": sum(1 for r in rows if r["status"] == "Validated"), "rows": rows,
                                                    "text": f"{sum(1 for r in rows if r['status'] == 'Validated')} of {len(rows)} critical fields validated; "
                                                            f"{sum(1 for r in rows if r['status'] == 'Failed')} failed and escalated."}

    # always-on escalations
    for r in ds.live():
        if norm_text(r.fields.get("Sanctions_Screening", "")) in ("potential match", "possible match", "potential hit"):
            escalate(f"Sanctions potential match ({r.source} {r.rid})", "Name match needs investigation; not a confirmed hit", "Financial Crime Compliance", 2)
    for e in ds.live_elements():
        if e.canonical == "Sanctions_Screening" and norm_text(e.value or "") in ("potential match", "possible match"):
            escalate(f"Sanctions potential match ({e.source})", "Internal screening shows a potential match", "Financial Crime Compliance", 2)
    sk = (ctx or {}).get("seek")
    for r in (sk["results"] if sk else []):
        if r["status"] == "miss":
            escalate(f"Obtain {r['attribute']} for {ds.borrower}", "Not held in any uploaded source (Seeker)", "Relationship manager", 10)
        elif r["status"] == "conf" and not (r.get("field") and G.get(r["field"])):
            escalate(f"Resolve {r['attribute']} for {ds.borrower}", "Sources disagree: " + "; ".join(f"{v['value']} ({', '.join(v['locations'])})" for v in r["values"][:4]),
                     "Credit analyst", 5)
    stale = [r for r in ds.live() if ds.is_stale(r)]
    for s in sorted({r.source for r in stale}):
        k = sum(1 for r in stale if r.source == s)
        escalate(f"Bring-down data from {s}", f"{k} record(s) older than {ds.stale_days} days or flagged stale", "Data owner · " + s, 5)

    # further actions picked from the list
    from .picks import CLEAN_ACT, clean_pick
    picks = {}
    for name in [x for x in dict.fromkeys(extra or []) if x in CLEAN_ACT]:
        picks[name] = clean_pick(name, ds, golden(ds), {**(ctx or {}), "user": user}, add, escalate)

    cleaned = apply_changes(raw, changes)
    return {"selected": selected, "extra": list(picks), "picks": picks, "log": log, "escalations": esc, "summary": summary, "changes": changes,
            "golden": golden(cleaned), "kept": len(cleaned.live()), "total": len(raw.records),
            "version": cleaned.version}
