"""Phase 2 · Improve & Plan: 6 gap analysis, 7 recommendations, 8 confidence by domain, 9 roadmap
and business case. Built from the Phase 1 results and the retained credit memo (ported from the demo)."""
from __future__ import annotations

import math
import re

from . import memo as MM
from .reference import GOLD_PRIORITY, LABEL, RELIABILITY
from .registry import EXTERNAL, INTERNAL, meta

IMPACT_N = {"High": 3, "Medium": 2, "Low": 1}
EFFORT_N = {"S": 1, "M": 2, "L": 3}
EFFORT_W = {"S": "Small", "M": "Medium", "L": "Large"}
REC_LIB = {
    "mandatory-ids": ("Quality", "Make LEI, Tax ID and registration number mandatory at onboarding", "S", "KYC Operations", ["Completeness"], "Every obligor carries the identifiers regulators and the memo need"),
    "borrower-request": ("Quality", "Send a standard borrower information request for missing profile and legal items", "S", "Relationship manager", ["Completeness"], "Profile, ownership and authority fields filled from the borrower"),
    "audited-fin": ("Reporting", "Load audited annual financials (FY-2, FY-1) into the spreading tool", "M", "Credit analyst", ["Completeness", "Business relevance"], "Three-year financial trend in every memo"),
    "digitise": ("Technology", "Digitise physical records (scan, OCR, index) and link them to the obligor ID", "L", "Records management", ["Timeliness", "Usage"], "Originals searchable in minutes, not days"),
    "email-index": ("Technology", "Index email archives for approvals, notices and deal evidence", "M", "Records management", ["Usage"], "Approval and notice evidence found automatically"),
    "access-model": ("Governance", "Role-based access with a request workflow for restricted and personal data", "M", "Data Governance Office", ["Usage"], "Analysts reach restricted data they are cleared for, with an audit trail"),
    "catalogue": ("Governance", "Register every source in the data catalogue so each run searches all of them", "S", "Data Governance Office", ["Completeness", "Usage"], "No blind spots in sourcing"),
    "api-feeds": ("Automation", "Replace manual uploads and SFTP files with API feeds", "M", "Technology", ["Timeliness", "Validity"], "External data arrives on time without manual handling"),
    "owners": ("Governance", "Assign a data owner and steward for every external feed", "S", "Data Governance Office", ["Accuracy", "Consistency"], "Every issue has someone accountable"),
    "dq-rules": ("Quality", "Automate quality rules and critical-field reconciliation at ingestion", "M", "Data Governance Office", ["Accuracy", "Consistency", "Validity"], "Discrepancies caught before they reach a memo"),
    "escalation-sla": ("Governance", "Set escalation SLAs and an owner dashboard for open data issues", "S", "Data Governance Office", ["Accuracy", "Timeliness"], "Escalations closed within agreed days"),
    "certify-defs": ("Governance", "Approve and certify common definitions v1.0 through the data council", "S", "Data Governance Office", ["Consistency"], "One certified meaning for every metric"),
    "rating-align": ("Governance", "Reconcile internal and external ratings and record overrides", "S", "Credit Risk Management", ["Consistency"], "Rating differences explained in every memo"),
    "kyc-workflow": ("Automation", "Automate KYC refresh tracking with reminders and status feeds", "M", "KYC Operations", ["Timeliness"], "No memo held up by pending KYC"),
    "covenant-monitor": ("Automation", "Automated covenant monitoring that links compliance certificates and early-warning alerts", "M", "Credit Risk Management", ["Accuracy", "Business relevance"], "One covenant position, tested automatically"),
    "memo-automation": ("Automation", "Auto-populate credit memo fields from certified datasets", "M", "Credit analyst", ["Completeness", "Business relevance"], "Fewer fields typed by hand, faster memos"),
    "stale": ("Quality", "Refresh or retire records older than 90 days", "S", "Data owners", ["Timeliness"], "Only current data in the golden record"),
    "refresh-cycles": ("Technology", "Align feed refresh cycles to credit needs", "S", "Data owners", ["Timeliness"], "Slow feeds (annual, quarterly) refreshed in time for reviews"),
    "crosswalk": ("Technology", "Correct data dictionary crosswalk mappings and publish them in the semantic layer", "S", "Data Governance Office", ["Validity", "Consistency"], "Fields map to the right business terms"),
    "id-match": ("Technology", "Entity resolution linking internal and external identifiers", "M", "Technology", ["Consistency", "Accuracy"], "EIN, UEN and registry numbers resolve to one obligor"),
    "feed-recon": ("Quality", "Daily reconciliation of facility terms between Loan systems and market data", "M", "Loan operations", ["Accuracy", "Consistency"], "Facility amount, drawn and maturity agree everywhere"),
    "kpi-instrument": ("Reporting", "Capture workflow timestamps to measure time-to-memo and auto-resolution", "S", "Data Governance Office", ["Business relevance"], "Data KPIs measured, not estimated"),
    "portfolio-kpi": ("Reporting", "Portfolio KPI dashboard (watchlist, NPL, covenant breaches, concentration)", "M", "Credit Risk Management", ["Business relevance"], "Portfolio view alongside single-name memos"),
    "lineage": ("Technology", "Capture field-level lineage from source to memo", "M", "Technology", ["Validity", "Usage"], "Every memo value traceable automatically"),
    "ai-ready": ("AI readiness", "Build AI-ready certified datasets: feature store, synonyms and lineage metadata", "L", "Data & AI office", ["Usage", "Business relevance"], "Data that models and assistants can use safely"),
    "ai-assist": ("AI readiness", "AI-assisted memo drafting with confidence thresholds and human review", "M", "Data & AI office", ["Business relevance"], "Drafts in hours, with every AI value flagged for review"),
    "retention": ("Governance", "Apply the retention schedule and legal holds to credit files", "S", "Records management", ["Usage"], "Evidence kept as long as required, no longer"),
    "training": ("People & skills", "Data literacy training on definitions, confidence scores and escalation", "S", "Data Governance Office", ["Usage"], "Teams read and act on confidence scores"),
    "change": ("Change management", "Change plan for the new memo process with champions in each team", "S", "Transformation office", ["Usage"], "New process adopted, not bypassed"),
    "security": ("Security & privacy", "Mask personal data and log access to restricted fields", "M", "Information security", ["Usage"], "Privacy risk reduced without blocking analysts"),
    "vendor": ("Vendor management", "Data contracts and SLAs for every external provider", "S", "Procurement", ["Timeliness", "Accuracy"], "Providers accountable for quality and timeliness"),
}
GAP_STD = {"Missing data": "Fields the memo and template need that no source holds.", "Inaccessible data": "Data that exists but cannot be reached or used easily.",
           "Governance": "Ownership, stewardship, certification and escalation weaknesses.", "Processes": "Manual, slow or conflicting process steps.",
           "Integrations": "Mappings, identifiers and feeds that do not join up.", "KPI coverage": "Decisions and KPIs that cannot be measured yet."}
