"""Step 5 · Credit memo. Maps every template field to its golden value, source and confidence,
analyses the financials, checks compliance against the active rules, drafts a decision, and
lays the memo out in the bank's template with a source on every value.

Ported from the demo console. Internal values are looked up by data-element name in the
uploaded data dictionaries; anything not held is marked "Not sourced" and goes to the
exception register rather than being guessed.
"""
from __future__ import annotations

import re
from datetime import date

from .confidence import STD, stages as conf_stages
from .core import Dataset, eligible, golden
from .normalise import p as fmtP, usd as fmtUSD, x as fmtX
from .policies import POLICY, rule_of_check
from .reference import INTERNAL_GRADE as RATING_MAP, LABEL, RELIABILITY
from .registry import owner_of
from .values import fmt, is_blank, parse_number, parse_percent, validate_element

SECTIONS = [
    ("1", "Executive Summary", True, "Credit request, recommendation, committee summary"),
    ("2", "Borrower Profile", True, "Identity, ownership, group structure"),
    ("3", "Relationship Overview", False, "Exposure, revenue, prior credit events"),
    ("4", "Facility Overview", True, "Structure, drawn and undrawn, tranches"),
    ("5", "Financial Assessment", True, "Performance trend, strengths, concerns"),
    ("6", "Credit Risk Assessment", True, "Ratings, PD, LGD, EAD, risk RAG"),
    ("7", "Collateral & Security Assessment", False, "Security package, valuation, LTV"),
    ("8", "Covenant Assessment", True, "Thresholds, actuals, headroom"),
    ("9", "Industry & Market Assessment", False, "Industry view and external intelligence"),
    ("10", "Treasury & Funding Assessment", False, "Cost of funds, liquidity, hedging"),
    ("11", "Legal Review", False, "Documentation and authority checks"),
    ("12", "Compliance Assessment", True, "KYC, AML, sanctions"),
    ("13", "ESG Assessment", False, "ESG, climate, transition and physical risk"),
    ("14", "Data Quality & Assurance", True, "Confidence dashboard, golden sources, exceptions"),
    ("15", "AI Assurance", False, "Automated checks and AI metrics"),
    ("16", "Credit Recommendation", True, "Decision, conditions precedent and subsequent"),
    ("17", "Approval Workflow", True, "Approver chain with decisions and dates"),
    ("A", "Appendix A – Source Traceability", False, "Every value with source, timestamp, owner"),
    ("B", "Appendix B – Data Quality Dashboard", False, "Quality scores by data domain"),
    ("C", "Appendix C – Reconciliation Log", False, "Values compared and golden value chosen"),
    ("D", "Appendix D – Assurance Certificate", False, "Assurance statement and final confidence"),
]
SEC = {s[0]: {"no": s[0], "t": s[1], "core": s[2], "d": s[3]} for s in SECTIONS}
CORE = [s[0] for s in SECTIONS if s[2]]
STAGES = [
    {"n": "5.1", "t": "Prepare", "d": "Map every template field to its golden value, source and confidence"},
    {"n": "5.2", "t": "Analyse", "d": "Calculate ratios, trends, covenant headroom and risk ratings"},
    {"n": "5.3", "t": "Rate against compliance", "d": "Check KYC, AML, sanctions, legal authority, covenants and credit policy"},
    {"n": "5.4", "t": "Present", "d": "Assemble the memo in the bank's template with a source on every value"},
    {"n": "5.5", "t": "Review and retain", "d": "Approval chain, reviewer edits, final version and evidence pack"},
]
APPROVERS = ["Relationship Manager", "Credit Officer", "Head of Credit", "CRO Delegate", "Credit Committee"]
DECISIONS = ["Approve", "Approve with conditions", "Refer", "Decline"]
CONF_N = {"High": 95, "Medium": 80, "Low": 60}
SOR = ["Loan systems", "Risk platforms", "CRM tools", "Treasury systems", "Legal systems"]
AUTO_KINDS = ["golden", "external", "internal", "calc", "draft"]
DOMAINS = [["Borrower", ["2"], "Corporate Registry"], ["Facility", ["4", "7"], "Bloomberg"], ["Ratings", ["6"], "Moody's"],
           ["Financials", ["5", "8"], "Bureau van Dijk"], ["Compliance", ["12", "11"], "Regulatory / Sanctions Feed"], ["ESG", ["13"], "ESG Database"]]
RAGW = {"g": "Green", "a": "Amber", "r": "Red", "na": "No data"}
WORD = {"high": "High", "med": "Medium", "low": "Low", "na": "—"}


def new_state() -> dict:
    return {"on": list(CORE), "extra": [], "done": 0, "facility": "", "built_at": None, "built_version": None,
            "approvals": [{"role": r, "name": "", "decision": "", "comment": "", "date": ""} for r in APPROVERS],
            "edits": [], "retained": None}


def selected(st: dict) -> list[str]:
    on = set(st.get("on") or []) | set(st.get("extra") or [])
    return [s[0] for s in SECTIONS if s[0] in on]


def num_of(s) -> float | None:
    m = re.search(r"-?\d+(\.\d+)?", str(s if s is not None else "").replace(",", ""))
    return float(m.group(0)) if m else None


def _join_vals(vals):
    return [v for v in dict.fromkeys(vals) if v]


def mk(**o) -> dict:
    f = {"conf": None, "kind": "missing", "src": "—", "srcFull": "", "rec": "", "when": "", "note": "", "v": "Not sourced"}
    f.update(o)
    return f


