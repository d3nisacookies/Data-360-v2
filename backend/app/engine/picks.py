"""Optional extras from the pick lists (ported from the demo): ~30 further Assess criteria,
further Clean actions and further Normalise definitions. Each works on the uploaded data; where a
judgement needs evidence that is not held, it says what is missing instead of inventing a score."""
from __future__ import annotations

import re
from collections import Counter

from .core import Dataset, golden, reliability
from .reference import CRITICAL, FX, GOLD_PRIORITY, INTERNAL_GRADE, LABEL, VALUE_FIELDS
from .registry import meta
from .values import differs, fmt, is_blank, parse_number, validate_element


def _pc(x):
    return None if x is None else round(max(0.0, min(1.0, x)) * 100)


def _mean(xs):
    v = [x for x in xs if x is not None]
    return sum(v) / len(v) if v else None


def rate(s):
    return "na" if s is None else "high" if s >= 85 else "med" if s >= 60 else "low"


def _plural(n, w):
    return f"{n} {w}{'' if n == 1 else 's'}"


# ======================= Assess · further criteria =======================
CRIT_CATS = [
    ["Source and provenance", [
        ["Reliability of source", "Audited financials, management accounts, bureau, rating agency or unverified claim.", None, "reliability"],
        ["Independence", "Verified by a third party (auditor, valuer, counsel) or only self-reported.", ["Audit status", "Valuer", "Issuing firm", "Certified by", "Appraiser"], "independence"],
        ["Lineage and traceability", "Each figure traceable to a source document, with version and date.", None, "lineage"],
        ["Authenticity and integrity", "Evidence documents are genuine and unaltered.", ["Original held flag", "Wet-ink flag", "Notarisation type", "Seal registration certificate", "File hash"], "authentic"]]],
    ["Comparability and analytical", [
        ["Comparability across periods", "Consistent accounting standards, reporting dates and consolidation scope.", ["Reporting period", "Audit status", "Revenue", "EBITDA", "Revenue period"], None],
        ["Comparability with peers", "Peer and industry benchmarks on a like-for-like basis.", ["Comparable deal", "Benchmark value", "Loan pricing index", "League table"], None],
        ["Normalisation and adjustments", "One-offs, restatements, qualified opinions and pro forma adjustments explained.", ["Audit status", "Management overlay", "Restructuring plan"], None],
        ["Granularity", "Segment, geography, product and facility-level detail, not only group totals.", None, "granularity"],
        ["Reasonableness of projections", "Explicit, supported and stress-tested forecast assumptions.", ["Base case DSCR", "Sensitivity scenarios", "Model version", "Capex budget", "Opex budget"], None]]],
    ["Risk-specific", [
        ["Materiality", "Could gaps or errors change the decision, rating, pricing, structure or limit?", None, "materiality"],
        ["Sufficiency", "Enough data for the requested exposure, tenor and structure.", None, "sufficiency"],
        ["Forward-looking quality", "Leading indicators, pipeline, covenant headroom and sensitivities.", ["Headroom", "Next test date", "Sensitivity scenarios", "Expected close date", "Win probability"], None],
        ["Collateral and security data quality", "Valuation date, valuer independence, enforceability, perfection and haircuts.", ["Valuation date", "Valuer", "Perfection status", "LTV ratio", "Valuation method", "Registration date"], None],
        ["Exposure and limit accuracy", "Group-wide and connected exposure incl. undrawn, derivatives and guarantees.", ["Limit amount", "Utilisation", "Exposure at default (EAD)", "Leverage exposure", "Total commitment", "Undrawn / available amount", "Notional"], None],
        ["Rating and model input integrity", "Correct, documented inputs to rating, PD, LGD and EAD models.", ["Obligor rating", "Probability of default (PD)", "Loss given default (LGD)", "Rating model", "Rating date"], None]]],
    ["Governance, compliance and regulatory", [
        ["KYC/AML and sanctions currency", "Current beneficial ownership, screening, adverse media and PEP checks.", ["KYC status", "Next KYC review date", "Screening result", "Sanctions hit flag", "PEP flag", "UBO name"], "kyc"],
        ["Regulatory alignment", "BCBS 239, IFRS 9 staging, large exposure limits, MAS/FSA rules.", ["ECL stage", "Return form", "Risk weight", "Exposure % of Tier 1 capital", "SICR flag"], None],
        ["Policy conformity", "Presented as credit policy, covenant standards and delegated authority require.", ["Approval authority", "Approval conditions", "Covenant threshold", "Document title"], None],
        ["Auditability and documentation", "Evidence retained, assumptions logged, approvals recorded.", ["Approval ID", "Approver", "Decision date", "Committee date"], "audit"],
        ["Data ownership and accountability", "Named owner or sign-off for key data points.", None, "ownership"],
        ["Confidentiality and permitted use", "MNPI and third-party data used within consent and information barriers.", ["Wall-crossing date", "Person wall-crossed", "Legal hold flag"], "confidential"]]],
    ["Presentation and decision-usefulness", [
        ["Clarity and interpretability", "Definitions, units, currencies and terms stated clearly.", None, "clarity"],
        ["Transparency of limitations", "Known gaps, estimates, unaudited figures and conflicts disclosed.", None, "transparency"],
        ["Currency and FX consistency", "Single stated basis for currency conversion and rate dates.", None, "fx"],
        ["Conciseness and focus", "Decision-relevant data rather than volume.", None, "concise"],
        ["Conflict resolution", "Where sources disagree, the memo says which was used and why.", None, "conflicts"]]],
    ["Environmental and non-financial", [
        ["ESG and climate data quality", "Emissions, transition risk and sustainability data; Equator Principles.", ["ESG score", "Financed emissions (tCO2e)", "Equator Principles category", "Hazard score", "Sector transition score"], None],
        ["Country, sector and geopolitical data", "Current country risk, sovereign ceiling and sector outlook.", ["Country exposure", "Sector exposure", "Geography", "Sector tag", "Country"], None],
        ["Management and governance information", "Management track record, ownership structure, related parties.", ["UBO name", "Ultimate parent", "Authorised signatory", "Contact name", "Job title", "Parent-subsidiary link"], None]]],
]
CRIT = {n: {"n": n, "d": d, "el": el, "fn": fn, "cat": cat} for cat, items in CRIT_CATS for n, d, el, fn in items}