GAP_PICK = {"Lineage and metadata": "Field-level lineage and catalogue completeness.", "Data security and privacy": "Personal and restricted data handling.",
            "Regulatory alignment": "BCBS 239 and MAS reporting gaps.", "AI readiness": "Whether the data can safely feed models and assistants.",
            "Third-party data contracts": "External providers without owners or SLAs.", "Records retention": "Retention classes and legal holds on credit evidence."}
REC_STD = {"Governance": "Ownership, certification, escalation.", "Quality": "Rules, reconciliation, completeness.", "Reporting": "Financials and KPIs.",
           "Automation": "Manual steps removed.", "Technology": "Feeds, mappings, digitisation.", "AI readiness": "Data fit for AI."}
REC_PICK = {"People & skills": "Training and capability.", "Change management": "Adoption of the new process.", "Security & privacy": "Masking and access logging.",
            "Vendor management": "Contracts and SLAs with providers."}
CONF_DOMAINS = {"Borrower": (["2"], "Identity, ownership, group"), "Facility": (["4"], "Terms, drawn, maturity"), "Ratings & risk": (["6"], "Ratings, PD, LGD, EAD"),
                "Financials": (["5", "8"], "Performance and covenants"), "Compliance": (["12"], "KYC, AML, sanctions"), "ESG": (["13"], "ESG, climate, physical risk"),
                "Collateral & legal": (["7", "11"], "Security, documents, authority")}
CONF_STD_M = {"Quality": "Completeness, accuracy, consistency, validity of the values.", "Reliability": "Trust in the sources the values come from.",
              "Timeliness": "How current the values are.", "Governance": "Owners, certification and open issues."}
CONF_PICK = {"Treasury & funding": "Cost of funds, liquidity, hedging", "Market & industry": "External intelligence and outlook", "Relationship": "Exposure, revenue, prior events",
             "Lineage": "Share of values traceable to a source record", "Usage": "How widely the data is used (Assess)"}
EXTRA_DOM = {"Treasury & funding": ["10"], "Market & industry": ["9"], "Relationship": ["3"]}
ROAD_STD = {"Initiatives": "Recommendations grouped into fundable initiatives.", "Timelines": "Placed on the Phase 3 horizons.", "Outcomes": "What changes when each initiative lands.",
            "Benefits": "Confidence uplift and time saved.", "Business case": "Annual benefit, payback and 3-year value.", "Investment": "One-off and running cost by initiative."}
ROAD_PICK = {"Risks and dependencies": "What could delay each initiative.", "RACI": "Who is responsible, accountable, consulted, informed.",
             "KPIs to track": "How progress will be measured.", "Change and training plan": "How teams adopt the changes."}
HORIZONS = [["Stabilise", 0, 3], ["Standardise", 3, 6], ["Optimise", 6, 12], ["Transform", 12, 18]]
SCOPES = {"desk": {"t": "Structured debt desk (Singapore)", "d": "The team this case models"},
          "apac": {"t": "Asia Pacific (all corporate lending)", "d": "Regional rollout; wider than structured debt"}}
VOL_RANGE = {"desk": {"borrowers": [80, 120], "deals": [40, 80], "amend": [0.3, 0.5], "watch": [5, 10]},
             "apac": {"borrowers": [1500, 2500], "deals": [500, 900], "amend": [0.3, 0.4], "watch": [3, 8]}}
STEPS = {"gap": {"n": "6", "t": "Gap analyse", "h": "Gap analyse the data", "lbl": "Areas to analyse", "std": GAP_STD, "pick": GAP_PICK, "verb": "Run gap analysis"},
         "rec": {"n": "7", "t": "Recommendations", "h": "Data improvement recommendations", "lbl": "Categories", "std": REC_STD, "pick": REC_PICK, "verb": "Prioritise recommendations"},
         "conf": {"n": "8", "t": "Confidence levels", "h": "Confidence levels in existing data", "lbl": "Domains and measures",
                  "std": {**{k: v[1] for k, v in CONF_DOMAINS.items()}, **CONF_STD_M}, "pick": CONF_PICK, "verb": "Rate confidence"},
         "road": {"n": "9", "t": "Roadmap", "h": "Roadmap to improve data and decision-making", "lbl": "Roadmap contents", "std": ROAD_STD, "pick": ROAD_PICK, "verb": "Build roadmap"}}
ORDER = ["gap", "rec", "conf", "road"]


def new_state() -> dict:
    return {"sel": {k: list(STEPS[k]["std"]) for k in STEPS}, "extra": {k: [] for k in STEPS}, "R": {k: None for k in STEPS}, "approved": None, "stamp": None,
            "assume": {"scope": "desk", "rate": 120, "escPer": 4, "escH": 6, "costS": 25000, "costM": 90000, "costL": 250000, "run": 15, "scale": {"desk": 1, "apac": 2.5},
                       "hrs": {"review": 24, "deal": 40, "amend": 12, "watch": 16},
                       "vol": {"desk": {"borrowers": 100, "deals": 60, "amend": 0.4, "watch": 7.5, "freq": 2},
                               "apac": {"borrowers": 2000, "deals": 700, "amend": 0.35, "watch": 5, "freq": 1.5}}}}


def usd(v) -> str:
    if v is None:
        return "—"
    s = "−" if v < 0 else ""
    a = abs(v)
    return f"{s}USD {a / 1e6:.2f}m" if a >= 1e6 else f"{s}USD {round(a / 1000)}k"


def _mean(xs):
    v = [x for x in xs if x is not None]
    return sum(v) / len(v) if v else None