def build(ds: Dataset, full: Dataset, borrower_id: int, clean: dict, assess: dict | None, norm: dict | None, seek: dict | None,
          rules_on: list[str], st: dict, owners: dict | None = None) -> dict:
    """The memo model: fields F (section|label -> value with source/confidence), analysis, checks, decision."""
    ref_date = ds.ref_date
    ymd = ref_date.isoformat()
    c = ds.borrower
    recs = [r for r in ds.live() if eligible(r)]
    G = golden(ds)
    crit = clean["summary"].get("Validate critical information") if clean else None
    failed = {r["key"] for r in (crit["rows"] if crit else []) if r["status"] == "Failed"}
    escal = clean["escalations"] if clean else []
    ELS = [e for e in full.elements if not validate_element(e.dtype, e.value)]

    def ints(el):
        el = el.lower()
        return [e for e in ELS if e.element.strip().lower() == el]

    def gv(f):
        return G[f]["value"] if G.get(f) else None

    def conf_of(src):
        r = RELIABILITY.get(src, 0.8)
        return "High" if r >= 0.85 else "Medium" if r >= 0.7 else "Low"

    def fG(f, fm=None):
        g = G.get(f)
        if not g:
            return mk(note=f"No validated {LABEL[f].lower()} in any source")
        fb = g["rule"] != "golden-source"
        return mk(v=fm(g["value"]) if fm else g["display"], raw=g["value"], src=g["source"], srcFull=g["source"], rec=g["record"], when=g["as_of"] or "",
                  kind="golden", conf="Medium" if f in failed or fb else "High",
                  note="Other sources disagree; escalated in Clean" if f in failed else g["why"] if fb else "Golden source, latest validated record")

    def fI(el, multi=False, mx=3, fm=None):
        xs = ints(el)
        if not xs:
            return mk(note=f"{el} not held in any internal source")
        vals = _join_vals(str(x.value) for x in xs)
        s = xs[0].source
        many = len(vals) > 1
        fm = fm or (lambda v: v)
        return mk(v="; ".join(fm(v) for v in vals[:mx]) + (f" (+{len(vals) - mx} more)" if len(vals) > mx else ""), vals=vals,
                  src=", ".join(dict.fromkeys(x.source for x in xs)), srcFull=s, rec=", ".join(x.key.split(":")[1] for x in xs[:3]), kind="internal",
                  conf="Low" if many and not multi else "High" if s in SOR else "Medium",
                  note=(f"{len(vals)} values, one per facility or record" if multi else f"{len(vals)} different values held; reviewer to confirm") if many else f"Single value in {s}")

    def fC(v, inputs, note):
        if v is None or v == "":
            return mk(v="Not calculable", note="Inputs missing: " + note)
        cs = [i.get("conf") for i in inputs if i and i.get("conf")]
        return mk(v=v, kind="calc", src="Calculated", conf="Low" if not cs or "Low" in cs else "Medium" if "Medium" in cs else "High", note=note)

    def fM(note):
        return mk(v="RM to complete", kind="manual", src="Manual", note=note)

    def fA(v, src, note, conf="Medium"):
        return mk(v=v, kind="draft", src=src, conf=conf, note=note)

    seek_res = {r["attribute"]: r for r in (seek or {}).get("results", [])}

    def fS(attr):
        r = seek_res.get(attr)
        if r is None:
            from .source import ATTRS, search
            r = search(full, attr, []) if attr in ATTRS else None
        good = [v for v in (r["values"] if r else []) if not validate_element("Text", v["value"])]
        if not good:
            return mk(note="Only placeholder values found" if r and r["values"] else f"The Seeker found no {attr}")
        h = next((h for h in r["hits"] if str(h["value"]) == str(good[0]["value"])), r["hits"][0])
        from .source import ATTRS
        multi_ok = bool(ATTRS.get(attr, {}).get("multi"))
        return mk(v="; ".join(re.sub(r":.*$", "", str(v["value"])) for v in good[:4]) if multi_ok else good[0]["value"], src=h["location"], srcFull=h["location"],
                  rec=h["record"], when=h["as_of"] or "", kind="internal" if h["zone"] == "Internal" else "external",
                  conf="Low" if len(good) > 1 and not multi_ok else "Medium",
                  note=f"{len(good)} values found by the Seeker; most frequent shown" if len(good) > 1 and not multi_ok else "Found by the Seeker")

    def gold_field(f, prio):
        c_ = sorted([r for r in recs if r.source in prio and not is_blank(r.fields.get(f))], key=lambda r: (prio.index(r.source), -(r.as_of.toordinal() if r.as_of else 0)))
        if not c_:
            return None
        r = c_[0]
        raw = r.fields[f]
        v = parse_percent(raw) if f in ("Interest_Rate", "Margin") else parse_number(raw) if f not in ("Default_Flag",) else raw
        return {"v": v if v is not None else raw, "src": r.source, "id": r.rid, "when": r.as_of.isoformat() if r.as_of else ""}

    F: dict[str, dict] = {}

    def put(sec, label, f):
        f = dict(f)
        f.update(sec=sec, label=label, key=f"{sec}|{label}")
        F[f["key"]] = f
        return f

    def first(el):
        xs = ints(el)
        return xs[0].value if xs else None

    # ---- identity and parties
    ref = f"CM-{ref_date.year}-{borrower_id:04d}"
    fac_ids = _join_vals([x for x in (list(ds.facility_ids) + [e.value for e in ints("Facility ID")]) if str(x).startswith("FAC-")])
    fac_in = (st.get("facility") or "").strip()
    rm = ""
    for e in ints("Attendees"):
        m = re.search(r";\s*([^;(]+?)\s*\((?:\w+\s)?RM", str(e.value))
        if m:
            rm = m.group(1).strip()
            break
    put("0", "Borrower", fG("Borrower_Name"))
    put("0", "Facility ID", mk(v=fac_in, kind="manual", src="User input", conf="High", note="Entered on the Source screen") if fac_in else fI("Facility ID", multi=True, mx=4))
    t1 = fI("Deal reference", multi=True)
    put("0", "Transaction Name", t1 if t1["kind"] != "missing" else fI("Deal code name", multi=True))
    put("0", "Relationship Manager", mk(v=rm, kind="internal", src="CRM tools", srcFull="CRM tools", conf="Medium", note="Named as RM in CRM meeting attendees") if rm else fM("RM not named in CRM"))
    put("0", "Credit Officer", fM("Assigned at review (5.5)"))
    put("0", "Risk Officer", fM("Assigned at review (5.5)"))

    # ---- 2 borrower
    put("2", "Borrower Name", fG("Borrower_Name"))
    put("2", "Legal Entity Name", fI("Legal name"))
    put("2", "Registration Number", fG("Registration_Number"))
    put("2", "LEI", fS("LEI (Legal Entity Identifier)"))
    put("2", "Tax ID", fS("Tax ID"))
    put("2", "Country of Incorporation", fG("Country"))
    put("2", "Operating Countries", fS("Operating Countries"))
    put("2", "Industry Sector", fG("Industry"))
    put("2", "SIC / NAICS Code", fI("Industry code"))
    put("2", "Date Established", fS("Date Established"))
    put("2", "Website", fS("Website"))
    put("2", "Organisation Type", fS("Organisation Type"))
    put("2", "Listed / Private", fS("Listed / Private Status"))
    grp, parent_id, guar, ubo, ubo_pct = fI("Counterparty group"), fI("Parent client ID"), fI("Guarantor name", multi=True), fG("Beneficial_Owner"), fI("UBO ownership percentage")
    spvs = _join_vals(e.value for e in ints("Issuing company") + ints("Registered owner"))
    holdco = fI("Registered holder")
    put("2", "Parent Company", {**grp, "v": grp["v"] + (f" (CRM parent {parent_id['v']})" if parent_id["kind"] != "missing" else "")} if grp["kind"] != "missing" else parent_id)
    put("2", "Sponsor", fI("Sponsor name"))
    put("2", "Guarantor", guar)
    put("2", "UBO", ubo)
    put("2", "UBO ownership %", ubo_pct)
    put("2", "SPV", mk(v="; ".join(spvs), kind="internal", src="Physical records", srcFull="Physical / hard-copy records", conf="Medium",
                       note="Share certificates and land titles held in the vault") if spvs else mk(note="No SPV records"))

    # ---- 3 relationship
    eads = [v for v in (parse_number(e.value) for e in ints("Exposure at default (EAD)")) if v is not None]
    status = [e.value for e in ints("Loan status")]
    dpd = max([0] + [num_of(e.value) or 0 for e in ints("Days past due")])
    decl = [e for e in ints("Decision") if re.search(r"declin", str(e.value), re.I)]
    ch11, ews = ints("Proceeding type"), ints("Covenant breached")
    events = [f"Loan status {s}" + (f" ({int(dpd)} days past due)" if dpd else "") for s in status if s != "Performing"]
    events += [f"Credit committee decision Declined ({first('Decision date') or 'date not held'})" for _ in decl]
    events += [f"{e.value} proceeding (Legal)" for e in ch11]
    events += [f"Early-warning alert: {e.value} covenant breached ({first('Breach magnitude') or ''})" for e in ews]
    ld = fI("Lead date")
    put("3", "Relationship Start Date", {**ld, "conf": "Low", "note": "Not held; first CRM lead date used as a proxy"} if ld["kind"] != "missing" else mk(note="Not held"))
    put("3", "Total Exposure", fC(fmtUSD(sum(eads)) if eads else None, [fI("Exposure at default (EAD)", multi=True)], f"Sum of {len(eads)} EAD values (Risk platforms)"))
    rev_, raroc, hurdle = fI("Revenue by product", multi=True), fI("RAROC"), fI("Hurdle rate")
    if rev_["kind"] != "missing" or raroc["kind"] != "missing":
        base = raroc if raroc["kind"] != "missing" else rev_
        put("3", "Revenue Contribution", {**base, "v": "; ".join(x for x in [rev_["v"] if rev_["kind"] != "missing" else None,
                                                                             f"RAROC {raroc['v']}" + (f" vs hurdle {hurdle['v']}" if hurdle["kind"] != "missing" else "") if raroc["kind"] != "missing" else None] if x)})
    else:
        put("3", "Revenue Contribution", rev_)
    put("3", "Number of Facilities", fC(str(len(fac_ids)) if fac_ids else None, [mk(conf="High")], ", ".join(fac_ids)))
    put("3", "Prior Credit Events", mk(v="; ".join(events), kind="internal", src="Loan, Docs, Legal, Risk", srcFull="Loan systems", conf="Medium",
                                       note=f"{len(events)} events across internal systems") if events else mk(v="None recorded", kind="internal", src="Loan systems", conf="Medium"))
    wl, alert = fI("Watchlist status"), fI("Alert ID")
    put("3", "Watchlist Status", wl if wl["kind"] != "missing" else {**alert, "v": f"Not held; early-warning alert {alert['v']} open", "conf": "Low"} if alert["kind"] != "missing" else wl)
    topics, follow, meet = [e.value for e in ints("Topics discussed")], [e.value for e in ints("Follow-up actions")], [e.value for e in ints("Meeting summary")]
    put("3", "Relationship Manager Commentary", fA(f"Draft from CRM call reports: discussions on {' and '.join(topics).lower()}; follow-ups: {'; '.join(follow).lower()}. {'. '.join(meet)}. RM to confirm.",
                                                  "CRM tools", "AI draft from call reports; RM to confirm") if topics else fM("No call reports held"))

    # ---- 4 facility
    fac = parse_number(gv("Facility_Amount")) if gv("Facility_Amount") else None
    outp = parse_number(gv("Outstanding_Principal")) if gv("Outstanding_Principal") else None
    put("4", "Facility Type", fI("Facility type", multi=True))
    put("4", "Facility Amount", fG("Facility_Amount"))
    put("4", "Drawn Amount", fG("Outstanding_Principal"))
    put("4", "Undrawn Amount", fC(fmtUSD(fac - outp) if fac is not None and outp is not None else None, [F["4|Facility Amount"], F["4|Drawn Amount"]], "Facility amount − drawn amount"))
    put("4", "Currency", fI("Facility currency") if ints("Facility currency") else fG("Currency"))
    put("4", "Maturity Date", fG("Maturity_Date"))
    rp, pp = fI("Repayment profile"), fI("Prepayment type")
    put("4", "Repayment Profile", rp if rp["kind"] != "missing" else {**pp, "v": f"{pp['v']} prepayment; amortisation schedule not held", "conf": "Low"} if pp["kind"] != "missing" else mk(note="Not held"))
    put("4", "Facility Purpose", fI("Facility purpose", multi=True))
    trs = fI("Tranche seniority")
    put("4", "Tranche A", trs if trs["kind"] != "missing" else mk(note="No tranche records in Loan systems"))
    put("4", "Tranche B", mk(note="No tranche records in Loan systems"))

    # ---- 5 financial trend
    PRI = {"Bureau van Dijk": 0, "Capital IQ": 1, "D&B": 2}
    fin = [r for r in recs if r.source in PRI and not is_blank(r.fields.get("Revenue")) and r.as_of]
    months = sorted({r.as_of.isoformat()[:7] for r in fin})[-3:]

    def col_rec(m, f):
        xs = [r for r in fin if r.as_of.isoformat().startswith(m) and not is_blank(r.fields.get(f))]
        xs.sort(key=lambda r: (PRI[r.source], -r.as_of.toordinal()))
        return xs[0] if xs else None

    def series(f):
        out = []
        for m in months:
            r = col_rec(m, f)
            out.append(parse_number(r.fields[f]) if r else None)
        return out

    def m_label(m):
        return date.fromisoformat(m + "-01").strftime("%b %Y")

    S = {"rev": series("Revenue"), "ebitda": series("EBITDA"), "nd": series("Net_Debt")}
    S["margin"] = [S["ebitda"][i] / v if v and S["ebitda"][i] else None for i, v in enumerate(S["rev"])]
    S["lev"] = [v / S["ebitda"][i] if v and S["ebitda"][i] else None for i, v in enumerate(S["nd"])]
    thr_l, act_l, rep_head = [e.value for e in ints("Covenant threshold")], [e.value for e in ints("Actual value")], [e.value for e in ints("Headroom")]
    icr_i = next((i for i, t in enumerate(thr_l) if "ICR" in str(t)), -1)
    ICR = num_of(act_l[icr_i]) if icr_i >= 0 and icr_i < len(act_l) else None

    def trend(a, up=True):
        v = [x for x in a if x is not None]
        if len(v) < 2:
            return "Insufficient data"
        ch = (v[-1] - v[0]) / abs(v[0]) if v[0] else 0
        if abs(ch) < 0.02:
            return "Stable"
        sign = "+" if ch > 0 else ""
        return f"Improving ({sign}{ch * 100:.1f}%)" if (ch > 0) == up else f"Weakening ({sign}{ch * 100:.1f}%)"

    fin_rows = [["Revenue", [fmtUSD(v) for v in S["rev"]], trend(S["rev"])], ["EBITDA", [fmtUSD(v) for v in S["ebitda"]], trend(S["ebitda"])],
                ["EBITDA Margin", [fmtP(v) for v in S["margin"]], trend(S["margin"])], ["Net Debt", [fmtUSD(v) for v in S["nd"]], trend(S["nd"], False)],
                ["Interest Cover", [f"{ICR:.2f}x" if i == len(months) - 1 and ICR is not None else "—" for i in range(len(months))], "Current only (Loan systems ICR test)" if ICR is not None else "Not held"],
                ["Leverage", [fmtX(v) for v in S["lev"]], trend(S["lev"], False)]]
    for r in fin_rows:
        vals = [v for v in r[1] if v != "—"]
        put("5", r[0], mk(v=vals[-1], kind="calc", src="Loan systems" if r[0] == "Interest Cover" else "Bureau van Dijk / Capital IQ / D&B",
                          conf="Low" if r[0] == "Interest Cover" else "Medium", note=r[2]) if vals else mk(note="No dated observations"))
    put("5", "FY-2 / FY-1 annual accounts", mk(note="Audited annual accounts not held; trend uses monthly validated observations"))

    # ---- 6 credit risk
    obl_r, fac_r, ext_r = fI("Obligor rating"), fI("Facility rating"), fG("External_Rating")
    pd_, lgd = fI("Probability of default (PD)", multi=True), fI("Loss given default (LGD)", multi=True)
    els_ = [v for v in (parse_number(e.value) for e in ints("Expected loss")) if v is not None]
    put("6", "Internal Rating", {**obl_r, "v": f"Obligor {obl_r['v']}" + (f" · facility {fac_r['v']}" if fac_r["kind"] != "missing" else "")} if obl_r["kind"] != "missing" else obl_r)
    ext_raw = gv("External_Rating")
    put("6", "External Rating", ext_r if ext_r["kind"] == "missing" else {**ext_r, "v": f"{ext_r['v']} ({G['External_Rating']['source']}) → internal {RATING_MAP.get(ext_raw, '?')}"})
    put("6", "PD", pd_)
    put("6", "LGD", lgd)
    put("6", "EAD", dict(F["3|Total Exposure"]))
    put("6", "Expected Loss", fC(fmtUSD(sum(els_)) if els_ else None, [mk(conf="High")], f"Sum of {len(els_)} expected-loss values (Risk platforms)"))

    # ---- covenants
    cov = gold_field("Leverage_Covenant", ["Capital IQ", "Bureau van Dijk", "Bloomberg"])
    nd = gold_field("Net_Debt", ["Bureau van Dijk", "Capital IQ"])
    ebitda = parse_number(gv("EBITDA")) if gv("EBITDA") else None
    lev = nd["v"] / ebitda if nd and ebitda else None
    coll = gold_field("Collateral_Value", ["Bureau van Dijk", "Capital IQ"])
    ltv = outp / coll["v"] if coll and coll["v"] and outp is not None else None
    ltv_thr = num_of(first("LTV covenant threshold"))
    ltv_rep = num_of(first("LTV ratio"))
    ews_t = [str(e.value) for e in ews]

    def cov_row(name, threshold, actual, is_max, note=""):
        if threshold is None or actual is None:
            return {"name": name, "threshold": threshold, "actual": actual, "isMax": is_max, "head": None, "status": "Not tested", "note": note}
        h = (threshold - actual) / threshold if is_max else (actual - threshold) / threshold
        conflict = any(t in name or (t == "ICR" and name == "Interest Cover") for t in ews_t)
        return {"name": name, "threshold": threshold, "actual": actual, "isMax": is_max, "head": h,
                "status": "Breach" if h < 0 else "Conflict" if conflict else "Tight" if h < 0.1 else "Compliant", "note": note}

    dscr_i = next((i for i, t in enumerate(thr_l) if "DSCR" in str(t)), -1)
    COV = [
        cov_row("Leverage", cov["v"] if cov else None, lev, True, f"Covenant from {cov['src']}; actual = net debt ÷ EBITDA" if cov else ""),
        cov_row("DSCR", num_of(thr_l[dscr_i]) if dscr_i >= 0 else None, num_of(act_l[dscr_i]) if 0 <= dscr_i < len(act_l) else None, False,
                f"Reported headroom {rep_head[dscr_i]}" if 0 <= dscr_i < len(rep_head) else ""),
        cov_row("Interest Cover", num_of(thr_l[icr_i]) if icr_i >= 0 else None, ICR, False,
                f"Early-warning alert reports {', '.join(ews_t)} breach: {first('Breach magnitude') or ''}" if ews else ""),
        cov_row("LTV", ltv_thr / 100 if ltv_thr is not None else None, ltv, True, f"Loan systems reports {ltv_rep:g}% on its own valuation" if ltv_rep is not None else ""),
    ]

    def fmt_cov(r, v):
        if v is None:
            return "—"
        return fmtP(v) if r["name"] == "LTV" else f"{v:.2f}x"

    for r in COV:
        put("8", r["name"], mk(note="Threshold or actual not held") if r["status"] == "Not tested" else
            mk(v=f"{fmt_cov(r, r['actual'])} vs {'≤' if r['isMax'] else '≥'} {fmt_cov(r, r['threshold'])} ({r['status']})", kind="calc",
               src="Capital IQ / calculated" if r["name"] == "Leverage" else "Loan systems / calculated" if r["name"] == "LTV" else "Loan systems",
               conf="Low" if r["status"] == "Conflict" else "Medium", note=r["note"]))

    # ---- 7 collateral
    shares = len(ints("Certificate number"))
    blank = sum(1 for e in ints("Blank transfer form held flag") if str(e.value).startswith("Y"))
    mort = [e for e in ints("Security type") if re.search("mortgage", str(e.value), re.I)]
    perf, enc = ints("Perfection status"), ints("Encumbrances recorded")
    g_amts = [v for v in (parse_number(e.value) for e in ints("Guarantee amount")) if v is not None]
    put("7", "Share Pledge", mk(v=f"{shares} share certificates held" + (f" with {blank} blank transfer forms" if blank else "") + " (vault)", kind="internal", src="Physical records",
                                srcFull="Physical / hard-copy records", conf="Medium", note="Original certificates in vault") if shares else mk(note="No share certificates held"))
    put("7", "Mortgage", mk(v="; ".join(x for x in [f"{len(mort)} mortgage {str(perf[0].value).lower() if perf else ''}".strip() if mort else None, *[e.value for e in enc]] if x),
                            kind="internal", src="Loan systems, Physical records", srcFull="Loan systems", conf="Medium", note="Security register and land titles") if mort or enc else mk(note="No mortgage recorded"))
    put("7", "Assignment of Receivables", mk(note="Not recorded in the security register"))
    put("7", "Account Charge", mk(note="Not recorded in the security register"))
    gtypes = "/".join(dict.fromkeys(e.value for e in ints("Guarantee type")))
    put("7", "Guarantees", mk(v=f"{len(g_amts)} {gtypes} guarantees from {', '.join(guar.get('vals') or ['—'])}, total {fmtUSD(sum(g_amts))}", kind="internal", src="Loan systems",
                              srcFull="Loan systems", conf="High", note="Expiry " + ", ".join(str(e.value) for e in ints("Guarantee expiry"))) if g_amts else mk(note="No guarantees recorded"))
    val_i = [parse_number(e.value) for e in ints("Valuation amount")]
    val_d = sorted(str(e.value) for e in ints("Valuation date"))
    put("7", "Asset Value", mk(v=fmtUSD(coll["v"]), raw=coll["v"], src=coll["src"], srcFull=coll["src"], rec=coll["id"], when=coll["when"], kind="external", conf="Medium",
                               note="Internal valuations: " + ", ".join(fmtUSD(v) for v in val_i if v is not None) if val_i else "") if coll else mk(note="No collateral value"))
    put("7", "Valuation Date", mk(v=f"{val_d[-1]} ({first('Valuation method') or 'method not held'})", kind="internal", src="Loan systems", srcFull="Loan systems", conf="Medium") if val_d else mk())
    put("7", "LTV", fC(fmtP(ltv) if ltv is not None else None, [F["7|Asset Value"], F["4|Drawn Amount"]], "Drawn ÷ asset value" + (f"; Loan systems reports {ltv_rep:g}%" if ltv_rep is not None else "")))
    put("7", "Security Coverage", fC(f"{1 / ltv:.2f}x" if ltv else None, [F["7|Asset Value"], F["4|Drawn Amount"]], "Asset value ÷ drawn amount"))

    # ---- 9 industry and market
    heads, pubs, dist = [str(e.value) for e in ints("Headline")], [str(e.value) for e in ints("Publisher")], [str(e.value) for e in ints("Distress indicator")]
    sent = [v for v in (num_of(e.value) for e in ints("Sentiment score")) if v is not None]
    s_avg = sum(sent) / len(sent) if sent else None
    drivers, krisks, reports = [str(e.value) for e in ints("Key rating drivers")], [str(e.value) for e in ints("Key risks")], [str(e.value) for e in ints("Report title")]
    cds, ytm = fI("CDS spread"), fI("Yield to maturity")
    sector_tags = ", ".join(dict.fromkeys(str(e.value) for e in ints("Sector tag"))) or "none"
    put("9", "Industry Overview", fA(f"{gv('Industry') or 'Industry not held'}; sector tags in news: {sector_tags}.", "Corporate Registry, News", "AI draft"))
    put("9", "Competitive Position", fA(f"Market pricing: 5Y CDS {cds['v']}" + (f", bond yield {ytm['v']}" if ytm["kind"] != "missing" else "") +
                                        f". Rating drivers: {'; '.join(drivers).lower() or 'not held'}.", "Market feeds, Credit agencies", "AI draft") if cds["kind"] != "missing" else fM("No market pricing held"))
    put("9", "Key Risks", fA("; ".join(krisks + [d for d in drivers if re.search("high|weak|low", d, re.I)]) or "None recorded", "Document repositories, Credit agencies", "AI draft"))
    put("9", "Market Outlook", fA(f"{len(heads)} news items (average sentiment {'—' if s_avg is None else f'{s_avg:.2f}'}): {'; '.join(dict.fromkeys(heads))}. "
                                  f"Agency research: {'; '.join(reports[:3]) or 'none'}.", "External news, Credit agencies", "AI draft"))

    def ext_sum(src):
        xs = sorted([r for r in recs if r.source == src], key=lambda r: r.as_of or date.min, reverse=True)
        return xs[0] if xs else None

    bb, ciq, md = ext_sum("Bloomberg"), ext_sum("Capital IQ"), ext_sum("Moody's")
    if bb:
        mg = parse_percent(bb.fields.get("Margin"))
        put("9", "Bloomberg", mk(v=f"Facility {fmtUSD(parse_number(bb.fields.get('Facility_Amount')))}, outstanding {fmtUSD(parse_number(bb.fields.get('Outstanding_Principal')))}, "
                                   f"matures {bb.fields.get('Maturity_Date') or '—'}" + (f", margin {round(mg * 10000)} bps" if mg else ""),
                                 src="Bloomberg", srcFull="Bloomberg", rec=bb.rid, when=bb.as_of.isoformat() if bb.as_of else "", kind="external", conf="High"))
    else:
        put("9", "Bloomberg", mk())
    if ciq:
        lc = parse_number(ciq.fields.get("Leverage_Covenant"))
        put("9", "Capital IQ", mk(v=f"Revenue {fmtUSD(parse_number(ciq.fields.get('Revenue')))}, EBITDA {fmtUSD(parse_number(ciq.fields.get('EBITDA')))}" + (f", leverage covenant {fmtX(lc)}" if lc else ""),
                                  src="Capital IQ", srcFull="Capital IQ", rec=ciq.rid, when=ciq.as_of.isoformat() if ciq.as_of else "", kind="external", conf="Medium"))
    else:
        put("9", "Capital IQ", mk())
    put("9", "Moody's", mk(v=f"Rating {md.fields.get('External_Rating') or '—'}; default flag {md.fields.get('Default_Flag') or '—'}" + (f"; outlook {first('Outlook')}" if first("Outlook") else ""),
                           src="Moody's", srcFull="Moody's", rec=md.rid, when=md.as_of.isoformat() if md.as_of else "", kind="external", conf="High") if md else mk())
    put("9", "Industry Research", fA("; ".join(reports[:4]), "Credit agencies", "Agency sector reports on file") if reports else mk())

    # ---- 10 treasury
    cof = fI("Cost of funds")
    rate = gold_field("Interest_Rate", ["Bloomberg", "Refinitiv"])
    mar = gold_field("Margin", ["Bloomberg", "Refinitiv"])
    cof_n = num_of(cof["v"]) if cof["kind"] != "missing" else None
    carry = round((rate["v"] * 100 - cof_n) * 100) if rate and cof_n is not None else None
    hedges, eff = [str(e.value) for e in ints("Hedge type")], [str(e.value) for e in ints("Effectiveness test result")]
    ftp = fI("FTP rate")
    put("10", "Cost of Funds", {**cof, "v": f"{cof['v']} (FTP {ftp['v']})"} if ftp["kind"] != "missing" and cof["kind"] != "missing" else cof)
    fcur, ften = fI("Funding currency"), fI("Funding tenor")
    put("10", "Funding Currency", {**fcur, "v": f"{fcur['v']}, {ften['v']} tenor"} if ften["kind"] != "missing" else fcur)
    nsfr = fI("NSFR ratio")
    put("10", "Liquidity Impact", {**nsfr, "v": f"Bank NSFR {nsfr['v']}; undrawn {F['4|Undrawn Amount']['v']} is a contingent outflow", "note": "Bank-level ratio, not facility-specific"} if nsfr["kind"] != "missing" else mk())
    hr = fI("Hedging requirement")
    put("10", "Hedging Requirement", hr if hr["kind"] != "missing" else mk(v=f"{len(hedges)} hedges in place ({', '.join(hedges)}); effectiveness {', '.join(eff)}", kind="internal", src="Treasury systems",
                                                                          srcFull="Treasury systems", conf="Medium", note="No hedging requirement in Loan systems") if hedges else mk())
    put("10", "Treasury Assessment", fC(None if carry is None else f"All-in {rate['v'] * 100:.2f}% vs cost of funds {cof['v']}: {'positive' if carry >= 0 else 'negative'} carry of {abs(carry)} bps",
                                       [cof, mk(conf="High")], f"All-in rate from {rate['src'] if rate else '—'}; margin {str(round(mar['v'] * 10000)) + ' bps' if mar else '—'}"))

    # ---- 11 legal
    contract, exe, law = fI("Contract ID"), fI("Execution date"), fI("Governing law", multi=True)
    docs = "; ".join(str(e.value) for e in ints("Documents collected"))
    board = bool(re.search("board resolution", docs, re.I))
    put("11", "Facility Agreement", {**contract, "v": f"{contract['v']} executed {exe['v'] if exe['kind'] != 'missing' else '—'} ({law['v']})"} if contract["kind"] != "missing" else contract)
    sdt = ints("Security document type")
    put("11", "Security Documents", {**fI("Security document type", multi=True), "v": "; ".join(dict.fromkeys(str(e.value) for e in sdt)) + (f"; mortgage {str(perf[0].value).lower()}" if perf else "")} if sdt else mk())
    put("11", "Guarantees", {**F["7|Guarantees"], "sec": "11", "label": "Guarantees", "key": "11|Guarantees"} if g_amts else mk())
    put("11", "Board Resolutions", mk(v="Collected at CDD; not verified against the constitution", kind="internal", src="CRM tools", srcFull="CRM tools", conf="Low", note=docs) if board else mk(note="Not collected"))
    poa = fI("POA expiry")
    put("11", "Powers of Attorney", {**poa, "v": "POA expiring " + poa["v"]} if poa["kind"] != "missing" else mk(note="No power of attorney on file"))
    put("11", "Authorised Signatories", fI("Authorised signatory"))
    put("11", "Corporate Authority", {**F["11|Board Resolutions"], "label": "Corporate Authority", "key": "11|Corporate Authority"} if board else mk())
    put("11", "Seal Validation", fI("Chop / seal type"))
    put("11", "Board Approval", mk(v="Board resolution collected; approval wording not verified", kind="internal", src="CRM tools", srcFull="CRM tools", conf="Low") if board else mk())
    restr = fI("Restructuring plan", multi=True)
    haircut, standstill = [str(e.value) for e in ints("Haircut")], [str(e.value) for e in ints("Standstill period")]
    if ch11 or restr["kind"] != "missing":
        put("11", "Litigation and Restructuring", mk(v="; ".join(x for x in [f"{ch11[0].value} proceeding (officer {first('Appointed officer') or '—'})" if ch11 else None,
                                                                              f"restructuring plan: {restr['vals'][0]}, haircut {'/'.join(haircut)}" if restr["kind"] != "missing" else None,
                                                                              f"standstill {'; '.join(standstill)}" if standstill else None] if x),
                                                     kind="internal", src="Legal systems", srcFull="Legal systems", conf="High"))
    else:
        put("11", "Litigation and Restructuring", mk(v="None recorded", kind="internal", src="Legal systems", conf="Medium"))

    # ---- 12 compliance values
    kyc, aml, pep = [str(e.value) for e in ints("KYC status")], [str(e.value) for e in ints("AML risk rating")], [str(e.value) for e in ints("PEP flag")]
    crm_hits = sum(1 for e in ints("Sanctions hit flag") if str(e.value).startswith("Y"))
    legal_pm = [e for e in ints("Screening result") if re.search("potential|match|hit", str(e.value), re.I) and not re.search("no match", str(e.value), re.I)]
    sanc_esc = [e for e in escal if re.search("sanction", e["item"], re.I)]
    aml_top = next((a for a in ["High", "Medium", "Low"] if a in aml), None)
    next_kyc = sorted(str(e.value) for e in ints("Next KYC review date"))
    put("12", "KYC Complete", mk(v="Yes" if all(re.search("complete|approved|verified", k, re.I) for k in kyc) else f"No – {', '.join(dict.fromkeys(kyc))} (next review {next_kyc[0] if next_kyc else '—'})",
                                 kind="internal", src="CRM tools", srcFull="CRM tools", conf="High") if kyc else mk())
    put("12", "AML Screening", mk(v=f"AML risk {aml_top}; PEP {'Yes' if 'Y' in pep else 'No'}", kind="internal", src="CRM tools", srcFull="CRM tools",
                                  conf="Low" if len(set(aml)) > 1 else "High", note=f"{len(aml)} ratings held: {', '.join(aml)}") if aml else mk())
    put("12", "UBO Validated", {**ubo, "v": f"{ubo['v']} (registry)" + ("; ownership % not held" if ubo_pct["kind"] == "missing" else "; " + ubo_pct["v"]),
                                "conf": "Medium" if ubo_pct["kind"] == "missing" else "High"} if ubo["kind"] != "missing" else ubo)
    put("12", "Adverse Media", mk(v=f"Yes – {len(dist)} distress indicators ({', '.join(dict.fromkeys(dist))}); average sentiment {s_avg:.2f}" if dist else "No adverse items",
                                  kind="internal", src="External news sources", srcFull="External news sources", conf="Medium", note=", ".join(pubs)) if heads else mk())
    sg = fG("Sanctions_Screening")
    put("12", "Sanctions Screening", {**sg, "v": f"Feed: {gv('Sanctions_Screening') or '—'}; internal: " + (f"{len(legal_pm)} potential match (Legal)" if legal_pm else "clear")
                                      + (f", {crm_hits} CRM hit flags" if crm_hits else ""), "conf": "Low" if legal_pm or crm_hits else "High"})
    put("12", "Potential Matches", mk(v=str(len(legal_pm) + crm_hits) + (" – " + "; ".join(f"{first('Screened party') or 'party'} on {first('Sanctions list') or 'list'} list ({first('Screening date') or '—'})" for _ in legal_pm) if legal_pm else ""),
                                      kind="calc", src="Legal, CRM", srcFull="Legal systems", conf="High"))
    put("12", "Escalations", mk(v="; ".join(f"{e['item']} → {e['owner']}, due {e['due']}" for e in sanc_esc) or "None", kind="calc", src="Data360 Clean", conf="High"))

    # ---- 13 ESG
    esg_a = [v for v in (num_of(e.value) for e in ints("ESG score")) if v is not None]
    crs = gold_field("Country_Risk_Score", ["Country Risk Database"])
    emis = [v for v in (num_of(e.value) for e in ints("Financed emissions (tCO2e)")) if v is not None]
    trans = [str(e.value) for e in ints("Sector transition score")]
    haz = [str(e.value) for e in ints("Hazard score") if ":" in str(e.value)]
    eg = fG("ESG_Score")
    put("13", "ESG Score", {**eg, "v": f"{gv('ESG_Score')} (higher is better)" + (f"; agency risk scores {min(esg_a):g}–{max(esg_a):g} (lower is better)" if esg_a else "")} if gv("ESG_Score") else eg)
    put("13", "Country Risk Score", mk(v=f"{crs['v']:g} ({gv('Country') or ''})", raw=crs["v"], src=crs["src"], srcFull=crs["src"], rec=crs["id"], when=crs["when"], kind="external", conf="Medium") if crs else mk())
    epc, esia = fI("Equator Principles category"), fI("ESIA status")
    put("13", "Climate Risk", mk(v=f"Financed emissions {sum(emis):,.0f} tCO2e; Equator Principles {epc['v']}; ESIA {str(esia['v']).lower()}", kind="internal", src="Risk platforms",
                                 srcFull="Risk platforms", conf="Medium") if emis else mk())
    trans_high = any((num_of(t) or 0) >= 4 for t in trans)
    put("13", "Transition Risk", mk(v=f"{'Medium-high' if trans_high else 'Low'} – sector transition scores {', '.join(trans)}", kind="calc", src="Risk platforms", srcFull="Risk platforms", conf="Medium") if trans else mk())
    haz_high = [h for h in haz if re.search("high", h, re.I)]
    put("13", "Physical Risk", mk(v=f"{'High' if haz_high else 'Medium'} – {'; '.join(haz)}", kind="calc", src="Risk platforms", srcFull="Risk platforms", conf="Medium") if haz else mk())
    esap = fI("E&S action plan")
    put("13", "ESG Commentary", fA(f"ESG score {gv('ESG_Score') or '—'} is adequate, but {len(haz_high)} high physical hazards ({', '.join(re.sub(r':.*$', '', h).lower() for h in haz_high)}) and "
                                   + (f"an open E&S action plan ({str(esap['v']).lower()})" if esap["kind"] != "missing" else "no E&S action plan") + " need monitoring.",
                                   "Risk platforms, ESG Database", "AI draft"))

    # ---- confidence
    S_conf = conf_stages(assess, norm) or [{"label": "Sourced", "pct": None, "dims": {k: None for k in STD}, "r": "na", "cap": "", "provisional": False}]
    last = S_conf[-1]
    capR = {"r": last.get("r", "na"), "cap": last.get("cap", "")}

    # ---- analysis
    obl_n = num_of(obl_r["v"]) if obl_r["kind"] != "missing" else None
    ext_mapped = num_of(RATING_MAP.get(ext_raw or "", ""))
    ecl = [str(e.value) for e in ints("ECL stage")]
    stage3 = any("3" in e for e in ecl)
    restructured = any(re.search("restruct|default|non-performing", str(s), re.I) for s in status)
    ind = gv("Industry")
    crs_v = crs["v"] if crs else None
    gsum = fmtUSD(sum(g_amts)) if g_amts else "—"
    RAG = [
        {"area": "Borrower Risk", "rag": "r" if (obl_n or 0) >= 7 or stage3 or restructured else "a" if (obl_n or 0) >= 6 else "g",
         "txt": f"Internal rating {obl_r['v']}" + (f" vs external {ext_raw} (maps to {RATING_MAP.get(ext_raw)})" if ext_mapped else "") + (f"; ECL {', '.join(ecl)}" if ecl else "")
                + (f"; a facility is {', '.join(s for s in status if s != 'Performing').lower()} ({int(dpd)} days past due)" if restructured else "") + "."},
        {"area": "Industry Risk", "rag": "a" if any(re.search("lower|loss|downgrade", h, re.I) for h in heads) else "g",
         "txt": f"{ind or 'Industry not held'}; " + ("news reports lower quarterly earnings" if any(re.search("lower|loss", h, re.I) for h in heads) else "no negative sector news") + "."},
        {"area": "Country Risk", "rag": ("g" if crs_v <= 3 else "a" if crs_v <= 6 else "r") if crs_v is not None else "na",
         "txt": f"{gv('Country') or '—'}; country risk score {crs_v if crs_v is not None else 'not held'} (Country Risk Database, 1 = lowest risk)."},
        {"area": "Sponsor Risk", "rag": "a" if legal_pm else "g" if guar["kind"] != "missing" else "a",
         "txt": (f"Group support from {', '.join(guar['vals'])} ({len(g_amts)} guarantees, {gsum})" if guar["kind"] != "missing" else "No guarantor")
                + ("; agency cites strong sponsor support" if any(re.search("sponsor", d, re.I) for d in drivers) else "")
                + ("; the guarantor has an open sanctions potential match" if legal_pm else "") + "."},
        {"area": "ESG Risk", "rag": "a" if haz_high else "g" if (parse_number(gv("ESG_Score")) or 0) >= 60 else "a",
         "txt": f"ESG score {gv('ESG_Score') or '—'}; {len(haz_high)} high physical hazards; Equator Principles {epc['v']}."},
        {"area": "Financing Risk", "rag": "r" if ch11 or restr["kind"] != "missing" else "a" if (carry is not None and carry < 0) or (outp and fac and outp / fac > 0.8) else "g",
         "txt": f"Net leverage {fmtX(lev)}, LTV {fmtP(ltv)}, utilisation {fmtP(outp / fac if outp and fac else None)}"
                + (f", pricing {abs(carry)} bps below cost of funds" if carry is not None and carry < 0 else "")
                + (f"; restructuring plan ({str(restr['vals'][0]).lower()})" if restr["kind"] != "missing" else "")
                + (f", standstill to {standstill[0].split(' to ')[-1]}" if standstill else "") + "."},
    ]
    strengths, concerns = [], []
    rv = [v for v in S["rev"] if v]
    if rv:
        strengths.append(f"Revenues: {fmtUSD(S['rev'][-1])} latest, trend {trend(S['rev']).lower()}.")
    mg_ = [v for v in S["margin"] if v]
    if mg_:
        (strengths if S["margin"][-1] and S["margin"][-1] >= 0.2 else concerns).append(f"Cash flow: EBITDA margin {fmtP(S['margin'][-1])}.")
    cr_r = gold_field("Current_Ratio", ["Bureau van Dijk", "Capital IQ"])
    if cr_r:
        (strengths if cr_r["v"] >= 1.2 else concerns).append(f"Liquidity: current ratio {fmtX(cr_r['v'])}.")
    if lev is not None:
        (strengths if lev <= 3 else concerns).append(f"Capital structure: net leverage {fmtX(lev)}" + (f" against a {fmtX(cov['v'])} covenant" if cov else "") + ".")
    if ltv is not None:
        (strengths if ltv <= 0.6 else concerns).append(f"Security: LTV {fmtP(ltv)}, cover {1 / ltv:.2f}x.")
    if g_amts:
        strengths.append(f"Support: {len(g_amts)} group guarantees totalling {gsum}.")
    if restructured or ch11:
        concerns.append("Refinancing: " + "; ".join(x for x in [f"facility {', '.join(s for s in status if s != 'Performing').lower()}, {int(dpd)} days past due" if restructured else None,
                                                                  f"{ch11[0].value} proceeding" if ch11 else None,
                                                                  f"plan of {str(restr['vals'][0]).lower()}" if restr["kind"] != "missing" else None] if x) + ".")
    if dist:
        concerns.append(f"Market conditions: {len(dist)} adverse news items ({', '.join(dict.fromkeys(dist)).lower()}), average sentiment {s_avg:.2f}.")
    if trend(S["rev"]).startswith("Weakening") or any(re.search("lower", h, re.I) for h in heads):
        concerns.append("Performance pressure: lower quarterly earnings reported.")
    if carry is not None and carry < 0:
        concerns.append(f"Pricing: all-in rate {abs(carry)} bps below the cost of funds.")
    for r in COV:
        if r["status"] in ("Breach", "Conflict", "Tight"):
            concerns.append(f"Covenants: {r['name']} {r['status'].lower()}" + (f" – {r['note']}" if r["note"] else "") + ".")

    # ---- compliance checks
    CH = []

    def chk(area, check, result, evidence, src, hard=False, cp=None, cs=None):
        CH.append({"area": area, "check": check, "result": result, "evidence": evidence, "src": src, "hard": bool(hard), "cp": cp, "cs": cs})

    kyc_ok = bool(kyc) and all(re.search("complete|approved|verified", k, re.I) for k in kyc)
    chk("KYC & AML", "KYC complete", "Exception" if not kyc else "Pass" if kyc_ok else "Fail", f"KYC status {', '.join(dict.fromkeys(kyc))}" if kyc else "No KYC status held", "CRM",
        hard=not kyc_ok and bool(kyc), cp=None if kyc_ok else "Complete the KYC refresh and record status Complete in CRM")
    nr = next_kyc[0] if next_kyc else None
    chk("KYC & AML", "KYC review in date", ("Pass" if nr >= ymd else "Fail") if nr else "Exception", f"Next review {nr}" if nr else "Not held", "CRM")
    chk("KYC & AML", "AML risk rating", "Exception" if not aml else "Fail" if aml_top == "High" else "Pass", f"{aml_top} ({len(aml)} ratings: {', '.join(aml)})" if aml else "Not held", "CRM",
        cs="Enhanced AML monitoring while the risk rating is Medium" if aml_top == "Medium" else None)
    chk("KYC & AML", "PEP screening", "Exception" if not pep or "Y" in pep else "Pass", f"PEP flag {', '.join(dict.fromkeys(pep))}" if pep else "Not held", "CRM")
    chk("KYC & AML", "UBO validated", "Fail" if ubo["kind"] == "missing" else "Exception" if ubo_pct["kind"] == "missing" else "Pass",
        f"{ubo['v']}" + ("; ownership percentage not held" if ubo_pct["kind"] == "missing" else ""), "Corporate Registry, CRM",
        cp="Obtain UBO ownership percentages and certified ID" if ubo_pct["kind"] == "missing" else None)
    chk("KYC & AML", "Adverse media", "Exception" if not heads else "Fail" if dist else "Pass",
        f"{len(dist)} distress indicators ({', '.join(dict.fromkeys(dist))}); average sentiment {s_avg:.2f}" if dist else "No adverse items", "External news",
        hard=any(re.search("missed payment|default", d, re.I) for d in dist), cp="RM to explain the missed-payment reports with written borrower confirmation" if dist else None)
    sv = gv("Sanctions_Screening")
    chk("Sanctions", "Sanctions feed screening", ("Pass" if re.search("no match|clear", str(sv), re.I) else "Fail") if sv else "Exception",
        f"{sv} ({G['Sanctions_Screening']['record']}, {G['Sanctions_Screening']['as_of']})" if sv else "Not held", "Regulatory / Sanctions Feed")
    chk("Sanctions", "Internal screening records", "Fail" if legal_pm or crm_hits else "Pass",
        F["12|Potential Matches"]["v"] + (f"; {crm_hits} CRM sanctions hit flags set to Y" if crm_hits else "") if legal_pm or crm_hits else "No potential matches", "Legal, CRM",
        hard=len(legal_pm) + crm_hits > 0, cp=("Financial Crime Compliance to clear the potential match" + (f" on {first('Screened party')}" if first("Screened party") else "") + " and the CRM hit flags") if legal_pm or crm_hits else None)
    chk("Sanctions", "Escalations open", "Exception" if sanc_esc else "Pass",
        f"{len(sanc_esc)} open with {', '.join(dict.fromkeys(e['owner'] for e in sanc_esc))}" if sanc_esc else "None", "Data360 Clean")
    for r in COV:
        if r["status"] == "Not tested":
            chk("Covenants", f"{r['name']} covenant", "Exception", "Threshold or actual not held", "Loan systems", cp=f"Obtain the latest {r['name']} compliance certificate")
            continue
        chk("Covenants", f"{r['name']} covenant", "Fail" if r["status"] == "Breach" else "Pass" if r["status"] == "Compliant" else "Exception",
            f"{fmt_cov(r, r['actual'])} vs {'≤' if r['isMax'] else '≥'} {fmt_cov(r, r['threshold'])}, headroom {fmtP(r['head'])}" + (f"; {r['note']}" if r["note"] else ""),
            "Capital IQ, calculated" if r["name"] == "Leverage" else "Loan systems", hard=r["status"] == "Breach",
            cp=f"Confirm the {r['name']} test result: the compliance figure and the early-warning alert disagree" if r["status"] == "Conflict" else f"Waiver or reset of the {r['name']} covenant" if r["status"] == "Breach" else None,
            cs=f"Monthly {r['name']} monitoring while headroom is below 10%" if r["status"] == "Tight" else None)
    chk("Credit policy", "Rating floor (internal grade 6 or better)", "Exception" if obl_n is None else "Fail" if obl_n >= 7 else "Pass", f"Obligor rating {obl_r['v']}", "Risk platforms", hard=(obl_n or 0) >= 7)
    if obl_n is not None and ext_mapped:
        gap = abs(obl_n - ext_mapped)
        chk("Credit policy", "Internal vs external rating", "Exception" if gap >= 2 else "Pass",
            f"Internal {obl_r['v']} vs external {ext_raw} (maps to {RATING_MAP.get(ext_raw)}), {gap:g} grades apart", "Risk platforms, rating agency",
            cp="Credit Risk to reconcile the internal and external ratings" if gap >= 2 else None)
    chk("Credit policy", "Asset quality (performing, IFRS 9 stage 1–2)", "Fail" if stage3 or restructured else "Pass",
        f"{', '.join(status) or 'Status not held'}; days past due {int(dpd)}; {', '.join(ecl) or 'stage not held'}", "Loan systems, Risk platforms", hard=stage3 or restructured)
    t1 = num_of(first("Exposure % of Tier 1 capital"))
    chk("Credit policy", "Large exposure (< 25% of Tier 1)", "Exception" if t1 is None else "Fail" if t1 >= 25 else "Pass",
        "Not held" if t1 is None else f"{t1:g}% of Tier 1 capital" + (" (reportable)" if t1 >= 10 else ""), "Risk platforms", hard=t1 is not None and t1 >= 25)
    chk("Credit policy", "Pricing above cost of funds", "Exception" if carry is None or carry < 0 else "Pass",
        "Not calculable" if carry is None else F["10|Treasury Assessment"]["v"] + (f"; relationship RAROC {raroc['v']}" if raroc["kind"] != "missing" else ""), "Bloomberg, Treasury",
        cp="Reprice above the cost of funds or document the relationship justification" if carry is not None and carry < 0 else None)
    mat = gv("Maturity_Date")
    if mat:
        try:
            yrs = (date.fromisoformat(str(mat)[:10]) - ref_date).days / 365
        except ValueError:
            yrs = None
    chk("Credit policy", "Tenor (≤ 7 years remaining)", ("Pass" if yrs is not None and yrs <= 7 else "Fail") if mat else "Exception", f"Matures {mat}" if mat else "Not held", "Bloomberg")
    chk("Legal", "Litigation and insolvency", "Fail" if ch11 else "Pass", F["11|Litigation and Restructuring"]["v"], "Legal", hard=bool(ch11),
        cp="Legal to confirm the status of the insolvency proceeding and the restructuring plan" if ch11 else None)
    sig = F["11|Authorised Signatories"]
    chk("Legal", "Authorised signatories", "Exception" if sig["kind"] == "missing" else "Pass", sig["v"], "Legal", cp="Obtain a certified authorised signatory list" if sig["kind"] == "missing" else None)
    chk("Legal", "Corporate authority", "Exception" if board else "Fail", "Board resolution collected at CDD, not verified" if board else "No board resolution", "CRM",
        cp="Verify the board resolution approving the facility against the constitution")
    chk("ESG", "Equator Principles and ESIA", "Exception" if epc["kind"] == "missing" else "Pass", f"Category {epc['v']}; ESIA {str(esia['v']).lower()}", "Risk platforms",
        cs="Deliver the completed ESIA and the E&S action plan" if re.search("progress", str(esia["v"]), re.I) else None)
    crit_fail = [r for r in (crit["rows"] if crit else []) if r["status"] == "Failed"]
    pct_ = last.get("pct")
    chk("Data", "Data confidence", "Pass" if (pct_ or 0) >= 60 else "Fail", f"{pct_ if pct_ is not None else '—'}% ({WORD.get(capR['r'], '—')}" + (f", {capR['cap']}" if capR["cap"] else "") + ")", "Data360 Assess")
    chk("Data", "Critical fields reconciled", "Exception" if crit_fail else "Pass",
        (f"{crit['n']} of {len(crit['rows'])} validated" + (f"; open: {', '.join(r['field'].lower() for r in crit_fail)}" if crit_fail else "")) if crit else "Clean validation not run", "Data360 Clean",
        cp=f"Resolve the {len(crit_fail)} critical-field discrepancies escalated in Clean" if crit_fail else None)
    on = set(rules_on)
    for x in CH:
        x["rule"] = rule_of_check(x["check"])
    CHoff = [x for x in CH if x["rule"] and x["rule"] not in on]
    CH = [x for x in CH if x not in CHoff]
    confirmed_hit = bool(sv and re.search("confirmed|true match", str(sv), re.I))
    dflag = gold_field("Default_Flag", ["Moody's", "Capital IQ", "D&B"])
    in_default = bool(dflag and re.match("y", str(dflag["v"]), re.I)) or dpd >= 90
    hard_fails = [x for x in CH if x["result"] == "Fail" and x["hard"]]
    decision = "Decline" if confirmed_hit or in_default else "Refer" if hard_fails else "Approve With Conditions" if any(x["result"] != "Pass" for x in CH) else "Approve"
    CP = list(dict.fromkeys(x["cp"] for x in CH if x["cp"]))
    CS = list(dict.fromkeys([x["cs"] for x in CH if x["cs"]] + ["Quarterly compliance certificates for all financial covenants",
                                                                  "Annual full (not desktop) valuation of the security" + (f"; last {val_d[-1]}" if val_d else "")]
                            + (["Obtain an LEI within 90 days"] if F["2|LEI"]["kind"] == "missing" else [])))
    dec_why = (f"{len(hard_fails)} hard policy failures need Credit Committee review: {'; '.join(x['check'] for x in hard_fails)}." if decision == "Refer"
               else ("Confirmed sanctions hit." if confirmed_hit else "Borrower in default.") if decision == "Decline"
               else "All hard checks pass; conditions clear the exceptions." if decision == "Approve With Conditions" else "All checks pass.")
    pitch, pout = ints("Product pitched"), ints("Pitch outcome")
    put("1", "Proposed Facility Type", mk(v=f"{pitch[0].value}" + (f" (pitch {str(pout[0].value).lower()})" if pout else ""), kind="internal", src="CRM tools", srcFull="CRM tools", conf="Medium",
                                          note="Latest product pitched in CRM") if pitch else fM("Proposed structure not in CRM"))
    put("1", "Proposed Facility Amount", fM("Requested amount not held"))
    put("1", "Proposed Maturity", fM("Proposed tenor not held"))
    put("1", "Proposed Pricing", fM("Proposed margin not held"))
    put("16", "Decision", mk(v=decision, kind="calc", src="Data360 rules", conf="Medium", note=dec_why))

    for e in st.get("edits") or []:
        if e["key"] in F:
            F[e["key"]] = {**F[e["key"]], "v": e["to"], "kind": "edited", "src": "Reviewer edit", "conf": "Reviewer",
                           "note": f"{e['reason']} (was \"{e['from']}\") · {e['by']}, {e['at']}"}
    return {"c": c, "ref": ref, "F": F, "months": months, "mLabels": [m_label(m) for m in months], "finRows": fin_rows,
            "COV": [{**r, "thrTxt": "Not held" if r["threshold"] is None else f"{'≤' if r['isMax'] else '≥'} {fmt_cov(r, r['threshold'])}",
                     "actTxt": fmt_cov(r, r["actual"]), "headTxt": fmtP(r["head"])} for r in COV],
            "RAG": RAG, "strengths": strengths, "concerns": concerns, "CH": CH, "CHoff": CHoff, "CP": CP, "CS": CS, "decision": decision, "decWhy": dec_why,
            "hardFails": len(hard_fails), "stages": S_conf, "last": last, "capR": capR, "crit": crit, "critFail": [r["key"] for r in crit_fail],
            "lev": lev, "ltv": ltv, "carry": carry, "levTxt": fmtX(lev), "ltvTxt": fmtP(ltv), "ubo": ubo, "guar": guar, "grp": grp, "spvs": spvs, "holdco": holdco,
            "rmName": rm, "rulesOn": len(on), "ymd": ymd, "owners": owners or {}, "clean": clean}


