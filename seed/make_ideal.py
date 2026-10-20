"""Build the "ideal" test data set: the same seven hypothetical borrowers, sources and file layouts
as seed/sample-files, but with every value correct, complete, current and consistent.

Upload seed/ideal-files instead of (or next to a reset of) seed/sample-files to see what Data360
reports when nothing is wrong with the data. Run from the repo root:

    python3 seed/make_ideal.py

What changes against the fragmented set
  External files   one current record per source (no history rows, no duplicates), every field the
                   source supplies filled from the reference values, no provider defect flags,
                   empty "Data Quality Defects" sheet, all as-of dates inside the 90-day window.
  Internal files   same rows and elements; option lists and placeholders replaced with one real
                   value; identity and credit-memo elements hold the same value as the external
                   sources; KYC and screening elements current; client identity attributes
                   (LEI, Tax ID, incorporation date, listing status...) added for every borrower.
  Vendor CSV       the Refinitiv export in its own layout, with the same values as everything else.

Credit facts are not changed into good news: a borrower rated BB+ stays BB+, and covenant or watchlist
results stay what the source says. "Ideal" is about the data, not the credit.
All values are hypothetical.
"""
from __future__ import annotations

import copy
import csv
import datetime as dt
import re
import shutil
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "sample-files"
OUT = ROOT / "ideal-files"
AS_OF = dt.date(2026, 10, 8)          # newest extract; the sample reference date is 2026-10-09

# ---------------- reference truth (same values the fragmented set was built around) ----------------
REF = {
    "SMBC-ASI-001": dict(name="Orion Infrastructure Holdings Pte. Ltd.", reg="SG-REG-201912345K", bo="Orion Capital Partners", rating="BBB+",
                         rev=1850e6, ebitda=410e6, nd=368.5e6, fac=420e6, out=368.5e6, rate=.0325, margin=.0175, mat="2029-06-30",
                         coll=560e6, cov=4.25, cr=1.35, esg=72, crs=2, country="Singapore", industry="Infrastructure",
                         lei="5493001KJTIIGC8Y1R12", tax="201912345K", inc="2019-04-12", seg="Corporate", listing="Private",
                         dom="orioninfra.com.sg", geo="Singapore"),
    "SMBC-ASI-002": dict(name="Meridian Renewables Limited", reg="HK-REG-2847165", bo="Meridian Energy Group", rating="BBB-",
                         rev=1120e6, ebitda=265e6, nd=284.2e6, fac=310e6, out=284.2e6, rate=.0325, margin=.0175, mat="2030-03-31",
                         coll=410e6, cov=4.25, cr=1.35, esg=81, crs=3, country="Hong Kong", industry="Renewable Energy",
                         lei="2549008MRDN7QK4XHE31", tax="62847165", inc="2017-08-22", seg="Corporate", listing="Private",
                         dom="meridianrenewables.com", geo="Hong Kong"),
    "SMBC-ASI-003": dict(name="Pacific Components Manufacturing Sdn. Bhd.", reg="MY-REG-201802945678", bo="Pacific Industrial Holdings", rating="BBB",
                         rev=890e6, ebitda=118e6, nd=121.7e6, fac=180e6, out=121.7e6, rate=.0325, margin=.0175, mat="2028-12-15",
                         coll=215e6, cov=4.25, cr=1.35, esg=64, crs=3, country="Malaysia", industry="Manufacturing",
                         lei="9845003PCMSB2018X771", tax="C2094567801", inc="2018-01-30", seg="Corporate", listing="Private",
                         dom="pacificcomponents.com.my", geo="Malaysia"),
    "SMBC-ASI-004": dict(name="Aster Logistics & Warehousing Co., Ltd.", reg="TH-REG-0105564123987", bo="Aster Logistics Group", rating="BBB-",
                         rev=760e6, ebitda=126e6, nd=226.9e6, fac=250e6, out=226.9e6, rate=.0325, margin=.0175, mat="2028-09-30",
                         coll=315e6, cov=4.25, cr=1.35, esg=58, crs=4, country="Thailand", industry="Logistics",
                         lei="6567004ASTRLW0105564", tax="0105564123987", inc="2021-03-09", seg="Corporate", listing="Private",
                         dom="asterlogistics.co.th", geo="Thailand"),
    "SMBC-ASI-005": dict(name="Nexus Digital Services Pte. Ltd.", reg="SG-REG-202045678M", bo="Nexus Holdings", rating="A-",
                         rev=540e6, ebitda=142e6, nd=138.6e6, fac=150e6, out=138.6e6, rate=.0325, margin=.0175, mat="2027-11-30",
                         coll=185e6, cov=4.25, cr=1.35, esg=76, crs=2, country="Singapore", industry="Digital Services",
                         lei="5493005NXDS2020Q6M44", tax="202045678M", inc="2020-11-02", seg="Corporate", listing="Private",
                         dom="nexusdigital.sg", geo="Singapore"),
    "SMBC-ASI-006": dict(name="Haneda Consumer Products KK", reg="JP-REG-0104-01-123456", bo="Haneda Holdings Inc.", rating="BB+",
                         rev=410e6, ebitda=76e6, nd=79.8e6, fac=120e6, out=79.8e6, rate=.0325, margin=.0175, mat="2027-04-30",
                         coll=102e6, cov=4.25, cr=1.35, esg=69, crs=3, country="Japan", industry="Consumer Products",
                         lei="353800HANEDACP0X1234", tax="T0104011234560", inc="1998-06-15", seg="Corporate", listing="Private",
                         dom="haneda-cp.co.jp", geo="Japan"),
    "SMBC-ASI-007": dict(name="HarbourVest", reg="US-REG-DE-4821937", bo="HarbourVest Partners, LLC", rating="A-",
                         rev=1240e6, ebitda=486e6, nd=412.5e6, fac=500e6, out=412.5e6, rate=.0325, margin=.0150, mat="2029-12-31",
                         coll=1650e6, cov=4.25, cr=1.62, esg=74, crs=1, country="United States", industry="Asset management",
                         lei="549300HRBVST48219370", tax="EIN 04-3101234", inc="1982-02-01", seg="Financial sponsor", listing="Private",
                         dom="harbourvest.com", geo="United States"),
}
BY_NAME = {R["name"]: fid for fid, R in REF.items()}