# ---------------- 6 · gaps ----------------
def run_gap(st, ctx) -> dict:
    """ctx: M (memo model), ST (memo stats), seek, collect, clean, norm, ds_full, owners, borrower"""
    M, ST, CL, NM = ctx["M"], ctx["ST"], ctx["clean"], ctx["norm"]
    c = ctx["borrower"]
    sel = set(st["sel"]["gap"]) | set(st["extra"]["gap"])
    G = []

    def add(area, gap, evidence, impact, fix, domain, owner=None):
        G.append({"area": area, "gap": gap, "evidence": evidence, "impact": impact, "fix": fix, "domain": domain, "owner": owner or REC_LIB[fix][3]})

    crit_fail = set(M["critFail"])
    seek = ctx.get("seek") or {"results": []}
    els = ctx["ds_full"].elements
    owners = ctx.get("owners") or {}
    ext_sources = sorted({r.source for r in ctx["ds_full"].records})
    if "Missing data" in sel:
        miss = [r["attribute"] for r in seek["results"] if r["status"] in ("miss", "pending")]
        ids = [a for a in miss if re.search("LEI|Tax ID", a)]
        prof = [a for a in miss if a not in ids]
        if ids:
            add("Missing data", f"{' and '.join(ids)} not held for {c}", "Seeker searched every internal and external location", "High", "mandatory-ids", "Borrower", "KYC Operations")
        if prof:
            add("Missing data", f"{len(prof)} borrower profile attributes not held", ", ".join(prof), "Low", "borrower-request", "Borrower")
        by_sec = {}
        for f in ST["missing"]:
            if f["sec"] != "2" or re.search("Sponsor|UBO|SIC", f["label"]):
                by_sec.setdefault(f["sec"], []).append(f["label"])
        for s, ls in by_sec.items():
            if s == "5":
                continue
            add("Missing data", f"{MM.SEC[s]['t'] if s in MM.SEC else 'Memo control'}: {len(ls)} template field{'s' if len(ls) > 1 else ''} not sourced", ", ".join(ls),
                "High" if s in ("12", "11", "6") else "Medium", "borrower-request",
                "Collateral & legal" if s in ("11", "7") else "Compliance" if s == "12" else "Facility" if s == "4" else "Borrower")
        add("Missing data", "Audited annual financials (FY-2, FY-1) not held", f"Trend built from {len(M['months'])} monthly observations instead", "High", "audited-fin", "Financials", "Credit analyst")
    if "Inaccessible data" in sel:
        phys = [e for e in els if e.source.startswith("Physical")]
        mail = [e for e in els if e.source == "Email archives"]
        if phys:
            m = INTERNAL["Physical / hard-copy records"]
            add("Inaccessible data", f"{len(phys)} physical and hard-copy elements need manual retrieval", f"Vault and archive boxes; {m['method'].lower()}, refreshed every {m['days']} days", "Medium", "digitise", "Collateral & legal")
        if mail:
            add("Inaccessible data", f"{len(mail)} email archive elements are unstructured", "Approvals, notices and CP checklists sit in message bodies and attachments", "Low", "email-index", "Collateral & legal")
        restr = [e for e in els if e.sensitivity.startswith("Restricted")]
        if restr:
            add("Inaccessible data", f"{len(restr)} restricted elements need clearance to use", ", ".join(dict.fromkeys(e.sensitivity.replace("Restricted – ", "") for e in restr)), "Medium", "access-model", "Compliance")
        scope = (ctx.get("collect") or {}).get("sources")
        internal = sorted({e.source for e in els})
        not_searched = [s for s in internal if scope and s not in scope]
        if not_searched:
            add("Inaccessible data", f"{len(not_searched)} internal sources not in the Collector's scope", ", ".join(not_searched), "Low", "catalogue", "Borrower")
    if "Governance" in sel:
        no_owner = [s for s in ext_sources if not meta(s, "External", owners)["owner"]]
        golden_src = [s for s in no_owner if any(p[0] == s for p in GOLD_PRIORITY.values())]
        if no_owner:
            add("Governance", f"{len(no_owner)} external feeds have no data owner", ", ".join(no_owner) + (f"; {', '.join(golden_src)} {'are golden sources' if len(golden_src) > 1 else 'is a golden source'}" if golden_src else ""),
                "High" if golden_src else "Medium", "owners", "Financials" if golden_src else "ESG")
        esc = CL["escalations"]
        if esc:
            add("Governance", f"{len(esc)} data issues escalated and still open", ", ".join(dict.fromkeys(e["owner"] for e in esc)), "High" if len(esc) > 10 else "Medium", "escalation-sla", "Compliance")
        if crit_fail and M["crit"]:
            add("Governance", f"{len(crit_fail)} of {len(M['crit']['rows'])} critical fields disagree across sources", ", ".join(LABEL[f].lower() for f in crit_fail), "High", "dq-rules", "Facility")
        add("Governance", "Common definitions v1.0 published but not yet certified", "Certification pending reviewer sign-off (Normalise)", "Medium", "certify-defs", "Financials")
        rg = next((x for x in M["CH"] if x["check"] == "Internal vs external rating" and x["result"] != "Pass"), None)
        if rg:
            add("Governance", "Internal and external ratings far apart", rg["evidence"], "Medium", "rating-align", "Ratings & risk")
    if "Processes" in sel:
        kyc = next((x for x in M["CH"] if x["check"] == "KYC complete" and x["result"] != "Pass"), None)
        if kyc:
            add("Processes", "KYC refresh not completed before the memo", kyc["evidence"], "High", "kyc-workflow", "Compliance")
        for r in M["COV"]:
            if r["status"] == "Conflict":
                add("Processes", f"{r['name']} covenant: compliance figure and early-warning alert disagree", r["note"], "High", "covenant-monitor", "Financials")
        manual = ST["manual"] + ST["edited"]
        add("Processes", f"{manual + len(ST['missing'])} memo fields still typed or chased by hand", f"{manual} for the RM or reviewer, {len(ST['missing'])} not sourced, of {ST['total']}",
            "Medium" if manual + len(ST["missing"]) > 15 else "Low", "memo-automation", "Borrower")
        stale = ctx.get("stale", 0)
        total = CL.get("total") or 0
        if stale and total:
            add("Processes", f"{stale} external records older than 90 days", f"{round(stale / total * 100)}% of {total} records", "Medium" if stale / total > 0.15 else "Low", "stale", "ESG")
        slow = [(s, EXTERNAL[s]) for s in ext_sources if s in EXTERNAL and EXTERNAL[s]["days"] > 90]
        if slow:
            add("Processes", f"{len(slow)} feeds refresh less often than quarterly reviews need", ", ".join(f"{s} ({m['cycle'].lower()})" for s, m in slow), "Low", "refresh-cycles", "ESG")
    if "Integrations" in sel:
        if "Registration_Number" in crit_fail:
            internal_reg = next((e.value for e in els if e.element.lower().startswith("company registration number")), "—")
            add("Integrations", "Internal and external identifiers do not resolve to one entity", f"Golden {M['F']['2|Registration Number']['v']} vs internal {internal_reg}", "High", "id-match", "Borrower")
        fac_f = [f for f in ("Facility_Amount", "Outstanding_Principal", "Maturity_Date") if f in crit_fail]
        if fac_f:
            add("Integrations", "Facility terms differ between Loan systems and market data", ", ".join(LABEL[f].lower() for f in fac_f), "High", "feed-recon", "Facility")
        manual_feeds = [(s, EXTERNAL[s]) for s in ext_sources if s in EXTERNAL and re.search("manual|sftp", EXTERNAL[s]["method"], re.I)]
        if manual_feeds:
            add("Integrations", f"{len(manual_feeds)} external feeds arrive by file or manual upload", ", ".join(f"{s} ({m['method']})" for s, m in manual_feeds), "Medium", "api-feeds", "Financials")
    if "KPI coverage" in sel:
        K = [k for k in (NM or {}).get("out", {}).get("KPIs", {}).get("rows", []) if k[6] == "na"]
        if K:
            add("KPI coverage", f"{len(K)} KPIs have no value yet", ", ".join(k[0] for k in K), "Medium", "kpi-instrument", "Financials")
        add("KPI coverage", "Time to memo cannot be measured", "No workflow timestamps captured", "Medium", "kpi-instrument", "Borrower")
        add("KPI coverage", "Portfolio KPIs defined but not calculated", "Watchlist %, NPL ratio, covenant breaches and concentration need a portfolio run", "Medium", "portfolio-kpi", "Ratings & risk")
        br = M["last"]["dims"].get("Business relevance")
        if br is not None and br < 70:
            add("KPI coverage", f"Business relevance only {br}/100", "Several decision metrics are not calculable from the data held", "High", "memo-automation", "Financials")
    if "Lineage and metadata" in sel:
        add("Lineage and metadata", "Lineage known at system level only", f"{len(INTERNAL) + len(EXTERNAL)} data flows mapped; no field-level lineage", "Medium", "lineage", "Financials")
    if "Data security and privacy" in sel:
        pii = [e for e in els if "Personal" in e.sensitivity]
        add("Data security and privacy", f"{len(pii)} personal-data elements held across sources", ", ".join(dict.fromkeys(e.source for e in pii)), "Medium" if pii else "Low", "security", "Compliance")
    if "Regulatory alignment" in sel:
        add("Regulatory alignment", "BCBS 239 evidence incomplete", f"Missing LEI and Tax ID; {len(crit_fail)} critical fields unreconciled; lineage at system level", "High", "dq-rules", "Compliance", "Regulatory reporting")
    if "AI readiness" in sel:
        add("AI readiness", f"Data confidence {M['last'].get('pct')}% ({MM.WORD.get(M['capR']['r'], '—')}) is below the 90% bar for unattended AI use",
            f"{ST['pctAuto']}% of memo fields filled automatically; {M['capR']['cap'] or 'no single weak criterion'}", "Medium", "ai-ready", "Financials")
    if "Third-party data contracts" in sel:
        add("Third-party data contracts", f"{len(ext_sources)} external providers without recorded SLAs", ", ".join(ext_sources), "Low", "vendor", "Financials")
    if "Records retention" in sel:
        add("Records retention", "Retention classes held only for email", "Credit files, models and physical originals lack a retention class", "Low", "retention", "Collateral & legal")
    for i, g in enumerate(G):
        g["id"] = f"G-{i + 1:02d}"
    return {"G": G}


