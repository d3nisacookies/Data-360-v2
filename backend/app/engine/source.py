"""Step 1 · Source: the Collector (what is held, and does it cover the credit memo?) and
the Seeker (find each identity attribute everywhere, and do the sources agree?).

Both run on everything uploaded for the borrower. The Collector's choice of sources then
scopes Assess, Clean and Normalise; its outputs and the Seeker's findings feed Assess.
"""
from collections import defaultdict

from rapidfuzz import fuzz

from .core import Dataset
from .reference import FIELDS, LABEL, norm_text
from .values import is_blank, norm_country, typed

# Credit-memo outputs -> evidence: [source, category, optional sub-categories] and record fields
OUTPUTS: dict[str, dict] = {
    "Borrower profile": {"desc": "Legal entity, segment, coverage and rating",
                         "ev": [["CRM tools", "Client master data"], ["Loan systems", "Borrower and obligor", ["Legal entity"]], ["Risk platforms", "Credit risk"]],
                         "fields": ["Borrower_Name", "Country", "Industry", "External_Rating"]},
    "Group structure": {"desc": "Parent, sponsor, guarantors and SPVs",
                        "ev": [["Loan systems", "Borrower and obligor", ["Group structure", "Sponsor", "Guarantors", "SPVs"]], ["Legal systems", "Entity management"], ["CRM tools", "Client master data"]],
                        "fields": ["Beneficial_Owner"]},
    "Ownership information": {"desc": "Beneficial owners and share ownership",
                              "ev": [["CRM tools", "Onboarding and KYC"], ["Physical / hard-copy records", "Security originals"], ["Legal systems", "Entity management"]],
                              "fields": ["Beneficial_Owner", "Registration_Number", "Registry_Status"]},
    "Relationship history": {"desc": "Meetings, pipeline, wallet and correspondence",
                             "ev": [["CRM tools", "Interactions"], ["CRM tools", "Pipeline"], ["CRM tools", "Wallet and profitability"], ["Email archives", "Deal correspondence"]],
                             "fields": []},
    "Facility summary": {"desc": "Facilities, tranches, commitments and maturity",
                         "ev": [["Loan systems", "Facility data"], ["Document repositories", "Deal documents"]],
                         "fields": ["Facility_Amount", "Outstanding_Principal", "Maturity_Date", "Interest_Rate", "Margin"]},
    "Financial performance": {"desc": "Revenue, EBITDA, leverage and liquidity",
                              "ev": [["Document repositories", "Borrower deliverables"], ["Credit agencies", "Research"]],
                              "fields": ["Revenue", "EBITDA", "Net_Debt", "Leverage", "Current_Ratio"]},
    "Collateral and security": {"desc": "Security package, valuations and title documents",
                                "ev": [["Loan systems", "Collateral and security"], ["Physical / hard-copy records", "Collateral title documents"], ["Physical / hard-copy records", "Custody records"]],
                                "fields": ["Collateral_Value"]},
    "Covenant compliance": {"desc": "Tests, certificates and waivers",
                            "ev": [["Loan systems", "Covenants"], ["Document repositories", "Borrower deliverables"]],
                            "fields": ["Leverage_Covenant"]},
    "Risk ratings and provisioning": {"desc": "Ratings, PD/LGD, watchlist and ECL",
                                      "ev": [["Risk platforms", "Credit risk"], ["Risk platforms", "Early warning"], ["Risk platforms", "Provisioning"]],
                                      "fields": ["External_Rating", "Default_Flag"]},
    "Hedging and treasury": {"desc": "Hedges, settlement and funding",
                             "ev": [["Treasury systems", "Hedging"], ["Treasury systems", "Payments and settlement"], ["Treasury systems", "Funding"]], "fields": []},
    "Legal and disputes": {"desc": "Contracts, matters and enforcement",
                           "ev": [["Legal systems", "Contracts"], ["Legal systems", "Matter management"], ["Legal systems", "Disputes and enforcement"]], "fields": []},
    "KYC and sanctions": {"desc": "KYC status, screening and compliance",
                          "ev": [["CRM tools", "Onboarding and KYC"], ["Legal systems", "Regulatory and compliance"]],
                          "fields": ["Sanctions_Screening", "Registry_Status"]},
    "ESG and country risk": {"desc": "ESG scores, climate and country risk",
                             "ev": [["Risk platforms", "ESG and climate risk"], ["Credit agencies", "ESG ratings"]],
                             "fields": ["ESG_Score", "Country_Risk_Score"]},
}
STANDARD_OUTPUTS = ["Borrower profile", "Group structure", "Ownership information", "Relationship history"]

