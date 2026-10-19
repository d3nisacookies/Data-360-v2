"""Step 4 · Normalise: one definition per metric, KPI thresholds, the obligor master record,
conformed reporting dimensions and a semantic layer (glossary, synonyms, field mapping)."""
from .core import Dataset, golden
from .reference import FIELDS, INTERNAL_GRADE, LABEL, GOLD_PRIORITY
from .values import is_blank, norm_country, parse_number, parse_percent

ITEMS = {
    "Metrics": "One approved formula, basis and unit per measure, calculated from the golden record.",
    "KPIs": "Thresholds, RAG bands, owners and frequency for the measures that drive decisions.",
    "Master data": "One obligor record linking every ID and name variant.",
    "Reporting dimensions": "Conformed time, geography, product, sector, rating and currency.",
    "Semantic layer": "Business glossary, term-to-field mapping and synonyms.",
}


def usd(v):
    if v is None:
        return "—"
    return f"USD {v / 1e9:.2f}bn" if abs(v) >= 1e9 else f"USD {v / 1e6:.1f}m"


def x(v):
    return "—" if v is None else f"{v:.2f}x"


def p(v):
    return "—" if v is None else f"{v * 100:.1f}%"


def rag(v, green, amber, higher_better=True):
    if v is None:
        return "na"
    if higher_better:
        return "g" if v >= green else "a" if v >= amber else "r"
    return "g" if v <= green else "a" if v <= amber else "r"