# ---------------- 7 · recommendations ----------------
def run_rec(st) -> dict:
    G = st["R"]["gap"]["G"]
    cats = set(st["sel"]["rec"]) | set(st["extra"]["rec"])
    by_fix: dict[str, list] = {}
    for g in G:
        by_fix.setdefault(g["fix"], []).append(g)
    for cat, k in {"People & skills": "training", "Change management": "change", "Security & privacy": "security", "Vendor management": "vendor"}.items():
        if cat in cats and k not in by_fix:
            by_fix[k] = []
    if "AI readiness" in cats and "ai-assist" not in by_fix:
        by_fix["ai-assist"] = [g for g in G if g["fix"] == "memo-automation"]
    R = []
    for k, gs in by_fix.items():
        cat, t, e, owner, dims, out = REC_LIB[k]
        if cat not in cats:
            continue
        imp = max((IMPACT_N[g["impact"]] for g in gs), default=2)
        hi = imp >= 3 or (imp == 2 and len(gs) >= 3)
        quad = ("Quick win" if e == "S" else "Major project") if hi else ("Fill-in" if e == "S" else "Later")
        R.append({"k": k, "cat": cat, "t": t, "e": e, "effort": EFFORT_W[e], "owner": owner, "dims": dims, "out": out, "gaps": [g["id"] for g in gs],
                  "impact": ["", "Low", "Medium", "High"][imp], "quad": quad, "score": imp * 3 + len(gs) - EFFORT_N[e] * 2,
                  "domains": list(dict.fromkeys(g["domain"] for g in gs))})
    QO = {"Quick win": 0, "Major project": 1, "Fill-in": 2, "Later": 3}
    R.sort(key=lambda r: (QO[r["quad"]], -r["score"]))
    for i, r in enumerate(R):
        r["rank"], r["id"] = i + 1, f"R-{i + 1:02d}"
    return {"R": R}


# ---------------- 8 · confidence ----------------
def domain_scores(M, secs, extra_measures, ctx):
    fs = MM.fields_in(M, secs)
    filled = [f for f in fs if f["kind"] != "missing"]
    r = MM.dom_score(M, secs, ctx["ref_date"]) or {}
    q = _mean([r.get("Completeness"), r.get("Accuracy"), r.get("Consistency"), r.get("Validity")])
    quality = round(q) if q is not None else None

    def rel_of(f):
        if f["kind"] in ("golden", "external"):
            return RELIABILITY.get(f["srcFull"], 0.8) * 100
        if f["kind"] == "internal":
            return 90 if f["srcFull"] in MM.SOR else 70
        return 80 if f["kind"] == "calc" else 65 if f["kind"] == "draft" else 75
    reliability = round(sum(rel_of(f) for f in filled) / len(filled)) if filled else None
    owners = ctx.get("owners") or {}
    srcs = list(dict.fromkeys(f["srcFull"] for f in filled if f["srcFull"] in EXTERNAL))
    no_own = [s for s in srcs if not meta(s, "External", owners)["owner"]]
    esc_n = sum(1 for e in ctx["clean"]["escalations"] if any(e["item"].lower().find(f["label"].lower().split(" ")[0]) >= 0 for f in fs)
                or ("12" in secs and re.search("sanction|kyc", e["item"], re.I)))
    chk_bad = sum(1 for x in M["CH"] if ((("12" in secs) and x["area"] in ("KYC & AML", "Sanctions")) or ("11" in secs and x["area"] == "Legal")
                                         or ("8" in secs and x["area"] == "Covenants") or ("6" in secs and x["area"] == "Credit policy")) and x["result"] != "Pass")
    gov = max(0, 100 - (20 if no_own else 0) - min(40, esc_n * 10) - 10 - min(30, chk_bad * 10))
    why = {"Quality": f"{r.get('Completeness', '—')}% complete, {r.get('Accuracy', '—')}% from validated sources",
           "Reliability": f"{len(filled)} values from {', '.join(list(dict.fromkeys(f['src'] for f in filled))[:3])}",
           "Timeliness": "No dated values" if r.get("Timeliness") is None else f"{r['Timeliness']}% of dated values within 90 days",
           "Governance": (f"no owner for {', '.join(no_own)}; " if no_own else "") + f"{esc_n} open escalations; {chk_bad} failed or exception checks; definitions not certified"}
    S = {"Quality": quality, "Reliability": reliability, "Timeliness": r.get("Timeliness"), "Governance": gov}
    if "Lineage" in extra_measures:
        S["Lineage"] = round(sum(1 for f in filled if f.get("rec") or f["kind"] == "calc") / len(filled) * 100) if filled else None
        why["Lineage"] = "Values with a source record ID or a calculation"
    if "Usage" in extra_measures:
        S["Usage"] = M["last"]["dims"].get("Usage")
        why["Usage"] = "Assess usage score"
    return {"S": S, "why": why, "fields": len(fs), "filled": len(filled)}