# int: data-element names in internal systems · ext: record fields · extSrc: only these feeds
# indirect: a hint, not the attribute itself · multi: several values are expected
ATTRS: dict[str, dict] = {
    "Borrower Name": {"pot": "Loan origination, Loan IQ, credit risk, treasury, trade finance, regulatory reporting, ERP, document management, SWIFT, sanctions screening",
                      "int": ["Legal name", "Client legal name", "Organisation", "Rated entity", "Reference entity", "Target client", "Entity", "Counterparty", "Maker", "Addressee", "Beneficiary name", "Chargor"],
                      "ext": ["Borrower_Name"]},
    "Legal Entity Name": {"pot": "Corporate registry feeds, Bureau van Dijk (Orbis), D&B, Bloomberg, Capital IQ, legal document repositories",
                          "int": ["Legal name", "Client legal name", "Rated entity", "Chargor", "Entity name"], "ext": ["Borrower_Name"],
                          "extSrc": ["Corporate Registry", "Bureau van Dijk", "D&B", "Bloomberg", "Capital IQ"]},
    "Registration Number": {"pot": "Corporate registry interfaces, AML platforms, customer due diligence systems, legal repositories, external data providers",
                            "int": ["Company registration number (UEN)", "Company registration number"], "ext": ["Registration_Number"]},
    "Tax ID": {"pot": "ERP, finance platforms, treasury, tax compliance, regulatory reporting, master data management", "int": ["Tax ID", "TIN"], "ext": []},
    "LEI (Legal Entity Identifier)": {"pot": "Treasury, trading platforms, market risk, regulatory reporting, Bloomberg, Refinitiv, GLEIF", "int": ["LEI"], "ext": []},
    "Country of Incorporation": {"pot": "Corporate registry feeds, AML systems, country risk systems, external due diligence databases",
                                 "int": ["Country of incorporation", "Client country"], "ext": ["Country"]},
    "Operating Countries": {"pot": "Trade finance, supply chain, ESG platforms, country risk databases, transaction banking",
                            "int": ["Geography", "Country", "Country exposure"], "ext": [], "multi": True,
                            "note": "Several values are expected: a company can operate in more than one country."},
    "Industry Sector": {"pot": "Credit risk platforms, internal rating systems, Bloomberg, Moody's, Capital IQ, D&B, ESG databases",
                        "int": ["Industry code", "Sector tag", "Coverage team"], "ext": ["Industry"]},
    "SIC / NAICS Code": {"pot": "Corporate registry feeds, D&B, Bureau van Dijk, Bloomberg, internal risk systems",
                         "int": ["Industry code"], "ext": [], "indirect": True,
                         "note": "Only internal industry codes are held, not SIC or NAICS. They can be mapped in Normalise."},
    "Date Established": {"pot": "Corporate registry feeds, company secretarial systems, D&B, Bureau van Dijk", "int": ["Date of incorporation", "Incorporation date"], "ext": []},
    "Website": {"pot": "D&B, Bloomberg, customer portals, vendor databases", "int": ["Counterparty domain", "Email address"], "ext": [], "indirect": True,
                "note": "No website field held. Email domains point to the likely website."},
    "Organisation Type": {"pot": "Legal systems, corporate registry feeds, credit risk systems, entity master repositories", "int": ["Client segment"], "ext": []},
    "Listed / Private Status": {"pot": "Exchange filings, Bloomberg, Capital IQ, entity master repositories", "int": ["Listing status"], "ext": []},
    "Beneficial Owner": {"pot": "KYC platforms, corporate registry feeds, Bureau van Dijk (Orbis), D&B, client onboarding", "int": ["UBO name"], "ext": ["Beneficial_Owner"]},
    "Ultimate Parent": {"pot": "Loan systems, credit risk systems, Bureau van Dijk (Orbis), Capital IQ", "int": ["Ultimate parent", "Counterparty group"], "ext": []},
    "Registry Status": {"pot": "Corporate registry feeds, D&B, Bureau van Dijk, KYC platforms", "int": [], "ext": ["Registry_Status"]},
    "External Rating": {"pot": "Moody's, S&P, Fitch, rating agency feeds, Capital IQ, D&B", "int": ["Issuer rating"], "ext": ["External_Rating"]},
    "Sanctions Screening": {"pot": "Sanctions screening systems, AML and KYC platforms, regulatory / sanctions feeds", "int": ["Screening result"], "ext": ["Sanctions_Screening"]},
    "Revenue": {"pot": "Financial statements, document repositories, Bureau van Dijk, Capital IQ, D&B", "int": ["Revenue"], "ext": ["Revenue"]},
    "EBITDA": {"pot": "Financial statements, document repositories, Bureau van Dijk, Capital IQ", "int": ["EBITDA"], "ext": ["EBITDA"]},
    "Facility Amount": {"pot": "Loan systems, Loan IQ, facility documentation, Capital IQ, Bloomberg", "int": ["Total commitment"], "ext": ["Facility_Amount"]},
    "Outstanding Principal": {"pot": "Loan systems, Loan IQ, agent statements, Capital IQ, Bloomberg", "int": ["Drawn amount"], "ext": ["Outstanding_Principal"]},
    "Maturity Date": {"pot": "Loan systems, facility documentation, Capital IQ, Bloomberg", "int": ["Final maturity date"], "ext": ["Maturity_Date"]},
}
STANDARD_ATTRS = ["Borrower Name", "Legal Entity Name", "Registration Number", "Tax ID", "LEI (Legal Entity Identifier)", "Country of Incorporation",
                  "Operating Countries", "Industry Sector", "SIC / NAICS Code", "Date Established", "Website", "Organisation Type", "Listed / Private Status"]