def normalise(ds: Dataset, assess_result: dict | None, clean_result: dict | None, selected: list[str] | None = None) -> dict:
    selected = [s for s in (selected or list(ITEMS)) if s in ITEMS] or list(ITEMS)
    G = golden(ds)

    def num(f):
        return parse_number(G[f]["value"]) if G.get(f) else None

    def src(f):
        return f"{G[f]['source']} ({G[f]['record']})" if G.get(f) else "—"

    rev, ebitda, fac, outp = num("Revenue"), num("EBITDA"), num("Facility_Amount"), num("Outstanding_Principal")
    nd, rep_lev, cov, coll, cr = num("Net_Debt"), num("Leverage"), num("Leverage_Covenant"), num("Collateral_Value"), num("Current_Ratio")
    rate = parse_percent(G["Interest_Rate"]["value"]) if G.get("Interest_Rate") else None
    mar = parse_percent(G["Margin"]["value"]) if G.get("Margin") else None
    lev = nd / ebitda if nd is not None and ebitda else None
    util = outp / fac if outp is not None and fac else None
    head = (cov - lev) / cov if cov and lev is not None else None
    ltv = outp / coll if outp is not None and coll else None
    out = {}

    M = [
        ["Revenue", "Total revenue", "LTM, as reported", "USD", usd(rev), src("Revenue")],
        ["EBITDA", "Earnings before interest, tax, depreciation and amortisation", "LTM, reported", "USD", usd(ebitda), src("EBITDA")],
        ["EBITDA margin", "EBITDA ÷ Revenue", "LTM", "%", p(ebitda / rev if rev and ebitda is not None else None), "Calculated"],
        ["Net debt", "Gross debt − cash and equivalents", "Period-end", "USD", usd(nd), src("Net_Debt")],
        ["Net leverage", "Net debt ÷ EBITDA", "Period-end debt over LTM EBITDA", "x", x(lev),
         f"Calculated; reported {x(rep_lev)} by {G['Leverage']['source']}" if G.get("Leverage") else "Calculated"],
        ["Facility utilisation", "Outstanding principal ÷ Facility amount", "Point-in-time", "%", p(util), "Calculated"],
        ["Undrawn commitment", "Facility amount − Outstanding principal", "Point-in-time", "USD", usd(fac - outp if fac is not None and outp is not None else None), "Calculated"],
        ["Leverage covenant headroom", "(Covenant − Net leverage) ÷ Covenant", "At last test date", "%", p(head), f"Covenant {x(cov)}" if cov else "—"],
        ["Loan-to-value (LTV)", "Outstanding principal ÷ Collateral value", "Latest valuation", "%", p(ltv), src("Collateral_Value")],
        ["All-in interest rate", "Benchmark rate + margin", "Current interest period", "%", "—" if rate is None else f"{rate * 100:.2f}%", src("Interest_Rate")],
        ["Margin", "Contractual spread over benchmark", "Current", "bps", "—" if mar is None else f"{round(mar * 10000)} bps", src("Margin")],
        ["Annual interest cost (est.)", "Outstanding principal × all-in rate", "Annualised", "USD", usd(outp * rate if outp is not None and rate is not None else None), "Calculated"],
        ["Current ratio", "Current assets ÷ Current liabilities", "Period-end", "x", x(cr), src("Current_Ratio")],
    ]
    gap = abs(rep_lev - lev) if rep_lev is not None and lev is not None else 0
    if "Metrics" in selected:
        out["Metrics"] = {"n": len(M), "head": ["Metric", "Definition", "Basis", "Unit", "Value", "Inputs"], "rows": M,
                          "text": f"{len(M)} metrics defined; {sum(1 for m in M if m[4] != '—')} calculated from the golden record."
                                  + (f" Reported leverage differs from the calculated value by {gap:.2f}x." if gap > 0.05 else "")}

    if "KPIs" in selected:
        conf = assess_result["overall"]["score"] if assess_result else None
        comp = assess_result["dims"]["Completeness"]["score"] if assess_result else None
        esc_n = len(clean_result["escalations"]) if clean_result else None
        chg = len(clean_result["log"]) if clean_result else None
        crit = clean_result["summary"].get("Validate critical information") if clean_result else None
        stale = sum(1 for r in ds.live() if ds.is_stale(r)) / len(ds.live()) if ds.live() else None
        K = [
            ["Data confidence", "Average of the Assess criteria", "≥ 85 green · 60–84 amber · < 60 red", "Data Governance Office", "Each run", "—" if conf is None else f"{conf}/100", rag(conf, 85, 60)],
            ["Completeness rate", "Assess completeness score", "≥ 85 green · 60–84 amber", "Credit analyst", "Each run", "—" if comp is None else f"{comp}/100", rag(comp, 85, 60)],
            ["Leverage covenant headroom", "From Metrics", "≥ 25% green · 10–25% amber · < 10% red", "Relationship manager", "Quarterly", p(head), rag(None if head is None else head * 100, 25, 10)],
            ["Facility utilisation", "From Metrics", "≤ 80% green · 80–95% amber · > 95% red", "Relationship manager", "Monthly", p(util), rag(None if util is None else util * 100, 80, 95, False)],
            ["Loan-to-value", "From Metrics", "≤ 60% green · 60–75% amber · > 75% red", "Credit Risk Management", "On valuation", p(ltv), rag(None if ltv is None else ltv * 100, 60, 75, False)],
            ["Critical fields validated", "Clean: critical fields matching the golden record", "All green · 2 short amber", "Credit analyst", "Each run",
             f"{crit['n']} of {len(crit['rows'])}" if crit else "Clean not run", rag(crit["n"], len(crit["rows"]), len(crit["rows"]) - 2) if crit else "na"],
            ["Open escalations", "Unresolved Clean items", "0 green · 1–5 amber · > 5 red", "Data Governance Office", "Daily",
             "Clean not run" if esc_n is None else str(esc_n), "na" if esc_n is None else rag(esc_n, 0, 5, False)],
            ["Auto-resolution rate", "Changes ÷ (changes + escalations)", "≥ 80% green · 60–79% amber", "Data Governance Office", "Each run",
             p(chg / (chg + esc_n)) if clean_result and (chg + esc_n) else "Clean not run", rag(chg / (chg + esc_n) * 100, 80, 60) if clean_result and (chg + esc_n) else "na"],
            ["Stale record share", f"Records older than {ds.stale_days} days", "< 5% green · 5–15% amber · > 15% red", "Data owners", "Weekly", p(stale), rag(None if stale is None else stale * 100, 5, 15, False)],
        ]
        out["KPIs"] = {"n": len(K), "head": ["KPI", "Definition", "RAG bands", "Owner", "Frequency", "Current", "Status"], "rows": K,
                       "text": f"{len(K)} KPIs: {sum(1 for k in K if k[6] == 'g')} green, {sum(1 for k in K if k[6] == 'a')} amber, {sum(1 for k in K if k[6] == 'r')} red."}

    names = sorted({v for r in ds.live() for k, v in r.fields.items() if k == "Borrower_Name" and not is_blank(v)}
                   | {e.value for e in ds.live_elements() if e.canonical == "Borrower_Name" and not is_blank(e.value)} | set(ds.aliases) | {ds.borrower})
    regs = sorted({r.fields["Registration_Number"] for r in ds.live() if not is_blank(r.fields.get("Registration_Number"))}
                  | {e.value for e in ds.live_elements() if e.canonical == "Registration_Number" and not is_blank(e.value)})
    facs = sorted(set(ds.facility_ids) | {e.value for e in ds.live_elements() if e.element.lower() == "facility id" and not is_blank(e.value)})
    gv = lambda f: G[f]["display"] if G.get(f) else "—"
    ctry = G["Country"]["value"] if G.get("Country") else None
    rating = G["External_Rating"]["display"] if G.get("External_Rating") else None
    if "Master data" in selected:
        MD = [
            ["Legal name", gv("Borrower_Name") if G.get("Borrower_Name") else ds.borrower, G["Borrower_Name"]["source"] if G.get("Borrower_Name") else "—"],
            ["Name variants linked", "; ".join(names), f"{len(names)} variants"],
            ["Registration number", gv("Registration_Number"), G["Registration_Number"]["source"] if G.get("Registration_Number") else "—"],
            ["Other identifiers linked", "; ".join(r for r in regs if not G.get("Registration_Number") or r != G["Registration_Number"]["value"]) or "None", f"{len(regs)} identifiers"],
            ["LEI", "Not held", "Request from GLEIF"],
            ["Country of incorporation", f"{ctry} ({norm_country(ctry) or '?'})" if ctry else "—", "ISO 3166-1"],
            ["Industry", gv("Industry"), G["Industry"]["source"] if G.get("Industry") else "—"],
            ["External rating", f"{rating} → internal grade {INTERNAL_GRADE.get(rating, '?')}" if rating else "—", G["External_Rating"]["source"] if rating else "—"],
            ["Beneficial owner", gv("Beneficial_Owner"), G["Beneficial_Owner"]["source"] if G.get("Beneficial_Owner") else "—"],
            ["Facility IDs linked", "; ".join(facs) or "None", f"{len(facs)} facilities"],
        ]
        out["Master data"] = {"n": 1 + len(facs), "head": ["Attribute", "Master value", "Source / rule"], "rows": MD,
                              "text": f"1 obligor record linking {len(names)} name variants, {len(regs)} identifiers and {len(facs)} facilities."}

    if "Reporting dimensions" in selected:
        asof = sorted(str(r.as_of) for r in ds.live() if r.as_of)
        ccys = sorted({r.fields["Currency"] for r in ds.live() if not is_blank(r.fields.get("Currency"))})
        D = [
            ["Time", f"Reference date {ds.ref_date.isoformat()} · data as of {asof[0] if asof else '—'} to {asof[-1] if asof else '—'}", "ISO 8601"],
            ["Geography", f"Incorporation {norm_country(ctry) or ctry or '—'}", "ISO 3166-1 alpha-2"],
            ["Product and facility", f"{len(facs)} facilities", "Bank facility-type list"],
            ["Sector", gv("Industry"), "Internal sector list"],
            ["Rating", f"External {rating or '—'} · internal {INTERNAL_GRADE.get(rating, '—') if rating else '—'}", "Internal master scale"],
            ["Currency", f"Reporting USD · source {', '.join(ccys) or 'USD'}", "ISO 4217"],
            ["Data provenance", f"{len(ds.sources())} sources · {len(ds.live())} records · {len(ds.live_elements())} internal elements", "Source, record ID, as-of date"],
        ]
        out["Reporting dimensions"] = {"n": len(D), "head": ["Dimension", "Members", "Standard"], "rows": D,
                                       "text": f"{len(D)} conformed dimensions for {ds.borrower}."}

    if "Semantic layer" in selected:
        T = [[v[0], v[3], k, ", ".join(v[4][:5]), (GOLD_PRIORITY.get(k) or ["—"])[0]] for k, v in FIELDS.items()
             if k in G or k in ("Borrower_Name",)]
        out["Semantic layer"] = {"n": len(T) + len(M), "head": ["Business term", "Section", "Field", "Also known as", "Golden source"], "rows": T,
                                 "text": f"{len(T)} business terms mapped to fields with synonyms; {len(M)} metric definitions in the glossary."}

    return {"selected": selected, "out": out, "version": ds.version,
            "values": {"leverage": lev, "utilisation": util, "headroom": head, "ltv": ltv}}