def run_conf(st, ctx) -> dict:
    M = ctx["M"]
    sel = list(dict.fromkeys(st["sel"]["conf"] + st["extra"]["conf"]))
    meas = [x for x in sel if x in CONF_STD_M or x in ("Lineage", "Usage")]
    doms = [x for x in sel if x in CONF_DOMAINS or x in EXTRA_DOM]
    D = []
    for d in doms:
        secs = CONF_DOMAINS[d][0] if d in CONF_DOMAINS else EXTRA_DOM[d]
        s = domain_scores(M, secs, meas, ctx)
        vals = [s["S"][m] for m in meas if s["S"].get(m) is not None]
        overall = round(sum(vals) / len(vals)) if vals else 0
        weak = [m for m in meas if s["S"].get(m) is not None and s["S"][m] < 60]
        rate = "High" if overall >= 85 and not weak else "Medium" if overall >= 60 else "Low"
        gaps = [g["id"] for g in st["R"]["gap"]["G"] if g["domain"] == d]
        D.append({"d": d, "secs": secs, **s, "overall": overall, "rate": rate, "weak": weak, "fit": "Yes" if rate == "High" else "With caveats" if rate == "Medium" else "No", "gaps": gaps})
    return {"D": D, "meas": meas, "p1": M["last"].get("pct")}


# ---------------- 9 · roadmap ----------------
INIT_GROUPS = [["Governance foundations", ["Governance"]], ["Data quality automation", ["Quality"]], ["Integration and feeds", ["Technology"]],
               ["Process automation", ["Automation"]], ["Reporting and KPIs", ["Reporting"]], ["AI readiness", ["AI readiness"]],
               ["People, change and controls", ["People & skills", "Change management", "Security & privacy", "Vendor management"]]]


def horizon_of(r):
    if r["cat"] == "AI readiness":
        return 3 if r["e"] == "L" else 2
    if r["quad"] in ("Quick win", "Fill-in"):
        return 0
    if r["quad"] == "Major project":
        return 2 if r["e"] == "L" else 1
    return 2


def memo_volume(v, H):
    rows = [["review", "Annual reviews", v["borrowers"]], ["deal", "New deals and refinancings", v["deals"]],
            ["amend", "Amendments, waivers, increases, extensions", round(v["borrowers"] * v["amend"])],
            ["watch", "Watchlist and problem-loan reviews", round(v["borrowers"] * v["watch"] / 100 * v["freq"])]]
    rows = [{"k": k, "t": t, "n": n, "h": H[k], "hours": n * H[k]} for k, t, n in rows]
    n = sum(r["n"] for r in rows)
    hours = sum(r["hours"] for r in rows)
    return {"rows": rows, "n": n, "hours": hours, "avg": hours / n if n else 0}


def biz_case(A, v, inv_base, auto_share):
    V = memo_volume(v, A["hrs"])
    scale = A["scale"].get(A["scope"], 1)
    inv = inv_base * scale
    run = inv * A["run"] / 100
    time_ben = V["hours"] * auto_share * A["rate"]
    esc_ben = V["n"] * A["escPer"] * A["escH"] * A["rate"] * 0.6
    annual = time_ben + esc_ben - run
    return {"V": V, "inv": inv, "run": run, "timeBen": time_ben, "escBen": esc_ben, "annual": annual,
            "payback": math.ceil(inv / annual * 12) if annual > 0 else None, "net3": annual * 3 - inv}


def run_road(st, ctx) -> dict:
    R = st["R"]["rec"]["R"]
    A = st["assume"]
    cost = {"S": A["costS"], "M": A["costM"], "L": A["costL"]}
    I = []
    for gi, (name, cats) in enumerate(INIT_GROUPS):
        rs = [r for r in R if r["cat"] in cats]
        if not rs:
            continue
        hs = [horizon_of(r) for r in rs]
        inv = sum(cost[r["e"]] for r in rs)
        I.append({"id": f"I-{gi + 1:02d}", "name": name, "recs": [r["id"] for r in rs], "start": HORIZONS[min(hs)][1], "end": HORIZONS[max(hs)][2],
                  "hz": [HORIZONS[h][0] for h in sorted(set(hs))], "inv": inv, "run": round(inv * A["run"] / 100),
                  "doms": list(dict.fromkeys(d for r in rs for d in r["domains"])), "dims": list(dict.fromkeys(d for r in rs for d in r["dims"])),
                  "gaps": sum(len(r["gaps"]) for r in rs), "out": "; ".join(r["out"] for r in rs[:2]), "owner": rs[0]["owner"]})
    D = st["R"]["conf"]["D"]
    G = st["R"]["gap"]["G"]
    target = []
    for d in D:
        closed = sum(1 for g in G if g["domain"] == d["d"])
        target.append({"d": d["d"], "now": d["overall"], "to": min(95, d["overall"] + round((100 - d["overall"]) * min(0.7, 0.15 + closed * 0.12)))})
    auto_share = min(0.75, 0.3 + sum(1 for r in R if r["cat"] in ("Automation", "AI readiness")) * 0.08)
    scale = A["scale"].get(A["scope"], 1)
    for i in I:
        i["inv"] = round(i["inv"] * scale)
        i["run"] = round(i["inv"] * A["run"] / 100)
    inv_base = sum(i["inv"] for i in I) / scale
    v, rg = A["vol"][A["scope"]], VOL_RANGE[A["scope"]]
    B = biz_case(A, v, inv_base, auto_share)
    h_now = round(B["V"]["avg"] * 10) / 10
    h_after = round(h_now * (1 - auto_share) * 10) / 10

    def pick(i):
        return {**v, "borrowers": rg["borrowers"][i], "deals": rg["deals"][i], "amend": rg["amend"][i], "watch": rg["watch"][i]}
    SC = [["Low", biz_case(A, pick(0), inv_base, auto_share)], ["Base", B], ["High", biz_case(A, pick(1), inv_base, auto_share)]]
    top = sorted(B["V"]["rows"], key=lambda r: -r["n"])[0]
    return {"I": I, "target": target, "hNow": h_now, "hAfter": h_after, "autoShare": auto_share, "V": B["V"], "SC": SC, "top": top, "scope": A["scope"],
            "timeBen": B["timeBen"], "escBen": B["escBen"], "invTot": B["inv"], "runTot": B["run"], "annual": B["annual"], "payback": B["payback"], "net3": B["net3"],
            "roi": B["net3"] / B["inv"] if B["inv"] else None, "escNow": len(ctx["clean"]["escalations"])}