# ---------------- statistics, domains, blocks ----------------
def fields_in(M, secs):
    return [f for f in M["F"].values() if f["sec"] in secs]


def stats(M, st):
    secs = ["0", *selected(st)]
    fs = fields_in(M, secs)
    auto = [f for f in fs if f["kind"] in AUTO_KINDS]
    manual = [f for f in fs if f["kind"] == "manual"]
    edited = [f for f in fs if f["kind"] == "edited"]
    missing = [f for f in fs if f["kind"] == "missing"]
    ai = round(sum(CONF_N.get(f["conf"], 60) for f in auto) / len(auto)) if auto else 0
    srcs = {f["srcFull"] or f["src"] for f in auto if (f["srcFull"] or f["src"]) not in ("Calculated", "Manual", "—", "")}
    by_sec = []
    for no in secs:
        x = fields_in(M, [no])
        if not x:
            continue
        a = [f for f in x if f["kind"] in AUTO_KINDS]
        by_sec.append({"no": no, "title": "Document control" if no == "0" else (no + ". " if not re.fullmatch("[A-D]", no) else "") + SEC[no]["t"], "n": len(x), "auto": len(a),
                       "man": sum(1 for f in x if f["kind"] in ("manual", "edited")), "miss": sum(1 for f in x if f["kind"] == "missing"),
                       "srcs": list(dict.fromkeys(f["src"] for f in a if f["src"] and f["src"] != "—"))[:4]})
    n = len(fs)
    return {"total": n, "auto": len(auto), "manual": len(manual), "edited": len(edited), "missing": [{"sec": f["sec"], "label": f["label"], "note": f["note"]} for f in missing],
            "ai": ai, "srcs": len(srcs), "bySec": by_sec, "pctAuto": round(len(auto) / n * 100) if n else 0, "pctMan": round((len(manual) + len(edited)) / n * 100) if n else 0}