# the fields each external source supplies (as in the fragmented set)
FIELDS = {
    "Corporate Registry": [],
    "D&B": ["External_Rating", "Revenue", "Default_Flag"],
    "Bureau van Dijk": ["Revenue", "EBITDA", "Net_Debt", "Leverage", "Collateral_Value", "Current_Ratio", "Default_Flag"],
    "Capital IQ": ["External_Rating", "Revenue", "EBITDA", "Net_Debt", "Leverage", "Facility_Amount", "Outstanding_Principal",
                   "Maturity_Date", "Collateral_Value", "Leverage_Covenant", "Current_Ratio", "Default_Flag"],
    "Bloomberg": ["Facility_Amount", "Outstanding_Principal", "Interest_Rate", "Margin", "Maturity_Date"],
    "Refinitiv": ["Interest_Rate", "Margin"],
    "Moody's": ["External_Rating", "Default_Flag"],
    "ESG Database": ["ESG_Score"],
    "Country Risk Database": ["Country_Risk_Score"],
    "Regulatory / Sanctions Feed": ["Sanctions_Screening"],
}


def field_value(R: dict, f: str):
    return {
        "External_Rating": R["rating"], "Revenue": R["rev"], "EBITDA": R["ebitda"], "Net_Debt": R["nd"],
        "Leverage": round(R["nd"] / R["ebitda"], 2), "Facility_Amount": R["fac"], "Outstanding_Principal": R["out"],
        "Interest_Rate": R["rate"], "Margin": R["margin"], "Maturity_Date": R["mat"], "Collateral_Value": R["coll"],
        "Leverage_Covenant": R["cov"], "Current_Ratio": R["cr"], "Default_Flag": "No", "Sanctions_Screening": "No Match",
        "ESG_Score": R["esg"], "Country_Risk_Score": R["crs"]}[f]