# attribute -> canonical field, for linking Seeker conflicts to the golden record
ATTR_FIELD = {"Borrower Name": "Borrower_Name", "Legal Entity Name": "Borrower_Name", "Registration Number": "Registration_Number",
              "Country of Incorporation": "Country", "Industry Sector": "Industry", "Beneficial Owner": "Beneficial_Owner",
              "Registry Status": "Registry_Status", "External Rating": "External_Rating", "Sanctions Screening": "Sanctions_Screening",
              "Revenue": "Revenue", "EBITDA": "EBITDA", "Facility Amount": "Facility_Amount", "Outstanding Principal": "Outstanding_Principal",
              "Maturity Date": "Maturity_Date"}

# Sources that are not uploaded but could be requested, by category, with the attributes they supply
PICK_CATS = [
    {"cat": "Official registries and identifiers", "use": "Legal name, registration number, incorporation date, status, LEI",
     "src": ["GLEIF (LEI)", "ACRA BizFile+ (Singapore)", "Hong Kong Companies Registry", "Japan NTA Corporate Number site", "Companies House (UK)", "SEC EDGAR", "OpenCorporates"],
     "attrs": ["Legal Entity Name", "Registration Number", "Date Established", "LEI (Legal Entity Identifier)", "Organisation Type", "Country of Incorporation", "Listed / Private Status", "Registry Status"]},
    {"cat": "Commercial credit bureaus", "use": "Payment behaviour, scores, defaults, public records",
     "src": ["Experian", "Equifax", "Creditsafe", "CRIF", "TransUnion (incl. CIBIL)", "Tokyo Shoko Research", "Teikoku Databank", "CTOS"], "attrs": ["SIC / NAICS Code", "Date Established"]},
    {"cat": "Ratings and credit analytics", "use": "External ratings, default probability",
     "src": ["S&P Global Ratings", "Fitch", "JCR", "R&I", "CRISIL / ICRA", "Moody's Analytics (CreditEdge, RiskCalc)", "Bloomberg DRSK"], "attrs": ["Industry Sector", "External Rating"]},
    {"cat": "Sanctions, PEP and adverse media", "use": "Screening evidence, reputational risk",
     "src": ["LSEG World-Check", "Dow Jones Risk & Compliance", "LexisNexis Risk Solutions", "ComplyAdvantage", "Factiva", "RepRisk", "Official lists (OFAC, UN, EU, UK OFSI, MAS)"],
     "attrs": ["Sanctions Screening"]},
    {"cat": "Ownership and group structure", "use": "Beneficial owners, ultimate parent",
     "src": ["Sayari", "Kyckr", "Local beneficial-owner registers"], "attrs": ["Organisation Type", "Beneficial Owner", "Ultimate Parent"]},
    {"cat": "Fundamentals and filings", "use": "Financial statements, listing status",
     "src": ["FactSet", "LSEG Workspace", "SGXNet", "HKEXnews", "EDINET / TDnet (Japan)"],
     "attrs": ["Listed / Private Status", "Website", "Operating Countries", "Industry Sector", "Revenue", "EBITDA"]},
    {"cat": "Private markets and funds", "use": "Fund size, strategy, investors (for asset-manager borrowers)",
     "src": ["PitchBook", "Preqin", "MSCI Private Capital (Burgiss)", "Morningstar", "SEC Form ADV"],
     "attrs": ["Organisation Type", "Website", "Date Established", "Operating Countries", "Listed / Private Status"]},
    {"cat": "Country and macro risk", "use": "Country limits, macro outlook",
     "src": ["Fitch Solutions (BMI)", "EIU", "Oxford Economics", "Coface", "Allianz Trade", "IMF / World Bank / ADB data"], "attrs": ["Operating Countries"]},
    {"cat": "Sector intelligence", "use": "Industry outlook, sector benchmarks",
     "src": ["IBISWorld", "S&P Global Commodity Insights", "Wood Mackenzie", "IJGlobal / Inframation"], "attrs": ["Industry Sector", "SIC / NAICS Code"]},
    {"cat": "Tax verification", "use": "Tax ID and FATCA / CRS status", "src": ["IRS FATCA FFI list", "National tax-ID verification portals"], "attrs": ["Tax ID"]},
]