def dom_score(M, secs, ref_date: date):
    fs = fields_in(M, secs)
    filled = [f for f in fs if f["kind"] != "missing"]
    if not fs:
        return None

    def p(a, b):
        return round(a / b * 100) if b else None
    dated = [f for f in filled if re.match(r"^\d{4}-\d{2}-\d{2}", str(f.get("when") or ""))]
    undated_sor = [f for f in filled if not f.get("when") and f.get("srcFull") in SOR]
    fresh = sum(1 for f in dated if (ref_date - date.fromisoformat(f["when"][:10])).days <= 90) + len(undated_sor)
    r = {"Completeness": p(len(filled), len(fs)), "Accuracy": p(sum(1 for f in filled if f["conf"] == "High" or f["kind"] == "golden"), len(filled)),
         "Consistency": p(sum(1 for f in filled if f["conf"] != "Low"), len(filled)), "Validity": p(sum(1 for f in filled if not str(f["v"]).startswith("Not calculable")), len(filled)),
         "Timeliness": p(fresh, len(dated) + len(undated_sor))}
    vals = [v for v in r.values() if v is not None]
    r["overall"] = round(sum(vals) / len(vals)) if vals else None
    return r


def rag_word(v):
    return "No data" if v is None else "Green" if v >= 85 else "Amber" if v >= 60 else "Red"