# ---------------- external files ----------------
def ideal_external(path: Path, dest: Path):
    wb = openpyxl.load_workbook(path)
    ws = wb["External Data"]
    H = [c.value for c in ws[1]]
    col = {h: i for i, h in enumerate(H)}
    old = [list(r) for r in ws.iter_rows(min_row=2, values_only=True) if r[0]]
    fid = old[0][col["Facility_ID"]]
    R = REF[fid]
    n = int(fid[-2:])
    template = {}                                   # first row per source keeps zone and diagram label
    for r in old:
        template.setdefault(r[col["External_Source"]], r)
    rows = []
    for i, (src, t) in enumerate(sorted(template.items(), key=lambda kv: list(FIELDS).index(kv[0]))):
        r = [None] * len(H)
        d = AS_OF - dt.timedelta(days=i % 3)   # inside every feed's refresh cycle
        r[col["Record_ID"]] = f"EXT-{n:02d}-{i + 1:02d}"
        r[col["Facility_ID"]] = fid
        r[col["Borrower_Name"]] = R["name"]
        r[col["Country"]] = R["country"]
        r[col["Industry"]] = R["industry"]
        r[col["External_Source"]] = src
        r[col["Source_Zone"]] = t[col["Source_Zone"]]
        r[col["Diagram_Source_Label"]] = t[col["Diagram_Source_Label"]]
        r[col["As_of_Date"]] = d.isoformat()
        r[col["Source_Reference"]] = f"{src.replace(' ', '_')}-{fid[-3:]}-{d:%Y%m}"
        r[col["Registration_Number"]] = R["reg"]
        r[col["Beneficial_Owner"]] = R["bo"]
        r[col["Registry_Status"]] = "Active"
        r[col["Currency"]] = "USD"
        for f in FIELDS[src]:
            r[col[f]] = field_value(R, f)
        r[col["Data_Quality_Status"]] = "VALIDATED"
        r[col["Data_Confidence"]] = "HIGH"
        rows.append(r)
    ws.delete_rows(2, ws.max_row)
    for r in rows:
        ws.append(r)

    dq = wb["Data Quality Defects"]
    dq.delete_rows(2, dq.max_row)

    snap = wb["Credit Memo Snapshot"]
    SH = [c.value for c in snap[1]]
    vals = {"Facility_ID": fid, "Borrower_Name": R["name"], "Commitment": R["fac"], "Outstanding": R["out"], "Currency": "USD",
            "External_Rating": R["rating"], "Revenue": R["rev"], "EBITDA": R["ebitda"], "Leverage": round(R["nd"] / R["ebitda"], 2),
            "Maturity": R["mat"], "Collateral": R["coll"], "Covenant": R["cov"], "Confidence": "HIGH",
            "Decision Note": "External data reconciled across all sources; fit for the credit memo"}
    snap.delete_rows(2, snap.max_row)
    snap.append([vals.get(h) for h in SH])

    rd = wb["README"]
    rd.append(["Ideal version", "Every value correct, complete, current and consistent across sources. Use it as the "
               "comparison baseline for the fragmented sample set. Still hypothetical."])
    wb.save(dest)


# ---------------- internal data dictionaries ----------------
def money(x: float) -> str:
    return f"USD {x:,.0f}"