def _els(ds, names):
    want = {x.lower() for x in names}
    return [e for e in ds.live_elements() if e.element.strip().lower() in want and not is_blank(e.value)]


def score_crit(name: str, ds: Dataset, full: Dataset, ctx: dict) -> dict:
    """ds: data in the Collector's scope; full: everything uploaded for the borrower."""
    k = CRIT[name]
    seek = (ctx or {}).get("seek") or {"results": []}
    coll = (ctx or {}).get("collect")
    res = {r["attribute"]: r for r in seek["results"]}
    ints = [e for e in ds.live_elements() if not is_blank(e.value)]
    ext = ds.live()
    ev = _els(ds, k["el"] or [])
    other = sorted({e.source for e in _els(full, k["el"] or [])} - {e.source for e in ev})
    fn, out = k["fn"], None
    if fn == "reliability":
        w = [reliability(e.source) for e in ints] + [reliability(r.source) for r in ext]
        out = (_pc(_mean(w)), f"Weighted by source type across {len(w)} items: registries, rating agencies and core systems score highest; email and news lowest.")
    elif fn == "independence":
        a = _els(full, ["Audit status"])
        aud = sum(1 for e in a if re.match("audited", str(e.value), re.I))
        out = (_pc(aud / len(a)), f"{aud} of {len(a)} financial records are audited; {len(ev)} third-party verification elements in scope.") if a else None
    elif fn == "lineage":
        withref = sum(1 for r in ext if r.rid and r.as_of)
        out = (_pc((withref + len(ints) * 0.7) / max(1, len(ext) + len(ints))),
               f"External records carry a record ID and as-of date ({withref}/{len(ext)}); internal elements carry an ID and file but no as-of date.")
    elif fn == "authentic":
        f = [e for e in ev if e.dtype == "Boolean"]
        y = sum(1 for e in f if str(e.value).startswith("Y"))
        out = (_pc(y / len(f)), f"{y} of {len(f)} originality / wet-ink flags confirm originals.") if f else None
    elif fn == "granularity":
        held = {(e.source, e.category) for e in ints}
        allc = {(e.source, e.category) for e in full.elements if e.source in {x.source for x in ds.elements}}
        out = (_pc(len(held) / len(allc)) if allc else 0, f"{len(held)} of {len(allc)} categories in the selected sources hold data for this client.")
    elif fn == "materiality":
        mat = ["Registration Number", "Legal Entity Name", "Country of Incorporation", "Borrower Name"]
        hit = [a for a in mat if a in res and res[a]["status"] in ("conf", "miss")]
        w = sum(1 for r in ext if r.flag == "WRONG")
        out = (_pc(max(0.0, 1 - (len(hit) * 0.2 + w * 0.03))),
               f"{', '.join(hit) + ' conflict or are missing' if hit else 'No identity attributes in conflict'}; {w} wrong external values could affect rating, pricing or limit.")
    elif fn == "sufficiency":
        if coll:
            g = sum(c["total"] for c in coll["coverage"])
            h = sum(c["hit"] for c in coll["coverage"])
            out = (_pc(h / g) if g else 0, f"{h} of {g} evidence groups needed for the required outputs were found.")
    elif fn == "kyc":
        kk = _els(full, ["KYC status"])
        ok = sum(1 for e in kk if re.search("approved", str(e.value), re.I))
        s = [r for r in ext if re.search("sanction", r.source, re.I)]
        old = sum(1 for r in s if r.as_of and (ds.ref_date - r.as_of).days > 30)
        out = (_pc(_mean([ok / len(kk) if kk else None, 1 - old / len(s) if s else None])),
               f"{ok} of {len(kk)} KYC records approved; {old} of {len(s)} sanctions screenings older than 30 days.")
    elif fn == "audit":
        out = (_pc(_mean([1 if ev else 0.4, 0.9])), f"Every value has a record ID and its upload; {len(ev)} approval records in scope.")
    elif fn == "ownership":
        srcs = ds.sources()
        own = sum(1 for s in srcs if meta(s, "Internal" if any(e.source == s for e in ds.elements) else "External", (ctx or {}).get("owners"))["owner"])
        out = (_pc(own / len(srcs)) if srcs else None, f"{own} of {len(srcs)} sources have a named business owner.")
    elif fn == "confidential":
        r = sum(1 for e in ints if re.search("Restricted|MNPI", e.sensitivity or ""))
        out = (_pc(0.85 if ev else 0.5), f"{r} restricted or MNPI elements collected; " + (f"{len(ev)} wall-crossing / legal-hold controls found." if ev else "no wall-crossing or legal-hold evidence in scope."))
    elif fn == "clarity":
        a = [e for e in ints if e.dtype == "Amount"]
        ok = sum(1 for e in a if re.search(r"\b[A-Z]{3}\b", str(e.value)) and re.search(r"\d", str(e.value)))
        out = (_pc(ok / len(a)) if a else None, f"{ok} of {len(a)} amounts state a currency and a number.")
    elif fn == "transparency":
        f = sum(1 for r in ext if r.flag and r.flag != "VALIDATED")
        conf = sum(1 for r in seek["results"] if r["status"] == "conf")
        out = (60 if conf else 90, f"{f} external records carry an explicit quality flag; {conf} attribute conflicts are surfaced but not yet explained.")
    elif fn == "fx":
        cur = sorted({m.group(0) for e in ints if e.dtype == "Amount" for m in [re.search(r"\b[A-Z]{3}\b", str(e.value))] if m})
        out = (max(30, 100 - 15 * max(0, len(cur) - 1)), f"Amounts in {len(cur)} currencies ({', '.join(cur)}) with no stated conversion basis or rate date." if len(cur) > 1
               else f"All amounts in {cur[0] if cur else 'one currency'}; no conversion needed.")
    elif fn == "concise":
        if coll:
            rel = sum(g["n"] for c in coll["coverage"] for g in c["groups"])
            tot = len(ints) + len(ext)
            out = (_pc(min(1, rel / tot)) if tot else None, f"{min(rel, tot)} of {tot} collected values feed a required output.")
    elif fn == "conflicts":
        conf = [r["attribute"] for r in seek["results"] if r["status"] == "conf"]
        out = (0 if conf else 100, f"{len(conf)} conflicts ({', '.join(conf)}) have no recorded decision on which source was used." if conf else "No conflicts to resolve.")
    ev_txt = ""
    if k["el"]:
        ev_txt = (f"{_plural(len(ev), 'element')} in {', '.join(sorted({e.source for e in ev}))}" if ev else "None in the Collector's scope") + (f"; also held in {', '.join(other)}" if other else "")
    needs = (f"Add {', '.join(other)} to the Collector's locations" if other else f"Source: {', '.join(k['el'][:4])}") if k["el"] and not ev else ""
    if out and out[0] is not None:
        return {"score": out[0], "basis": out[1] + (f" Evidence: {ev_txt}." if ev_txt else ""), "needs": needs, "status": rate(out[0]), "cat": k["cat"]}
    return {"score": None, "basis": f"Evidence: {ev_txt}. Needs analyst review to score." if ev_txt else "No evidence held.", "needs": needs,
            "status": "review" if ev else "none", "cat": k["cat"]}