def version(st):
    return st["retained"]["version"] if st.get("retained") else f"v0.{1 + len(st.get('edits') or [])} draft"


def status(st):
    cc = st["approvals"][-1]["decision"]
    if st.get("retained"):
        return "Declined" if "Decline" in cc else "Referred" if "Refer" in cc else "Approved"
    return "Review" if any(a["decision"] for a in st["approvals"]) else "Draft"


def reviewer_conf(M, st):
    d = [a for a in st["approvals"] if a["decision"]]
    if not d:
        return "Pending review"
    agree = sum(1 for a in d if a["decision"].lower() == M["decision"].lower())
    return f"{round(agree / len(d) * 100)}% agree with the draft decision ({len(d)} of {len(st['approvals'])} decided)"


def group_tree(M):
    L = []
    ubo = M["ubo"]["v"] if M["ubo"]["kind"] != "missing" else None
    grp = M["grp"]["v"] if M["grp"]["kind"] != "missing" else None
    g = M["guar"].get("vals") or [] if M["guar"]["kind"] != "missing" else []
    chain = [x for x in [f"{ubo}  [UBO · Corporate Registry]" if ubo else None, f"{grp}  [Group · Risk platforms]" if grp else None,
                         *[f"{x}  [Guarantor · Loan systems]" for x in g], f"{M['c']}  [Borrower · {M['ref']}]"] if x]
    for i, x in enumerate(chain):
        L.append(("   " * (i - 1) + "└─ " + x) if i else x)
    d = len(chain) - 1
    if M["holdco"]["kind"] != "missing":
        L.append("   " * d + "└─ " + ", ".join(M["holdco"]["vals"]) + "  [Holdco · link not evidenced]")
        for i, s in enumerate(M["spvs"]):
            L.append("   " * (d + 1) + ("└─ " if i == len(M["spvs"]) - 1 else "├─ ") + s + "  [SPV / asset owner · Physical records]")
    return L