# identity and credit-memo elements: the same value everywhere, matching the external sources
def canonical(R: dict, el: str, dtype: str | None = None):
    e = el.strip().lower()
    if (dtype or '') == 'Amount' and e in ('country exposure', 'utilisation'):
        return f"{money(R['out'])} ({R['country']})" if e == 'country exposure' else money(R['out'])
    names = {"legal name", "client legal name", "organisation", "rated entity", "reference entity", "target client", "entity",
             "counterparty", "maker", "addressee", "beneficiary name", "chargor", "entity name", "issuing company",
             "registered owner", "registered holder", "screened party", "borrower name", "obligor name"}
    if e in names:
        return R["name"]
    return {
        "company registration number (uen)": R["reg"], "company registration number": R["reg"],
        "country of incorporation": R["country"], "client country": R["country"],
        "geography": R["geo"], "country": R["geo"], "country exposure": R["geo"],
        "industry code": R["industry"], "sector tag": R["industry"], "coverage team": R["industry"],
        "issuer rating": R["rating"], "screening result": "No Match", "sanctions hit flag": "N", "pep flag": "N",
        "kyc status": "Approved", "next kyc review date": "2027-09-30",
        "obligor rating": GRADE[R["rating"]], "facility rating": GRADE[R["rating"]], "ecl stage": "Stage 1", "loan status": "Performing",
        "days past due": "0", "restructuring flag": "N", "watchlist status": "Not on watchlist", "decision": "Approved",
        "exposure % of tier 1 capital": "3.5%", "ltv covenant threshold": "80%", "ltv ratio": f"{R['out'] / R['coll'] * 100:.1f}%",
        "sentiment score": "0.35", "aml risk rating": "Low",
        "ubo name": R["bo"], "ultimate parent": R["bo"], "counterparty group": R["bo"],
        "revenue": money(R["rev"]), "ebitda": money(R["ebitda"]),
        "total commitment": money(R["fac"]), "limit amount": money(R["fac"]),
        "drawn amount": money(R["out"]), "undrawn / available amount": money(R["fac"] - R["out"]),
        "utilisation": f"{R['out'] / R['fac'] * 100:.1f}%",
        "final maturity date": R["mat"], "margin": f"{R['margin'] * 1e4:.0f} bps", "all-in rate": f"{(R['rate'] + R['margin']) * 100:.2f}%",
        "covenant threshold": f"{R['cov']:.2f}x", "esg score": str(R["esg"]),
        "lei": R["lei"], "tax id": R["tax"], "tin": R["tax"], "date of incorporation": R["inc"], "incorporation date": R["inc"],
        "client segment": R["seg"], "listing status": R["listing"], "counterparty domain": R["dom"],
        "email address": f"treasury@{R['dom']}", "facility currency": "USD", "funding currency": "USD",
    }.get(e)


# internal grade for each external rating (same scale as Data360)
GRADE = {"A+": "3", "A": "4+", "A-": "4", "BBB+": "4-", "BBB": "5+", "BBB-": "5", "BB+": "5-", "BB": "6+", "BB-": "6"}
# records of events that did not happen: the external sources show every borrower performing with no default,
# so legal proceedings, covenant-breach alerts, distress reports and restructuring plans are not held
NOT_HELD = {"proceeding type", "covenant breached", "breach magnitude", "distress indicator", "restructuring plan", "standstill period",
            "alert id", "allegation type"}


# one real value for a placeholder or option list, by element name and data type
NAMED = {
    "approver": "Head of Credit, Asia", "person wall-crossed": "Structured debt desk analyst", "sponsor name": "Founding partners (management-owned)",
    "valuer": "Knight Frank Valuation", "signatory": "Company secretary", "registration number": None, "deal name": None,
    "bond isin": "US41162X1019", "id document number": "Passport ending 4821 (masked)", "basis spread": "12 bps", "linked share charge": None, "title number": "LUR-2026-004812",
}


def fix_value(el: str, dtype: str, v, R: dict, code: str, fid: str):
    from_named = NAMED.get(el.strip().lower(), "missing")
    s = "" if v is None else str(v).strip()
    if from_named not in ("missing", None):
        return from_named
    if el.strip().lower() == "registration number":
        return f"REG-{fid}-2026-01"
    if el.strip().lower() == "linked share charge":
        return f"SEC-{fid}-SC-01"
    if el.strip().lower() == "deal name":
        return f"Project {code}"
    if el.strip().lower() == "hazard score":
        lvl = re.search(r"(High|Medium|Low)", s)
        return f"{ {'High': 4, 'Medium': 3, 'Low': 2}.get(lvl.group(1) if lvl else 'Low', 2)} ({s})" if s else "2"
    if s.lower() == "country":
        return R["country"]
    if s.lower().startswith("passport"):
        return "Passport ending 4821 (masked)"
    if " / " in s:
        return s.split(" / ")[0].strip()
    t = (dtype or "").strip()
    if t == "Percentage" and s and not re.search(r"%|bps", s):
        return s + " (bps)" if re.search(r"\d", s) else "10 bps"
    if t == "Text":
        return R["bo"] if el.strip().lower().endswith("name") else f"{R['name']}: {el.strip().lower()} on file"
    if t == "Identifier":
        return f"{fid}-{re.sub(r'[^A-Z]', '', el.upper())[:4]}-0001"
    if t == "Number":
        return "1"
    if t == "Amount":
        return money(R["fac"])
    if t == "Date":
        return AS_OF.isoformat()
    return s or "Not applicable"