def can(st, k) -> bool:
    return k == "gap" or (k == "rec" and st["R"]["gap"]) or (k == "conf" and st["R"]["rec"]) or (k == "road" and st["R"]["conf"])


def blocks(st, borrower, ref_ymd) -> list[dict]:
    G, R, D, RD = st["R"]["gap"]["G"], st["R"]["rec"]["R"], st["R"]["conf"], st["R"]["road"]
    ap = st.get("approved")
    B = [{"t": "title", "kicker": "Data360 · Phase 2 · Improve & Plan", "title": "Gap analysis, confidence and roadmap", "sub": borrower,
          "meta": [["Client", borrower], ["Date", ref_ymd], ["Phase 1 confidence", f"{D['p1']}%"], ["Gaps", str(len(G))], ["Recommendations", str(len(R))],
                   ["Roadmap", f"Approved by {ap['by']}, {ap['at']}" if ap else "Draft"]]},
         {"t": "h1", "text": "Summary"},
         {"t": "callout", "tone": "warn", "text": f"{len(G)} gaps ({sum(1 for g in G if g['impact'] == 'High')} high impact) lead to {len(R)} recommendations and {len(RD['I'])} initiatives. "
                                                 f"Investment {usd(RD['invTot'])}; net annual benefit {usd(RD['annual'])}" + (f"; payback {RD['payback']} months" if RD["payback"] else "") + "."},
         {"t": "h1", "text": "6. Gap analysis"}, {"t": "table", "head": ["ID", "Area", "Gap", "Evidence", "Impact"], "widths": [8, 16, 30, 34, 12], "small": True,
                                                  "rows": [[g["id"], g["area"], g["gap"], g["evidence"], g["impact"]] for g in G]},
         {"t": "h1", "text": "7. Recommendations"}, {"t": "table", "head": ["ID", "Recommendation", "Category", "Impact", "Effort", "Priority", "Owner"], "widths": [7, 37, 12, 9, 9, 12, 14], "small": True,
                                                     "rows": [[r["id"], r["t"], r["cat"], r["impact"], r["effort"], r["quad"], r["owner"]] for r in R]},
         {"t": "h1", "text": "8. Confidence levels"},
         {"t": "table", "head": ["Domain", *D["meas"], "Overall", "Rating", "Fit"], "widths": [18, *[round(50 / max(1, len(D["meas"])))] * len(D["meas"]), 10, 10, 12], "small": True,
          "rows": [[d["d"], *[str(d["S"].get(m) if d["S"].get(m) is not None else "—") for m in D["meas"]], f"{d['overall']}%", d["rate"], d["fit"]] for d in D["D"]]},
         {"t": "h1", "text": "9. Roadmap"}, {"t": "table", "head": ["ID", "Initiative", "Months", "Horizon", "One-off", "Owner"], "widths": [7, 28, 11, 24, 12, 18], "small": True,
                                             "rows": [[i["id"], i["name"], f"{i['start']}–{'12+' if i['end'] == 18 else i['end']}", " → ".join(i["hz"]), usd(i["inv"]), i["owner"]] for i in RD["I"]]},
         {"t": "h2", "text": f"Memo volume · {SCOPES[RD['scope']]['t']}"},
         {"t": "table", "head": ["Memo type", "Memos / yr", "Hours each", "Hours / yr"], "widths": [46, 18, 16, 20], "num": [1, 2, 3],
          "rows": [*[[r["t"], str(r["n"]), str(r["h"]), f"{r['hours']:,}"] for r in RD["V"]["rows"]], ["Total", str(RD["V"]["n"]), f"{RD['hNow']} avg", f"{RD['V']['hours']:,}"]]},
         {"t": "p", "muted": True, "text": f"{RD['top']['t']} are the largest share ({round(RD['top']['n'] / RD['V']['n'] * 100)}%): every borrower needs one each year. "
                                           "Volumes are Data360 estimates; replace them with a 12-month count of credit applications by type from credit administration."},
         {"t": "h2", "text": "Scenarios"}, {"t": "table", "head": ["Scenario", "Memos / yr", "Net annual benefit", "Payback", "3-year net value"], "widths": [18, 16, 24, 18, 24], "num": [1, 2, 4],
                                            "rows": [[n, str(b["V"]["n"]), usd(b["annual"]), f"{b['payback']} months" if b["payback"] else "—", usd(b["net3"])] for n, b in RD["SC"]]},
         {"t": "h2", "text": "Business case (illustrative assumptions)"},
         {"t": "table", "head": ["Item", "Value"], "widths": [60, 40], "rows": [["Analyst time saved / yr", usd(RD["timeBen"])], ["Fewer escalations / yr", usd(RD["escBen"])],
                                                                               ["Running cost / yr", usd(-RD["runTot"])], ["Net annual benefit", usd(RD["annual"])],
                                                                               ["One-off investment", usd(RD["invTot"])], ["Payback", f"{RD['payback']} months" if RD["payback"] else "—"],
                                                                               ["3-year net value", usd(RD["net3"])]]},
         {"t": "h2", "text": "Confidence targets"}, {"t": "table", "head": ["Domain", "Today", "Target"], "widths": [50, 25, 25], "rows": [[t["d"], f"{t['now']}%", f"{t['to']}%"] for t in RD["target"]]}]
    return B


# ---------------- views (server-described sections) ----------------
def _imp(i):
    from . import ui
    return ui.chip({"High": "bad", "Medium": "warn"}.get(i, "idle"), i)