def exceptions(M, ST):
    E = [{"ex": f"{x['check']}: {x['evidence']}", "impact": "High" if x["result"] == "Fail" and x["hard"] else "Medium", "res": x["cp"] or x["cs"] or "Reviewer to assess"}
         for x in M["CH"] if x["result"] != "Pass"]
    E += [{"ex": f"{SEC[f['sec']]['t'] if f['sec'] in SEC else 'Document control'} · {f['label']} not sourced", "impact": "Medium" if f["sec"] in ("2", "12", "6") else "Low",
           "res": f["note"] or "Request from borrower or RM"} for f in ST["missing"]]
    return E


def ai_checks(M, ST):
    fs = fields_in(M, ["0", *[s[0] for s in SECTIONS]])
    golden_ = [f for f in fs if f["kind"] == "golden"]
    hard = [x for x in M["CH"] if x["result"] == "Fail" and x["hard"]]
    reg = [x for x in M["CH"] if x["area"] in ("KYC & AML", "Sanctions")]
    v = M["last"]["dims"].get("Validity")
    hp = [x for x in hard if x["area"] == "Credit policy"]
    return [["Source Validation", f"Pass – {len(golden_)} values from golden sources; {sum(1 for f in golden_ if f['conf'] == 'High')} fully validated"],
            ["Completeness Check", f"{'Pass' if ST['pctAuto'] >= 85 else 'Exception'} – {ST['auto']} of {ST['total']} fields filled automatically ({ST['pctAuto']}%)"],
            ["Reconciliation Check", f"Exception – {len(M['critFail'])} critical fields disagree across sources" if M["critFail"] else "Pass"],
            ["Quality Rules", f"{'Pass' if (v or 0) >= 85 else 'Exception'} – validity {v if v is not None else '—'}"],
            ["Policy Compliance", "Fail – " + "; ".join(x["check"] for x in hp) if hp else "Pass"],
            ["Regulatory Controls", "Fail – " + "; ".join(x["check"] for x in reg if x["result"] == "Fail") if any(x["result"] == "Fail" for x in reg) else "Pass"]]