def _blocks(rows, c):
    """Split dictionary rows into blocks: a "Record N" separator row and the element rows under it."""
    blocks, cur = [], None
    for r in rows:
        if not any(v is not None for v in r):
            continue
        if not r[c["ID"]]:
            cur = {"head": list(r), "rows": []}
            blocks.append(cur)
        elif cur is not None:
            cur["rows"].append(list(r))
    return blocks


def ideal_internal(path: Path, dest: Path, validate):
    wb = openpyxl.load_workbook(path)
    ws = wb["Data Dictionary"]
    H = [x.value for x in ws[1]]
    c = {h: i for i, h in enumerate(H)}
    rows = [list(r) for r in ws.iter_rows(min_row=2, values_only=True)]
    src_name = next(r[c["Data source"]] for r in rows if r[c["Data source"]])
    blocks = _blocks(rows, c)

    # every borrower gets every category this system holds: a missing category is copied from another
    # borrower's block and rewritten for this borrower
    subs = lambda b: frozenset(r[c["Sub-category"]] for r in b["rows"])
    have = {(b["head"][c["Borrower name"]], b["head"][c["Category"]], sc) for b in blocks for sc in subs(b)}
    cats = list(dict.fromkeys(b["head"][c["Category"]] for b in blocks))
    out = [copy.deepcopy(b) for b in blocks if b["head"][c["Borrower name"]] in BY_NAME]
    seen = set()
    for tmpl in blocks:
        cat, sc = tmpl["head"][c["Category"]], subs(tmpl)
        if (cat, sc) in seen or not sc:
            continue
        seen.add((cat, sc))
        for fid, R in REF.items():
            if all((R["name"], cat, x) in have for x in sc):
                continue
            nb = copy.deepcopy(tmpl)
            old = tmpl["head"][c["Borrower name"]]
            for r in [nb["head"], *nb["rows"]]:
                r[c["Borrower name"]] = R["name"]
                v = r[c["Example value"]]
                if isinstance(v, str) and old and old in v:
                    r[c["Example value"]] = v.replace(old, R["name"])
            out.append(nb)
            have.update((R["name"], cat, x) for x in sc)
    # keep each borrower's blocks together, in the original category order
    order = {R["name"]: i for i, R in enumerate(REF.values())}
    out.sort(key=lambda b: (order[b["head"][c["Borrower name"]]], cats.index(b["head"][c["Category"]])))

    first = {}                                     # (borrower, element) -> one value for every record
    for b in out:
        bname = b["head"][c["Borrower name"]]
        fid = BY_NAME[bname]
        R = REF[fid]
        code = "".join(w[0] for w in R["name"].split()[:2]).upper()
        b["rows"] = [r for r in b["rows"] if r[c["Data element"]].strip().lower() not in NOT_HELD]
        for r in b["rows"]:
            el, dtype = r[c["Data element"]], r[c["Data type"]]
            v = canonical(R, el, dtype)
            if v is None:
                v = r[c["Example value"]]
                if isinstance(v, str) and v.strip().lower() in ("none", "n/a", "na", "null", "-", "tbc", "tbd"):
                    v = "Not applicable (none agreed)" if (dtype or "Text") in ("Text", "Code") else None
                if validate(dtype, v):
                    v = fix_value(el, dtype, v, R, code, fid)
                key = (bname, el.strip().lower())
                if key in first and key[1] in MEMO:
                    v = first[key]
                first.setdefault(key, v)
            r[c["Example value"]] = v

    # client identity attributes the Seeker looks for, one block per borrower, in the CRM dictionary
    if src_name == "CRM tools":
        n = 0
        for fid, R in REF.items():
            head = [None] * len(H)
            head[c["Data source"]], head[c["Category"]], head[c["Sub-category"]], head[c["Borrower name"]] = \
                "CRM tools", "Client master data", "Client identity", R["name"]
            blk = {"head": head, "rows": []}
            for el, dtype, sens in IDENTITY_BLOCK:
                n += 1
                blk["rows"].append([f"DE-9{n:03d}", "CRM tools", "Client master data", "Client identity", el, dtype,
                                    canonical(R, el, dtype), "Structured", sens, R["name"]])
            i = max(i for i, b in enumerate(out) if b["head"][c["Borrower name"]] == R["name"])
            out.insert(i + 1, blk)

    ws.delete_rows(2, ws.max_row)
    for b in out:
        ws.append(b["head"])
        for r in b["rows"]:
            ws.append(r)
    last = ws.max_row
    sm = wb["Summary"]
    for row in sm.iter_rows(min_row=2):
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("=COUNTIFS"):
                cell.value = re.sub(r"\$(\w)\$2:\$\1\$\d+", lambda m: f"${m.group(1)}$2:${m.group(1)}${last}", cell.value)
        cat = row[1].value
        if cat and row[0].value == src_name:
            row[2].value = sum(1 for b in out if b["head"][c["Category"]] == cat)
    wb.save(dest)