# ======================= Clean · further actions =======================
CLEAN_CATS = [
    ["Standardise and normalise", [["Standardise formats", "Align dates, ISO 4217 currency codes, number formats, units and decimals.", "fmt"],
                                   ["Harmonise currency and FX", "Convert to one reporting currency with a stated rate source and date.", "fx"],
                                   ["Normalise entity names and identifiers", "Match legal names, LEI, registration numbers, customer IDs and group codes.", "names"],
                                   ["Align accounting bases", "Map statements to a common GAAP, consolidation scope and reporting date.", "gaap"],
                                   ["Map to the bank's taxonomy", "Apply internal industry codes, facility types, rating grades and products.", "taxo"]]],
    ["Complete and fill gaps", [["Identify and chase missing data", "Request outstanding items from the borrower or RM with owners and due dates.", "chase"],
                                ["Treat nulls explicitly", "Distinguish not provided, not applicable and zero; never default silently.", "nulls"],
                                ["Impute only with documented justification", "Label estimates and disclose the method.", "impute"]]],
    ["Verify and corroborate", [["Tie data to source documents", "Re-perform figures against audited accounts, bureau reports and legal documents.", "tie"],
                                ["Independent corroboration", "Cross-check against auditor, valuer, registry, rating agency, bureau, filings.", "corrob"],
                                ["Authenticate documents", "Confirm genuineness with the issuer where fraud risk is elevated.", "auth"],
                                ["Refresh KYC, AML and sanctions screening", "Confirm ownership, PEP, adverse media and sanctions status are current.", "kyc"],
                                ["Verify exposure and limits", "Reconcile group exposure, undrawn commitments and derivatives to systems of record.", "expo"],
                                ["Validate rating model inputs", "Confirm inputs match verified financials; document overrides.", "rating"]]],
    ["Detect anomalies and apply judgement", [["Outlier and reasonableness testing", "Flag implausible ratios, swings, round numbers and out-of-range values.", "outlier"],
                                              ["Trend and variance analysis", "Investigate unexplained movements against prior periods and peers.", "trend"],
                                              ["Normalise one-offs", "Adjust exceptional items with a reported-to-adjusted bridge.", "oneoff"],
                                              ["Assess materiality", "Prioritise errors that could change the decision, rating, pricing or structure.", "material"]]],
    ["Resolve and document", [["Disclose residual limitations", "State remaining gaps, estimates and conflicts, with mitigants.", "residual"],
                              ["Version control", "Keep one controlled data pack and retain superseded versions.", "version"]]],
    ["Governance and sign-off", [["Segregate duties", "The preparer cleans; an independent reviewer checks.", "sod"],
                                 ["Obtain attestation", "RM and analyst confirm accuracy and completeness.", "attest"],
                                 ["Check confidentiality and permitted use", "Restrict MNPI and third-party data outside consent or barriers.", "mnpi"],
                                 ["Meet data protection requirements", "Mask or minimise personal data (PDPA) and apply retention rules.", "pdpa"],
                                 ["Feed back root causes", "Report recurring errors to data owners to fix at source.", "root"]]],
]
CLEAN_ACT = {n: {"n": n, "d": d, "k": k, "cat": cat} for cat, items in CLEAN_CATS for n, d, k in items}