def owner_of_field(f, owners):
    if f["kind"] in ("manual", "edited"):
        return "Relationship manager"
    if f["kind"] == "calc":
        return "Credit analyst"
    if f["kind"] == "draft":
        return "Credit analyst (AI draft)"
    return owner_of(f["srcFull"], owners) if f.get("srcFull") else "Credit analyst"


def trace_rows(M, ST, st):
    fs = fields_in(M, ["0", *selected(st)])
    return [{"key": f["key"], "sec": "Control" if f["sec"] == "0" else f["sec"], "label": f["label"], "v": f["v"], "src": f["src"] + (f" ({f['rec']})" if f.get("rec") else ""),
             "when": f.get("when") or "", "owner": owner_of_field(f, M["owners"]), "conf": f["conf"], "kind": f["kind"], "note": f["note"]}
            for f in fs if not (f["sec"] == "1" and f["kind"] == "manual")]


def recon_rows(M):
    R = []
    crit = M["crit"]
    if crit:
        for r in crit["rows"]:
            R.append([r["field"], f"{r['source'] or '—'} vs other external and internal values", r["golden"] or "—",
                      "Matched" if r["status"] == "Validated" else "Escalated" if r["status"] == "Failed" else r["status"]])
    rc = (M.get("clean") or {}).get("summary", {}).get("Reconcile conflicting records")
    for d in (rc or {}).get("decisions", []):
        R.append([d["field"], f"{d['chosen']} vs {', '.join(d['replaced'])}", d["chosen"], "Reconciled"])
    return R


def final_conf(M, ref_date):
    def pct(secs):
        r = dom_score(M, secs, ref_date)
        return r["overall"] if r else None

    def area(n, v, ch=""):
        return [n, f"{rag_word(v)}" + (f" ({v}%)" if v is not None else "") + (f" · {ch}" if ch else "")]

    def fails(a):
        return sum(1 for x in M["CH"] if x["area"] in a and x["result"] == "Fail")
    credit, fin, comp, legal, dq = pct(["4", "6", "7"]), pct(["5", "8"]), pct(["12"]), pct(["11"]), M["last"].get("pct")
    vals = [v for v in [credit, fin, comp, legal, dq] if v is not None]
    allv = round(sum(vals) / len(vals)) if vals else None
    fk = fails(["KYC & AML", "Sanctions"])
    fl = fails(["Legal"])
    return [area("Credit Information", credit), area("Financial Information", fin), area("Compliance Information", comp, f"{fk} checks failed" if fk else ""),
            area("Legal Information", legal, f"{fl} checks failed" if fl else ""), area("Data Quality", dq), area("Overall Memo Confidence", allv)]