def results_view(st, k, ctx) -> list[dict]:
    from . import ui
    R = st["R"][k]
    if not R:
        return []
    c = ctx["borrower"]
    if k == "gap":
        G = R["G"]
        areas = list(dict.fromkeys(g["area"] for g in G))
        hi = sum(1 for g in G if g["impact"] == "High")
        cards = []
        for a in areas:
            g = [x for x in G if x["area"] == a]
            w = "low" if any(x["impact"] == "High" for x in g) else "med" if any(x["impact"] == "Medium" for x in g) else "high"
            cards.append({"title": a, "rate": w, "chip": ["bad" if w == "low" else "warn" if w == "med" else "ok", f"{len(g)} gap{'s' if len(g) > 1 else ''}"],
                          "hint": "; ".join(x["gap"] for x in g[:2]) + ("…" if len(g) > 2 else "")})
        return [ui.section("Gap register", c, [
            ui.headline(f"**{len(G)}** gaps across **{len(areas)}** areas; **{hi}** high impact."),
            ui.kpis([(len(G), "Gaps"), (hi, "High impact", "bad"), (sum(1 for g in G if g["impact"] == "Medium"), "Medium", "warn"), (sum(1 for g in G if g["impact"] == "Low"), "Low")]),
            {"type": "cards", "items": cards},
            ui.table(["ID", "Area", "Gap", "Evidence", "Impact", "Domain", "Owner"],
                     [[ui.mono(g["id"]), ui.hint(g["area"]), ui.bold(g["gap"]), ui.hint(g["evidence"]), _imp(g["impact"]), ui.hint(g["domain"]), ui.hint(g["owner"])] for g in G])],
            foot={"hint": "Each gap feeds a recommendation in step 7.", "next": {"label": "Continue to Recommendations →", "step": "rec"}})]
    if k == "rec":
        R_ = R["R"]
        QD = {"Quick win": "High impact · small effort", "Major project": "High impact · bigger effort", "Fill-in": "Lower impact · small effort", "Later": "Lower impact · bigger effort"}
        return [ui.section("Prioritised recommendations", f"{len(R_)} from {len(st['R']['gap']['G'])} gaps", [
            ui.headline(f"**{sum(1 for r in R_ if r['quad'] == 'Quick win')}** quick wins and **{sum(1 for r in R_ if r['quad'] == 'Major project')}** major projects; "
                        f"{sum(1 for r in R_ if r['quad'] in ('Fill-in', 'Later'))} lower-priority items."),
            {"type": "matrix", "quads": [{"q": q, "d": QD[q], "cls": "qw" if q == "Quick win" else "mp" if q == "Major project" else "",
                                          "items": [{"id": r["id"], "t": r["t"]} for r in R_ if r["quad"] == q]} for q in QD]},
            ui.table(["#", "Recommendation", "Category", "Impact", "Effort", "Priority", "Gaps", "Owner"],
                     [[ui.mono(r["id"]), ui.bold(r["t"], r["out"]), ui.hint(r["cat"]), _imp(r["impact"]), ui.hint(r["effort"]),
                       ui.chip("ok" if r["quad"] == "Quick win" else "info" if r["quad"] == "Major project" else "idle", r["quad"]),
                       ui.mono(", ".join(r["gaps"]) or "—"), ui.hint(r["owner"])] for r in R_])],
            foot={"hint": "Quick wins first, then major projects. Effort is a planning estimate.", "next": {"label": "Continue to Confidence levels →", "step": "conf"}})]
    if k == "conf":
        D, meas, p1 = R["D"], R["meas"], R["p1"]
        avg = round(sum(d["overall"] for d in D) / len(D)) if D else 0
        rows = [[ui.bold(d["d"], f"{d['filled']} of {d['fields']} fields · {len(d['gaps'])} gaps"),
                 *[ui.cell(d["S"].get(m) if d["S"].get(m) is not None else "—", "hc " + ui.heat(d["S"].get(m)), d["why"].get(m, "")) for m in meas],
                 ui.cell(d["overall"], "hc " + ui.heat(d["overall"]), strong=True),
                 ui.group(ui.chip("ok" if d["rate"] == "High" else "warn" if d["rate"] == "Medium" else "bad", d["rate"]), *([ui.hint("weak: " + ", ".join(d["weak"]))] if d["weak"] else [])),
                 d["fit"]] for d in D]
        return [ui.section("Confidence by domain", f"{len(D)} domains · {len(meas)} measures", [
            ui.headline(f"Average domain confidence **{avg}%** (Phase 1 overall {p1}%). **{sum(1 for d in D if d['rate'] == 'High')}** high, "
                        f"**{sum(1 for d in D if d['rate'] == 'Medium')}** medium, **{sum(1 for d in D if d['rate'] == 'Low')}** low."),
            ui.table(["Domain", *meas, "Overall", "Rating", "Fit for credit decisions"], rows, num=list(range(1, len(meas) + 2))),
            ui.details("Evidence · what each score is based on", [ui.table(["Domain", "Measure", "Evidence"], [[d["d"], m, ui.hint(d["why"].get(m, "—"))] for d in D for m in meas])])],
            foot={"hint": "Scores: 85+ high, 60–84 medium, below 60 low. A domain with any measure below 60 can't rate high.", "next": {"label": "Continue to Roadmap →", "step": "road"}})]
    # road
    A = st["assume"]
    on = set(st["sel"]["road"]) | set(st["extra"]["road"])
    ap = st.get("approved")
    dis = bool(ap)
    out = [ui.headline(f"Invest **{usd(R['invTot'])}** for an annual net benefit of **{usd(R['annual'])}**" + (f"; payback in **{R['payback']} months**" if R["payback"] else "")
                       + f". Average memo effort falls from **{R['hNow']} h** to **{R['hAfter']} h** across **{R['V']['n']:,}** memos a year ({SCOPES[R['scope']]['t']}).")]
    if on & {"Initiatives", "Timelines"}:
        out += [ui.h3("Timeline"), {"type": "gantt", "W": 18, "scale": [{"n": n, "s": s, "e": e} for n, s, e in HORIZONS],
                                    "rows": [{"name": i["name"], "sub": f"{len(i['recs'])} recommendations · {i['gaps']} gaps", "start": i["start"], "end": i["end"]} for i in R["I"]]}]
    if on & {"Initiatives", "Outcomes", "Investment"}:
        head = ["ID", "Initiative", "Horizon", "Recommendations (step 7)"] + (["Outcome"] if "Outcomes" in on else []) + (["One-off", "Running / yr"] if "Investment" in on else []) + ["Owner"]
        rows = [[ui.mono(i["id"]), ui.bold(i["name"]), " → ".join(i["hz"]), ui.mono(", ".join(i["recs"]))] + ([ui.hint(i["out"])] if "Outcomes" in on else [])
                + ([usd(i["inv"]), usd(i["run"])] if "Investment" in on else []) + [ui.hint(i["owner"])] for i in R["I"]]
        out += [ui.h3("Initiatives"), ui.table(head, rows, flat=False),
                ui.hint_block("R-numbers are the recommendation IDs from step 7. Each initiative bundles those recommendations.")]
    if "Benefits" in on:
        out += [ui.h3("Benefits: confidence by domain"), ui.table(["Domain", "Today", "Target", "Uplift"], [[t["d"], f"{t['now']}%", ui.bold(f"{t['to']}%"), ui.uplift(t["now"], t["to"])] for t in R["target"]], num=[1, 2], flat=False),
                ui.hint_block(f"Targets assume the gaps in each domain close on plan. Memo effort: {R['hNow']} h → {R['hAfter']} h per memo on average ({round(R['autoShare'] * 100)}% automated).")]
    if "Business case" in on:
        v = A["vol"][A["scope"]]
        V = R["V"]["rows"]
        ni = lambda key, val, step="any": ui.num_input("p2.assume", key, val, step, dis)  # noqa: E731
        out += [ui.h3("Business case"),
                {"type": "radio", "action": "p2.scope", "value": A["scope"], "disabled": dis, "options": [{"k": k2, "t": x["t"], "d": x["d"]} for k2, x in SCOPES.items()]},
                ui.h3("Memo volume"),
                ui.table(["Memo type", "Driver", "Memos / yr", "Hours each today", "Hours / yr"], [
                    [ui.bold("Annual reviews", "Every borrower, every year"), ui.group(ni("v:borrowers", v["borrowers"], 1), ui.hint("borrowers")), f"{V[0]['n']:,}", ni("h:review", A["hrs"]["review"]), f"{V[0]['hours']:,}"],
                    [ui.bold("New deals and refinancings"), ui.group(ni("v:deals", v["deals"], 1), ui.hint("a year")), f"{V[1]['n']:,}", ni("h:deal", A["hrs"]["deal"]), f"{V[1]['hours']:,}"],
                    [ui.bold("Amendments, waivers, increases, extensions"), ui.group(ni("v:amend", v["amend"], 0.05), ui.hint("per borrower")), f"{V[2]['n']:,}", ni("h:amend", A["hrs"]["amend"]), f"{V[2]['hours']:,}"],
                    [ui.bold("Watchlist and problem-loan reviews"), ui.group(ni("v:watch", v["watch"], 0.5), ui.hint("% of borrowers ×"), ni("v:freq", v["freq"], 0.5), ui.hint("a year")),
                     f"{V[3]['n']:,}", ni("h:watch", A["hrs"]["watch"]), f"{V[3]['hours']:,}"],
                    [ui.bold("Total"), "", ui.bold(f"{R['V']['n']:,}"), ui.bold(f"{R['hNow']} avg"), ui.bold(f"{R['V']['hours']:,}")]], num=[2, 3, 4], row_class=["", "", "", "", "tot"], flat=False),
                ui.notes([f"{R['top']['t']} are the largest share ({round(R['top']['n'] / R['V']['n'] * 100) if R['V']['n'] else 0}% of memos), because every borrower needs one each year whether or not anything new happens.",
                          "These volumes are Data360 estimates, not bank figures. Replace them with a 12-month count of credit applications by type from credit administration.",
                          "The Asia Pacific scope is wider than structured debt; label it as a regional rollout when presenting." if A["scope"] == "apac" else "Switch to the Asia Pacific scope to see the regional rollout case."]),
                ui.h3("Cost and benefit assumptions"),
                {"type": "assume", "items": [{"label": l, "unit": u, "input": ni(key, A["scale"][A["scope"]] if key == "scale" else A[key])} for key, l, u in [
                    ["rate", "Loaded cost per hour", "USD"], ["escPer", f"Escalations per memo ({c} had {R['escNow']})", ""], ["escH", "Hours per escalation", "h"],
                    ["run", "Running cost", "% of investment / yr"], ["costS", "Small initiative cost", "USD"], ["costM", "Medium initiative cost", "USD"], ["costL", "Large initiative cost", "USD"],
                    ["scale", f"Rollout cost multiplier ({'Asia Pacific' if A['scope'] == 'apac' else 'desk'})", "×"]]]},
                ui.h3("Scenarios"),
                ui.table(["Scenario", "Memos / yr", "Net annual benefit", "Payback", "3-year net value"],
                         [[ui.bold(n, "Your inputs above" if n == "Base" else f"{'Lower' if n == 'Low' else 'Upper'} end of the volume range"), f"{b['V']['n']:,}", usd(b["annual"]),
                           f"{b['payback']} months" if b["payback"] else "Not within 3 years", usd(b["net3"])] for n, b in R["SC"]], num=[1, 2, 3, 4], row_class=["", "tot", ""], flat=False),
                ui.h3("Base case"),
                ui.table(["Item", "Annual value"], [["Analyst time saved", usd(R["timeBen"])], ["Fewer escalations and rework", usd(R["escBen"])], ["Running cost", usd(-R["runTot"])],
                                                    ["Net annual benefit", usd(R["annual"])], ["One-off investment", usd(R["invTot"])], ["Payback", f"{R['payback']} months" if R["payback"] else "Not within 3 years"],
                                                    ["3-year net value", usd(R["net3"])], ["3-year ROI", "—" if R["roi"] is None else f"{round(R['roi'] * 100)}%"]], num=[1], flat=False)]
    if "Risks and dependencies" in on:
        out += [ui.h3("Risks and dependencies"), ui.table(["Initiative", "Depends on", "Main risk"], [[i["name"],
                "Data council mandate" if i["name"] == "Governance foundations" else "Data quality automation, Integration and feeds" if i["name"] == "AI readiness" else "Governance foundations (owners named)",
                "Vendor API availability and cost" if i["name"] == "Integration and feeds" else "Confidence must reach 90% first" if i["name"] == "AI readiness" else "Adoption by RMs and analysts" if i["name"] == "Process automation" else "Owner capacity"] for i in R["I"]], flat=False)]
    if "RACI" in on:
        out += [ui.h3("RACI"), ui.table(["Initiative", "Responsible", "Accountable", "Consulted", "Informed"], [[i["name"], i["owner"], "Chief Data Officer", "Credit Risk Management, Technology", "Credit Committee"] for i in R["I"]], flat=False)]
    if "KPIs to track" in on:
        ext = sorted({r.source for r in ctx["ds_full"].records})
        owned = sum(1 for s in ext if meta(s, "External", ctx.get("owners") or {})["owner"])
        out += [ui.h3("KPIs to track"), ui.table(["KPI", "Today", "Target"], [["Data confidence", f"{st['R']['conf']['p1']}%", "90%+"], ["Open escalations", str(R["escNow"]), "< 5"],
                                                                             ["Average hours per memo", f"{R['hNow']} h", f"{R['hAfter']} h"], ["Memo fields filled automatically", f"{ctx['ST']['pctAuto']}%", "90%"],
                                                                             ["External feeds with an owner", f"{owned} of {len(ext)}", "All"]], flat=False)]
    if "Change and training plan" in on:
        out += [ui.h3("Change and training plan"), ui.notes(["Months 0–1: brief Credit Committee and RMs on confidence scores and the new memo flow.",
                                                             "Months 1–3: train analysts on definitions v1.0 and escalation SLAs; name champions per team.",
                                                             "Months 3–6: run old and new memo processes side by side for one portfolio; compare time and quality.",
                                                             "Month 6 onward: retire manual steps as each initiative lands; refresh training quarterly."])]
    foot = {"hint": f"Approved by {ap['by']} on {ap['at']}. Phase 2 cleared; Phase 3 unlocked." if ap else "Approving the roadmap clears Phase 2 and unlocks Phase 3.",
            "download": {"label": "Phase 2 report (.docx)", "href": "report/p2.docx"}}
    if not ap:
        foot["approve"] = {"action": "p2.approve", "label": "Approve roadmap", "placeholder": "Approver name"}
    return [ui.section("Roadmap", f"{len(R['I'])} initiatives over 18 months", out, foot=foot)]