def suppliers(attr: str) -> list[str]:
    return [s for c in PICK_CATS if attr in c["attrs"] for s in c["src"]]


def _sub(label: str) -> str:
    return label.split(" / ", 1)[1] if " / " in label else ""


# ---------------- Collector ----------------
def collect(ds: Dataset, sources: list[str] | None, outputs: list[str] | None) -> dict:
    available = ds.sources()
    scope = [s for s in (sources or available) if s in available] or available
    outputs = [o for o in (outputs or STANDARD_OUTPUTS) if o in OUTPUTS] or STANDARD_OUTPUTS
    els = [e for e in ds.elements if e.source in scope]
    recs = [r for r in ds.records if r.source in scope]
    all_els = ds.elements
    cov = []
    for o in outputs:
        d = OUTPUTS[o]
        groups = []
        for g in d["ev"]:
            src, cat = g[0], g[1]
            subs = g[2] if len(g) > 2 else None
            match = lambda e: e.source == src and e.category == cat and (not subs or _sub(e.label) in subs) and not is_blank(e.value)
            n = sum(1 for e in els if match(e))
            held = sum(1 for e in all_els if match(e))
            groups.append({"label": f"{cat} ({src})", "source": src, "n": n, "in_scope": src in scope, "uploaded": src in available, "held_elsewhere": held if src not in scope else 0})
        for f in d["fields"]:
            srcs = sorted({r.source for r in recs if not is_blank(r.fields.get(f))})
            out_srcs = sorted({r.source for r in ds.records if r.source not in scope and not is_blank(r.fields.get(f))})
            groups.append({"label": LABEL[f], "source": ", ".join(srcs) or "record feeds", "n": sum(1 for r in recs if not is_blank(r.fields.get(f))),
                           "in_scope": bool(srcs) or not out_srcs, "uploaded": bool(srcs or out_srcs), "held_elsewhere": len(out_srcs), "field": f,
                           "addable": out_srcs})
        hit = [g for g in groups if g["n"]]
        status = "ok" if len(hit) == len(groups) else "part" if hit else "none"
        addable = sorted({g["source"] for g in groups if not g["n"] and g["uploaded"] and not g["in_scope"] and "field" not in g}
                         | {s for g in groups if not g["n"] for s in g.get("addable", [])})
        cov.append({"output": o, "desc": d["desc"], "status": status, "groups": groups, "hit": len(hit), "total": len(groups),
                    "addable": addable, "missing": [g["label"] for g in groups if not g["n"] and not g["held_elsewhere"]]})
    locs = []
    for s in available:
        se = [e for e in ds.elements if e.source == s]
        sr = [r for r in ds.records if r.source == s]
        cats = defaultdict(int)
        for e in se:
            cats[e.category or "Uncategorised"] += 1
        locs.append({"source": s, "in_scope": s in scope, "zone": sr[0].zone if sr else "Internal", "records": len(sr), "elements": len(se),
                     "categories": sorted(cats.items(), key=lambda x: -x[1]),
                     "restricted": sum(1 for e in se if e.sensitivity.lower().startswith("restricted")),
                     "newest": max((r.as_of.isoformat() for r in sr if r.as_of), default=None)})
    return {"sources": scope, "outputs": outputs, "available": available, "coverage": cov, "locations": locs,
            "counts": {"locations": len(scope), "records": len(recs), "elements": len(els),
                       "restricted": sum(1 for e in els if e.sensitivity.lower().startswith("restricted")),
                       "full": sum(1 for c in cov if c["status"] == "ok")}}