def blocks(M, ST, st, ref_date: date) -> list[dict]:
    F, on, B = M["F"], set(selected(st)), []

    def v(k):
        return F[k]["v"] if k in F else "—"

    def tbl(head, widths, keys, mp=None, **o):
        rows = [mp(F[k]) if mp else [F[k]["label"], F[k]["v"]] for k in keys if k in F]
        B.append({"t": "table", "head": head, "widths": widths, "rows": rows, **o})

    word = WORD.get(M["capR"]["r"], "—")
    last = M["last"]
    ap = st["approvals"]
    B.append({"t": "title", "kicker": "Credit Memo Acceleration & Assurance", "title": "Credit Memo", "sub": f"{M['c']} · {M['ref']}", "metaHead": ["Item", "Details"], "meta": [
        ["Credit Memo Reference", M["ref"]], ["Borrower", v("0|Borrower")], ["Facility ID", v("0|Facility ID")], ["Transaction Name", v("0|Transaction Name")],
        ["Relationship Manager", ap[0]["name"] or v("0|Relationship Manager")], ["Credit Officer", ap[1]["name"] or "To be assigned"], ["Risk Officer", ap[3]["name"] or "To be assigned"],
        ["Memo Version", version(st)], ["Date", M["ymd"]], ["Approval Status", status(st)],
        ["Data Confidence Score", f"{last.get('pct')}% ({word}" + (f", {M['capR']['cap']}" if M["capR"]["cap"] else "") + ")"],
        ["AI Confidence Score", f"{ST['ai']}% ({ST['pctAuto']}% of fields filled automatically)"]]})
    if "1" in on:
        B += [{"t": "h1", "text": "1. Executive Summary"}, {"t": "h2", "text": "Credit Request"}]
        pricing = F["10|Treasury Assessment"]["v"].split(":")[0] if M["carry"] is not None else "—"
        B.append({"t": "table", "head": ["Item", "Current", "Proposed"], "widths": [22, 39, 39], "rows": [
            ["Facility Type", v("4|Facility Type"), v("1|Proposed Facility Type")], ["Facility Amount", v("4|Facility Amount"), v("1|Proposed Facility Amount")],
            ["Outstanding", v("4|Drawn Amount"), "—"], ["Maturity", v("4|Maturity Date"), v("1|Proposed Maturity")],
            ["Pricing", pricing, v("1|Proposed Pricing")], ["Rating", f"{v('6|Internal Rating')}; external {v('6|External Rating')}", "—"]]})
        B += [{"t": "h2", "text": "Recommendation"}, {"t": "callout", "tone": "ok" if M["decision"].startswith("Approve") else "warn", "text": f"{M['decision']}: {M['decWhy']}"}]
        B.append({"t": "bullets", "items": [f"Key conditions: {'; '.join(M['CP'][:3]) or 'none'}.",
                                            f"Key risks: {', '.join(r['area'].lower() for r in M['RAG'] if r['rag'] == 'r') or 'none rated red'}.",
                                            f"Key mitigants: {'; '.join(s.rstrip('.') for s in M['strengths'][:3]) or 'none'}."]})
        B += [{"t": "h2", "text": "Credit Committee Decision Summary"}, {"t": "bullets", "items": [
            f"Transaction rationale: {v('4|Facility Purpose')}; CRM pitch: {v('1|Proposed Facility Type')}.",
            f"Financial strength: revenue {v('5|Revenue')}, EBITDA margin {v('5|EBITDA Margin')}, net leverage {M['levTxt']}.",
            f"Key risks: {' '.join(M['concerns'][:3])}", f"Mitigating factors: {' '.join(M['strengths'][-3:])}", f"Recommended decision: {M['decision']}."]}]
    if "2" in on:
        B += [{"t": "h1", "text": "2. Borrower Profile"}, {"t": "h2", "text": "Borrower Identity"}]
        tbl(["Attribute", "Value", "Source", "Confidence"], [26, 40, 20, 14], ["2|" + x for x in ["Borrower Name", "Legal Entity Name", "Registration Number", "LEI", "Tax ID", "Country of Incorporation",
                                                                                          "Operating Countries", "Industry Sector", "SIC / NAICS Code", "Date Established", "Website",
                                                                                          "Organisation Type", "Listed / Private"]],
            lambda f: [f["label"], f["v"], f["src"], f["conf"] or "—"])
        B.append({"t": "h2", "text": "Ownership Structure"})
        tbl(["Entity", "Role", "Ownership %"], [44, 30, 26], ["2|" + x for x in ["Parent Company", "Sponsor", "Guarantor", "UBO", "SPV"]],
            lambda f: [f["v"], f["label"], F["2|UBO ownership %"]["v"] if f["label"] == "UBO" else (f"Shares held by {', '.join(M['holdco']['vals'])}" if f["label"] == "SPV" and M["holdco"]["kind"] != "missing" else "—")])
        B += [{"t": "h2", "text": "Group Structure Diagram"}, {"t": "mono", "lines": group_tree(M)}]
    if "3" in on:
        B += [{"t": "h1", "text": "3. Relationship Overview"}, {"t": "h2", "text": "Existing Relationship"}]
        tbl(["Metric", "Value"], [30, 70], ["3|" + x for x in ["Relationship Start Date", "Total Exposure", "Revenue Contribution", "Number of Facilities", "Prior Credit Events", "Watchlist Status"]])
        B += [{"t": "h2", "text": "Relationship Manager Commentary"}, {"t": "p", "text": v("3|Relationship Manager Commentary")}]
    if "4" in on:
        B += [{"t": "h1", "text": "4. Facility Overview"}, {"t": "h2", "text": "Facility Structure"}]
        tbl(["Item", "Value"], [30, 70], ["4|" + x for x in ["Facility Type", "Facility Amount", "Drawn Amount", "Undrawn Amount", "Currency", "Maturity Date", "Repayment Profile", "Facility Purpose"]])
        B += [{"t": "h2", "text": "Tranches"}, {"t": "table", "head": ["Tranche", "Amount", "Seniority", "Pricing"], "widths": [16, 28, 28, 28],
                                                 "rows": [["A", v("4|Tranche A"), "—", "—"], ["B", v("4|Tranche B"), "—", "—"]]}]
    if "5" in on:
        B += [{"t": "h1", "text": "5. Financial Assessment"}, {"t": "h2", "text": "Historical Performance"}]
        L = [f"Current ({m})" if i == len(M["mLabels"]) - 1 else m for i, m in enumerate(M["mLabels"])]
        w = round(52 / len(L)) if L else 52
        B.append({"t": "table", "head": ["Metric", *L, "Trend"], "widths": [18, *[w] * len(L), 30], "num": list(range(1, len(L) + 1)), "rows": [[r[0], *r[1], r[2]] for r in M["finRows"]]})
        B.append({"t": "p", "muted": True, "text": "Audited FY-2 and FY-1 accounts are not held. Columns show the latest validated observation per month (Bureau van Dijk first, then Capital IQ, then D&B)."})
        B += [{"t": "h2", "text": "Financial Analysis"}, {"t": "h3", "text": "Strengths"}, {"t": "bullets", "items": M["strengths"] or ["None identified."]},
              {"t": "h3", "text": "Concerns"}, {"t": "bullets", "items": M["concerns"] or ["None identified."]}]
    if "6" in on:
        B += [{"t": "h1", "text": "6. Credit Risk Assessment"}, {"t": "h2", "text": "Internal Credit Assessment"}]
        tbl(["Metric", "Value"], [30, 70], ["6|" + x for x in ["Internal Rating", "External Rating", "PD", "LGD", "EAD", "Expected Loss"]])
        B += [{"t": "h2", "text": "Risk Assessment"}, {"t": "table", "head": ["Risk Area", "Assessment", "RAG"], "widths": [20, 66, 14], "rows": [[r["area"], r["txt"], RAGW[r["rag"]]] for r in M["RAG"]]}]
    if "7" in on:
        B += [{"t": "h1", "text": "7. Collateral & Security Assessment"}, {"t": "h2", "text": "Security Package"}]
        tbl(["Security Item", "Status"], [30, 70], ["7|" + x for x in ["Share Pledge", "Mortgage", "Assignment of Receivables", "Account Charge", "Guarantees"]])
        B.append({"t": "h2", "text": "Collateral Assessment"})
        tbl(["Item", "Value"], [30, 70], ["7|" + x for x in ["Asset Value", "Valuation Date", "LTV", "Security Coverage"]])
    if "8" in on:
        B.append({"t": "h1", "text": "8. Covenant Assessment"})
        B.append({"t": "table", "head": ["Covenant", "Threshold", "Actual", "Headroom", "Status"], "widths": [20] * 5,
                  "rows": [[r["name"], r["thrTxt"], r["actTxt"], r["headTxt"], r["status"]] for r in M["COV"]]})
        B += [{"t": "h2", "text": "Covenant Commentary"}, {"t": "p", "text": " ".join(f"{r['name']}: {r['status'].lower()} with {r['headTxt']} headroom" + (f" ({r['note']})" if r["note"] else "") + "."
                                                                                     for r in M["COV"] if r["status"] != "Not tested") or "No covenants tested."}]
    if "9" in on:
        B += [{"t": "h1", "text": "9. Industry & Market Assessment"}, {"t": "h2", "text": "Industry Analysis"},
              {"t": "bullets", "items": [f"{x}: {v('9|' + x)}" for x in ["Industry Overview", "Competitive Position", "Key Risks", "Market Outlook"]]}, {"t": "h2", "text": "External Intelligence"}]
        tbl(["Source", "Summary"], [24, 76], ["9|" + x for x in ["Bloomberg", "Capital IQ", "Moody's", "Industry Research"]])
    if "10" in on:
        B.append({"t": "h1", "text": "10. Treasury & Funding Assessment"})
        tbl(["Metric", "Value"], [30, 70], ["10|" + x for x in ["Cost of Funds", "Funding Currency", "Liquidity Impact", "Hedging Requirement", "Treasury Assessment"]])
    if "11" in on:
        B += [{"t": "h1", "text": "11. Legal Review"}, {"t": "h2", "text": "Legal Documentation"}]
        tbl(["Document", "Status"], [30, 70], ["11|" + x for x in ["Facility Agreement", "Security Documents", "Guarantees", "Board Resolutions", "Powers of Attorney"]])
        B.append({"t": "h2", "text": "Legal Authority Verification"})
        tbl(["Check", "Status"], [30, 70], ["11|" + x for x in ["Authorised Signatories", "Corporate Authority", "Seal Validation", "Board Approval"]])
        B += [{"t": "h2", "text": "Litigation and Restructuring"}, {"t": "p", "text": v("11|Litigation and Restructuring")}]
    if "12" in on:
        B += [{"t": "h1", "text": "12. Compliance Assessment"}, {"t": "h2", "text": "KYC & AML"}]
        tbl(["Item", "Status"], [30, 70], ["12|" + x for x in ["KYC Complete", "AML Screening", "UBO Validated", "Adverse Media"]])
        B.append({"t": "h2", "text": "Sanctions Review"})
        tbl(["Item", "Status"], [30, 70], ["12|" + x for x in ["Sanctions Screening", "Potential Matches", "Escalations"]])
        B += [{"t": "h2", "text": "Compliance Checks"}, {"t": "table", "head": ["Area", "Check", "Result", "Evidence"], "widths": [14, 24, 12, 50], "small": True,
                                                          "rows": [[x["area"], x["check"], x["result"], x["evidence"]] for x in M["CH"]]}]
    if "13" in on:
        B.append({"t": "h1", "text": "13. ESG Assessment"})
        tbl(["Metric", "Score"], [30, 70], ["13|" + x for x in ["ESG Score", "Country Risk Score", "Climate Risk", "Transition Risk", "Physical Risk"]])
        B += [{"t": "h2", "text": "ESG Commentary"}, {"t": "p", "text": v("13|ESG Commentary")}]
    if "14" in on:
        B += [{"t": "h1", "text": "14. Data Quality & Assurance"}, {"t": "h2", "text": "Data Confidence Dashboard"}]
        B.append({"t": "table", "head": ["Dimension", "Score"], "widths": [50, 50], "num": [1],
                  "rows": [[k, "—" if last["dims"].get(k) is None else str(last["dims"][k])] for k in STD]
                  + [["Overall Confidence", f"{last.get('pct')}% ({word}" + (f", {M['capR']['cap']}" if M["capR"]["cap"] else "") + ")"]]})
        rows = []
        for d, s, g in DOMAINS:
            r = dom_score(M, s, ref_date)
            rows.append([d, g, f"{r['overall']}% ({rag_word(r['overall'])})" if r and r["overall"] is not None else "—"])
        B += [{"t": "h2", "text": "Source Validation"}, {"t": "table", "head": ["Data Domain", "Golden Source", "Confidence"], "widths": [30, 40, 30], "rows": rows}]
        B += [{"t": "h2", "text": "Exception Register"}, {"t": "table", "head": ["Exception", "Impact", "Resolution"], "widths": [46, 12, 42], "small": True,
                                                           "rows": [[e["ex"], e["impact"], e["res"]] for e in exceptions(M, ST)]}]
    if "15" in on:
        B += [{"t": "h1", "text": "15. AI Assurance"}, {"t": "h2", "text": "Automated Checks"}, {"t": "table", "head": ["Control", "Result"], "widths": [40, 60], "rows": ai_checks(M, ST)}]
        B += [{"t": "h2", "text": "AI Metrics"}, {"t": "table", "head": ["Metric", "Value"], "widths": [40, 60], "rows": [
            ["AI Confidence", f"{ST['ai']}%"], ["Manual Content %", f"{ST['pctMan']}%"], ["AI Generated Content %", f"{ST['pctAuto']}%"],
            ["Not sourced %", f"{100 - ST['pctMan'] - ST['pctAuto']}%"], ["Reviewer Confidence", reviewer_conf(M, st)]]}]
    if "16" in on:
        B += [{"t": "h1", "text": "16. Credit Recommendation"}, {"t": "h2", "text": "Decision"},
              {"t": "mono", "lines": [f"{'☒' if d == M['decision'] else '☐'} {d}" for d in ["Approve", "Approve With Conditions", "Refer", "Decline"]]},
              {"t": "p", "text": M["decWhy"]}, {"t": "h2", "text": "Conditions Precedent"}, {"t": "numbered", "items": M["CP"] or ["None."]},
              {"t": "h2", "text": "Conditions Subsequent"}, {"t": "numbered", "items": M["CS"] or ["None."]}]
    if "17" in on:
        B += [{"t": "h1", "text": "17. Approval Workflow"}, {"t": "table", "head": ["Approver", "Name", "Decision", "Date", "Comment"], "widths": [20, 18, 20, 14, 28],
                                                             "rows": [[a["role"], a["name"] or "—", a["decision"] or "Pending", a["date"] or "—", a["comment"] or "—"] for a in ap]}]
    if "A" in on:
        B += [{"t": "pagebreak"}, {"t": "h1", "text": "Appendix A – Source Traceability"}, {"t": "table", "head": ["Data Element", "Source", "Timestamp", "Owner"], "widths": [40, 22, 16, 22],
                                                                                       "small": True, "rows": [[f"{r['sec']} · {r['label']}", r["src"], r["when"] or "—", r["owner"]] for r in trace_rows(M, ST, st)]}]
    if "B" in on:
        rows = []
        for d, s, _ in DOMAINS:
            r = dom_score(M, s, ref_date) or {}
            rows.append([d, *[("—" if r.get(k) is None else f"{r[k]}%") for k in ["Completeness", "Accuracy", "Consistency", "Validity", "Timeliness"]]])
        B += [{"t": "h1", "text": "Appendix B – Data Quality Dashboard"}, {"t": "table", "head": ["Domain", "Completeness", "Accuracy", "Consistency", "Validity", "Timeliness"],
                                                                           "widths": [20, 16, 16, 16, 16, 16], "num": [1, 2, 3, 4, 5], "rows": rows}]
    if "C" in on:
        B += [{"t": "h1", "text": "Appendix C – Reconciliation Log"}, {"t": "table", "head": ["Attribute", "Sources Compared", "Golden Value", "Status"], "widths": [22, 36, 24, 18],
                                                                       "small": True, "rows": recon_rows(M)}]
    if "D" in on:
        B += [{"t": "h1", "text": "Appendix D – Credit Memo Assurance Certificate"}, {"t": "h2", "text": "Assurance Statement"}, {"t": "p", "text": "This Credit Memo has been validated against:"},
              {"t": "bullets", "items": ["Authoritative Sources", "Data Quality Rules", "Compliance Requirements", "Regulatory Controls", "Credit Policy Requirements"]},
              {"t": "p", "text": "All material exceptions have been disclosed and escalated where appropriate."},
              {"t": "h2", "text": "Final Confidence Assessment"}, {"t": "table", "head": ["Area", "Status"], "widths": [50, 50], "rows": final_conf(M, ref_date)}]
        R = st.get("retained")
        if R:
            B.append({"t": "p", "muted": True, "text": f"Retained {R['at']} as {R['version']}. SHA-256 fingerprint {R['hash']}. {R['retention']}."})
        B += [{"t": "h2", "text": "Executive Outcome"}, {"t": "p", "text": "The Credit Memo Acceleration & Assurance process ensures that every credit submission is not only produced faster, but is also complete, governed, traceable, auditable and supported by trusted data, enabling stronger credit decisions and greater Credit Committee confidence."}]
    return B