def clean_pick(name: str, ds: Dataset, G: dict, ctx: dict, add, escalate) -> dict:
    """ds: the cleaned dataset. add(action, where, field, frm, to, reason, source) logs a note in the audit trail."""
    k = CLEAN_ACT[name]["k"]
    seek = (ctx or {}).get("seek") or {"results": []}
    ints = [e for e in ds.live_elements() if not is_blank(e.value)]
    recs = ds.live()
    if k == "fmt":
        n = 0
        for e in ints:
            v = str(e.value)
            m = re.match(r"^FY(\d{4})$", v)
            if m:
                n += 1
                add(name, e.key.split(":")[1], e.element, v, f"{m[1]}-01-01 to {m[1]}-12-31", "Fiscal year as an ISO 8601 date range", e.source)
                continue
            m = re.match(r"^(\d{4})-Q(\d)$", v)
            if m:
                q = int(m[2])
                n += 1
                add(name, e.key.split(":")[1], e.element, v, f"{m[1]}-{q * 3 - 2:02d}-01 to {m[1]}-{q * 3:02d}-{[31, 30, 30, 31][q - 1]}", "Quarter as an ISO 8601 date range", e.source)
                continue
            m = re.match(r"^([\d,.]+)\s*(bn|m)$", v, re.I)
            if m:
                n += 1
                add(name, e.key.split(":")[1], e.element, v, f"{float(m[1].replace(',', '')) * (1e9 if m[2].lower() == 'bn' else 1e6):,.0f}", "Scale suffix expanded to a full number", e.source)
        return {"text": f"{n} values standardised to ISO 8601 dates and full-number formats (recorded in the audit trail as notes for the source owners)."}
    if k == "fx":
        used = []
        for e in ints:
            if e.dtype != "Amount":
                continue
            m = re.match(r"^([A-Z]{3})\s*([\d,]+(?:\.\d+)?)", str(e.value))
            if m and m[1] != "USD" and m[1] in FX:
                used.append(m[1])
                add(name, e.key.split(":")[1], e.element, e.value, f"USD {float(m[2].replace(',', '')) / FX[m[1]]:,.0f}", f"Converted at {FX[m[1]]} {m[1]}/USD", e.source)
        if not used:
            return {"text": "All collected amounts are already in USD, the reporting currency; no conversion needed."}
        return {"text": f"{len(used)} amounts converted to USD (reporting currency) at the reference rates configured in Data360 ("
                        + ", ".join(f"{c} {FX[c]}" for c in sorted(set(used))) + " per USD). Confirm the rate source and date with Treasury."}
    if k == "names":
        names = {r.fields.get("Borrower_Name") for r in recs if r.fields.get("Borrower_Name")} | {str(e.value) for e in _els(ds, ["Legal name", "Client legal name", "Rated entity", "Counterparty"])}
        regs = {r.fields.get("Registration_Number") for r in recs if r.fields.get("Registration_Number")}
        return {"text": f"{_plural(len(names), 'name variant')} ({'; '.join(sorted(names)[:4])}) and {_plural(len(regs), 'registration identifier')} mapped to one obligor record for {ds.borrower}."}
    if k == "gaap":
        a = _els(ds, ["Accounting standard", "Basis of preparation", "Consolidation scope"])
        return {"text": f"{len(a)} accounting-basis elements held." if a else "Not completed: no accounting standard, consolidation scope or restatement data is held. Request the borrower's audited accounts with the basis of preparation."}
    if k == "taxo":
        ind = G.get("Industry", {}) or {}
        rat = (G.get("External_Rating") or {}).get("value")
        return {"text": f"Industry \"{ind.get('value', 'n/a')}\" mapped to the internal sector; external rating {rat or 'n/a'} mapped to internal grade {INTERNAL_GRADE.get(rat, 'n/a') if rat else 'n/a'}."}
    if k == "chase":
        items = [r["attribute"] for r in seek["results"] if r["status"] in ("miss", "indirect", "pending")]
        for a in items:
            escalate(f"Obtain {a} for {ds.borrower}", "Missing for the credit memo", "Relationship manager", 10)
        return {"text": f"{len(items)} attributes requested with owners and due dates." if items else "Nothing to chase: every attribute searched was found." if seek["results"] else "Run the Seeker to find missing attributes."}
    if k == "nulls":
        n = 0
        for r in recs:
            for f in VALUE_FIELDS:
                if r.source in GOLD_PRIORITY.get(f, []) and is_blank(r.fields.get(f)):
                    n += 1
                    add(name, r.rid, LABEL[f], "Blank", "Not provided", f"{r.source} is a golden source for this field", r.source)
        for e in ds.live_elements():
            w = validate_element(e.dtype, e.value)
            if w and re.search("Placeholder|options|Empty", w):
                n += 1
                add(name, e.key.split(":")[1], e.element, e.value or "Blank", "Not provided", w, e.source)
        return {"text": f"{n} blank, placeholder or option-list values labelled \"Not provided\". No value was defaulted to zero."}
    if k == "impute":
        return {"text": "No values imputed. Blank values were left as \"Not provided\" pending source data."}
    if k == "tie":
        tied = sum(1 for r in recs if r.rid and r.as_of)
        return {"text": f"{tied} of {len(recs)} external records tied to a record ID and as-of date; {len(ints)} internal values tied to a record ID and their uploaded file. Spreads not re-performed: no audited accounts in scope."}
    if k == "corrob":
        rows = [f"{LABEL[f]} {len({r.source for r in recs if not is_blank(r.fields.get(f)) and not differs(f, r.fields.get(f), G[f]['value'])})}" for f in CRITICAL if G.get(f)]
        return {"text": "Golden values corroborated by independent sources: " + ", ".join(rows) + "."}
    if k == "auth":
        f = _els(ds, ["Original held flag", "Wet-ink flag"])
        y = sum(1 for e in f if str(e.value).startswith("Y"))
        return {"text": f"{y} of {len(f)} originals confirmed held / wet-ink. Issuer confirmation required for the remainder where fraud risk is elevated."}
    if k == "kyc":
        s = [r for r in recs if re.search("sanction", r.source, re.I)]
        old = [r for r in s if r.as_of and (ds.ref_date - r.as_of).days > 30]
        kk = [e for e in _els(ds, ["KYC status"]) if not re.search("approved", str(e.value), re.I)]
        if old:
            escalate("Re-screen sanctions and PEP", f"{len(old)} screening(s) older than 30 days", "Financial Crime Compliance", 2)
        if kk:
            escalate("Refresh KYC", f"{len(kk)} KYC record(s) not approved ({', '.join(sorted({str(e.value) for e in kk}))})", "KYC Operations", 5)
        return {"text": f"{len(old)} of {len(s)} sanctions screenings re-requested; {len(kk)} KYC records sent for refresh."}
    if k == "expo":
        vals = [parse_number(e.value) for e in _els(ds, ["Total commitment"])]
        vals = [v for v in vals if v is not None]
        g = (G.get("Facility_Amount") or {}).get("value")
        return {"text": f"Golden facility amount {fmt('Facility_Amount', g) if g else 'n/a'}; {len(vals)} loan-system commitments found ({sum(1 for v in vals if g and differs('Facility_Amount', v, g))} differ). "
                        "Undrawn, derivative and guarantee exposure to be reconciled to the systems of record."}
    if k == "rating":
        r = _els(ds, ["Obligor rating", "Probability of default (PD)", "Loss given default (LGD)"])
        g = G.get("External_Rating")
        return {"text": f"{len(r)} rating model inputs found; external golden rating {g['display'] + ' (' + g['source'] + ')' if g else 'n/a'}. Overrides: none recorded."}
    if k == "outlier":
        n = 0
        for r in recs:
            for f in ("Revenue", "EBITDA"):
                gv = (G.get(f) or {}).get("value")
                a, b = parse_number(r.fields.get(f)), parse_number(gv)
                if a is not None and b and abs(a - b) / abs(b) > 0.15:
                    n += 1
                    add(name, r.rid, LABEL[f], fmt(f, r.fields.get(f)), "Flagged outlier", f"More than 15% from golden {fmt(f, gv)}", r.source)
        return {"text": f"{n} revenue or EBITDA values more than 15% away from the golden value flagged."}
    if k == "trend":
        rv = [parse_number(r.fields.get("Revenue")) for r in recs]
        rv = [v for v in rv if v]
        if len(rv) < 2:
            return {"text": "Not enough periods for trend analysis."}
        lo, hi = min(rv), max(rv)
        return {"text": f"Revenue observations range {fmt('Revenue', lo)} to {fmt('Revenue', hi)} ({round((hi - lo) / lo * 100)}% spread) across {len(rv)} observations; movements above 10% referred for explanation."}
    if k == "oneoff":
        return {"text": "Not completed: no exceptional items or adjustments are held. Request management's bridge from reported to adjusted EBITDA."}
    if k == "material":
        return {"text": "Cleaning prioritised on identity, rating, facility amount, maturity and sanctions fields, which can change the decision, rating, pricing or structure."}
    if k == "residual":
        inc = sum(1 for r in recs if r.flag in ("INCOMPLETE", "STALE") or ds.is_stale(r))
        return {"text": f"{inc} incomplete or stale records and all escalated items to be disclosed in the credit memo, with mitigants."}
    if k == "version":
        return {"text": "Data pack v1.1 (cleaned) issued as the single controlled version; v1.0 (as sourced) retained."}
    if k == "sod":
        return {"text": f"Preparer: {ctx.get('user', 'Data360 Clean')} (automated run). Independent reviewer: pending assignment."}
    if k == "attest":
        rm = _els(ds, ["RM name"])
        return {"text": f"Attestation requested from the RM{' (' + str(rm[0].value) + ')' if rm else ''} and the credit analyst; status pending."}
    if k == "mnpi":
        m = sum(1 for e in ints if re.search("MNPI|Legal privilege", e.sensitivity or ""))
        return {"text": f"{m} MNPI or legally privileged elements restricted to wall-crossed users."}
    if k == "pdpa":
        p = [e for e in ints if re.search("Personal data", e.sensitivity or "")]
        for e in p:
            add(name, e.key.split(":")[1], e.element, "(personal data)", re.sub(r"[A-Za-z0-9]", "•", str(e.value))[:24], "Personal data masked (PDPA)", e.source)
        return {"text": f"{len(p)} personal-data elements masked under PDPA in the data pack; retention follows the source policy."}
    if k == "root":
        by = Counter(r.source for r in ds.records if r.flag and r.flag != "VALIDATED")
        return {"text": "Recurring issues reported to owners: " + (", ".join(f"{s} {n}" for s, n in by.most_common()) or "none") + "."}
    return {"text": "Not available."}