IDENTITY_BLOCK = [
    ("Legal name", "Text", "Confidential – Client"), ("Company registration number (UEN)", "Identifier", "Confidential – Client"),
    ("Tax ID", "Identifier", "Restricted"), ("LEI", "Identifier", "Internal"), ("Country of incorporation", "Code", "Internal"),
    ("Geography", "Code", "Internal"), ("Industry code", "Code", "Internal"), ("Date of incorporation", "Date", "Internal"),
    ("Client segment", "Code", "Internal"), ("Listing status", "Code", "Internal"), ("UBO name", "Text", "Restricted"),
    ("Ultimate parent", "Text", "Confidential – Client"), ("Issuer rating", "Code", "Confidential – Client"),
    ("Screening result", "Code", "Restricted"), ("KYC status", "Code", "Restricted"), ("Next KYC review date", "Date", "Restricted"),
]
# elements that describe the client or the facility, so every record must agree
MEMO = {"obligor rating", "facility rating", "probability of default (pd)", "loss given default (lgd)", "rating model", "rating date",
        "audit status", "valuation date", "perfection status", "ltv ratio", "headroom", "next test date", "ecl stage", "approval authority",
        "approval id", "facility type", "facility id", "rm name", "watchlist status", "exposure at default (ead)", "aml risk rating",
        "governing law", "facility purpose", "repayment profile", "tranche seniority", "security type", "days past due", "loan status"}


# ---------------- vendor CSV ----------------
def ideal_csv(path: Path, dest: Path):
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    H = rows[0][:-1] + ["Interest Rate", "Margin", rows[0][-1]]   # a complete Refinitiv record carries pricing
    out = [H]
    for fid, R in REF.items():
        v = {"Obligor": R["name"], "Provider": "Refinitiv", "Report Date": AS_OF.isoformat(), "Ctry": R["country"],
             "Total Revenue": f"{R['rev']:,.0f}", "EBITDA (USD)": f"{R['ebitda']:,.0f}", "Facility Limit": f"{R['fac']:,.0f}",
             "Drawn": f"{R['out']:,.0f}", "Credit Rating": R["rating"], "Sanctions Status": "No Match",
             "Interest Rate": f"{R['rate'] * 100:.2f}%", "Margin": f"{R['margin'] * 100:.2f}%",
             "Analyst comment": "Hypothetical vendor export (ideal version: values agree with every other source)"}
        out.append([v.get(h, "") for h in H])
    with dest.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(out)


def main():
    import sys
    sys.path.insert(0, str(ROOT.parent / "backend"))
    from app.engine.values import validate_element
    for sub in ("internal", "external", "other-layouts"):       # README.md in OUT is kept
        shutil.rmtree(OUT / sub, ignore_errors=True)
        (OUT / sub).mkdir(parents=True)
    for p in sorted((SRC / "external").glob("*.xlsx")):
        ideal_external(p, OUT / "external" / p.name)
    for p in sorted((SRC / "internal").glob("*.xlsx")):
        ideal_internal(p, OUT / "internal" / p.name, validate_element)
    for p in sorted((SRC / "other-layouts").glob("*.csv")):
        ideal_csv(p, OUT / "other-layouts" / p.name)
    print("Wrote", sum(1 for p in OUT.rglob("*.*") if p.parent != OUT), "files to", OUT)


if __name__ == "__main__":
    main()