# ---------------- Seeker ----------------
def _key(field: str | None, v) -> str:
    if field:
        t = typed(field, v)
        if t is not None:
            return str(round(t, 2) if isinstance(t, float) else t)
    c = norm_country(v)
    return c or norm_text(v)


def search(ds: Dataset, name: str, requested: list[str]) -> dict:
    a = ATTRS.get(name)
    field = ATTR_FIELD.get(name)
    hits = []
    if a:
        want = {x.lower() for x in a["int"]}
        el_match = lambda e: e.element.strip().lower() in want
        ext_fields, ext_src = a["ext"], a.get("extSrc")
    else:  # an attribute the user typed: match element names and record fields by similarity
        el_match = lambda e: fuzz.token_sort_ratio(norm_text(name), norm_text(e.element)) >= 86
        ext_fields = [k for k, v in FIELDS.items() if max(fuzz.token_sort_ratio(norm_text(name), norm_text(s)) for s in [v[0], *v[4]]) >= 86]
        ext_src = None
        field = field or (ext_fields[0] if ext_fields else None)
    for e in ds.elements:
        if el_match(e) and not is_blank(e.value):
            hits.append({"location": e.source, "zone": "Internal", "field": e.element, "value": e.value, "record": e.key.split(":")[1], "as_of": None, "flag": ""})
    for r in ds.records:
        if ext_src and r.source not in ext_src:
            continue
        for f in ext_fields:
            v = r.fields.get(f)
            if not is_blank(v):
                hits.append({"location": r.source, "zone": r.zone, "field": LABEL.get(f, f), "value": v, "record": r.rid,
                             "as_of": r.as_of.isoformat() if r.as_of else None, "flag": r.flag})
    groups: dict[str, dict] = {}
    for h in hits:
        k = _key(field, h["value"])
        g = groups.setdefault(k, {"value": h["value"], "count": 0, "locations": set()})
        g["count"] += 1
        g["locations"].add(h["location"])
    vals = sorted(({"value": g["value"], "count": g["count"], "locations": sorted(g["locations"])} for g in groups.values()), key=lambda x: -x["count"])
    from_ = [s for s in requested if s in suppliers(name)]
    if not hits:
        status = "pending" if from_ else "miss"
    elif a and a.get("indirect"):
        status = "indirect"
    elif len(vals) == 1:
        status = "ok"
    else:
        status = "multi" if a and a.get("multi") else "conf"
    return {"attribute": name, "status": status, "hits": hits, "values": vals, "locations": sorted({h["location"] for h in hits}),
            "requested_from": from_, "field": field, "note": (a or {}).get("note", "" if a else "Custom attribute: matched by name similarity."),
            "potential": (a or {}).get("pot", ""), "suppliers": suppliers(name)[:6]}


def seek(ds: Dataset, attrs: list[str] | None, requested: list[str] | None) -> dict:
    attrs = [x.strip() for x in (attrs or STANDARD_ATTRS) if x and x.strip()] or STANDARD_ATTRS
    requested = requested or []
    res = [search(ds, a, requested) for a in dict.fromkeys(attrs)]
    count = lambda *s: sum(1 for r in res if r["status"] in s)
    return {"attributes": [r["attribute"] for r in res], "requested": requested, "results": res,
            "counts": {"total": len(res), "found": count("ok", "multi"), "conflict": count("conf"), "gap": count("miss", "indirect"), "pending": count("pending")},
            "locations": len(ds.sources())}