# ======================= Normalise · further definitions =======================
NORM_CATS = [
    ["Metric definitions", [["Standard formula library", "One approved formula per metric with numerator, denominator and source field.", "formula"],
                            ["Calculation basis", "LTM, annualised or point-in-time; average or period-end balances.", "basis"],
                            ["Reported vs adjusted", "EBITDA add-backs, IFRS 16 leases, gross vs net debt.", "adjusted"],
                            ["Units, rounding and precision", "Decimals, x vs %, bps and rounding rules.", "units"]]],
    ["KPI framework", [["KPI owner, frequency and target", "Who signs off each KPI and how often it refreshes.", "owner"],
                       ["Portfolio KPIs", "Watchlist %, NPL ratio, covenant breaches, concentration.", "portfolio"]]],
    ["Master data", [["Group hierarchy and connected parties", "Parent, sponsor, guarantors and SPVs.", "group"],
                     ["Reference data", "ISO 3166 countries, ISO 4217 currencies, industry crosswalk, rating scale map.", "refdata"],
                     ["Survivorship rules and stewards", "Which source wins per field, and who maintains it.", "survive"]]],
    ["Semantic layer", [["Role-based access and masking", "Who can see which tier of data.", "access"],
                        ["Versioning and change approval", "Effective-dated definitions with an approval log.", "versioning"]]],
    ["Regulatory alignment", [["BCBS 239 aggregation principles", "Accuracy, completeness, timeliness and adaptability of risk data.", "bcbs"],
                              ["IFRS 9 definitions", "SICR, staging and default definitions.", "ifrs9"],
                              ["MAS 610 / 637 / 649 definitions", "Regulatory return definitions and mappings.", "mas"],
                              ["Large exposure and connected parties", "Connected-party grouping and exposure limits.", "largeexp"]]],
]
NORM_ACT = {n: {"n": n, "d": d, "k": k, "cat": cat} for cat, items in NORM_CATS for n, d, k in items}


def norm_pick(name: str, ds: Dataset, out: dict, assess: dict | None, n_borrowers: int = 1) -> dict:
    k = NORM_ACT[name]["k"]
    M = (out.get("Metrics") or {}).get("rows", [])
    K = (out.get("KPIs") or {}).get("rows", [])
    if k == "formula":
        return {"text": f"{len(M)} formulas published in the metric library; each names its inputs and golden source." if M else "Select Metrics to publish the formula library."}
    if k == "basis":
        return {"text": "Income measures on an LTM basis; balances at period-end; facility measures point-in-time; ratios use period-end debt over LTM EBITDA."}
    if k == "adjusted":
        return {"text": "Only reported EBITDA is held, so adjusted EBITDA cannot be built. IFRS 16 lease liabilities: not identified. Request the add-back schedule from the borrower."}
    if k == "units":
        return {"text": "Ratios to 2 decimals with \"x\"; percentages to 1 decimal; spreads in bps; amounts in USD millions to 1 decimal; half-up rounding."}
    if k == "owner":
        return {"text": f"Owners: {', '.join(sorted({r[3] for r in K}))}. Frequencies range from daily to quarterly." if K else "Select KPIs to set owners."}
    if k == "portfolio":
        return {"text": f"Portfolio KPIs defined across {n_borrowers} borrowers: watchlist %, NPL ratio, covenant breach count, top-20 concentration. Values need every borrower assessed."}
    if k == "group":
        g = _els(ds, ["Ultimate parent", "Parent-subsidiary link", "Sponsor name", "Guarantor name", "SPV name"])
        return {"text": f"{len(g)} hierarchy elements found (parent, sponsor, guarantor, SPV)" + ("; linked to the obligor record." if g else "; upload Loan systems data to build the hierarchy.")}
    if k == "refdata":
        return {"text": "ISO 3166 countries, ISO 4217 currencies and the agency-to-internal rating map ("
                        + ", ".join(f"{a}→{b}" for a, b in list(INTERNAL_GRADE.items())[:8]) + ", …) applied."}
    if k == "survive":
        return {"text": "Survivorship: " + "; ".join(f"{LABEL[f]}: {p[0]}" for f, p in GOLD_PRIORITY.items() if p) + ". Stewards from the ownership register."}
    if k == "access":
        tiers = Counter((e.sensitivity or "Internal").split(" – ")[0] for e in ds.elements)
        return {"text": "Access by tier: " + ", ".join(f"{t} {n}" for t, n in tiers.most_common()) + ". Restricted tiers masked for users without clearance."}
    if k == "versioning":
        return {"text": f"Definitions v1.0 effective {ds.ref_date.isoformat()}; changes need owner approval and are effective-dated."}
    if k == "bcbs":
        conf = (assess or {}).get("overall", {}).get("score")
        return {"text": f"BCBS 239: accuracy and completeness evidenced by Assess (confidence {conf if conf is not None else '—'}%), timeliness by refresh cycles, adaptability by the semantic layer."}
    if k == "ifrs9":
        return {"text": f"{len(_els(ds, ['ECL stage', 'SICR flag', 'Staging date']))} IFRS 9 elements found; stage, SICR and default definitions aligned to the bank standard."}
    if k == "mas":
        e = _els(ds, ["Return form"])
        return {"text": f"MAS returns referenced: {', '.join(sorted({str(x.value) for x in e})) or 'none held'}; metric definitions mapped to return line items."}
    if k == "largeexp":
        return {"text": f"{len(_els(ds, ['Counterparty group', 'Exposure % of Tier 1 capital']))} large-exposure elements found; connected parties grouped under the obligor record."}
    return {"text": "Not available."}


def catalogue() -> dict:
    return {"assess": [{"cat": c, "items": [{"n": i[0], "d": i[1]} for i in items]} for c, items in CRIT_CATS],
            "clean": [{"cat": c, "items": [{"n": i[0], "d": i[1]} for i in items]} for c, items in CLEAN_CATS],
            "normalise": [{"cat": c, "items": [{"n": i[0], "d": i[1]} for i in items]} for c, items in NORM_CATS]}
