"""Build a messy test folder for the Data360 folder scan, plus an answer key to score the scan against.

The folder looks like part of a bank's shared drive and three people's home folders: the hypothetical
sample files spread across them, exact copies, an Office lock file, files hidden in system and hidden
folders, unrelated decoy spreadsheets, one genuine file for a borrower that is not in the sample set,
and a few documents (Word, PDF, email, text) that only the AI Collector will be able to read.

The answer key is written NEXT TO the folder, not inside it, so the scan never sees it.

    python seed/make_scan_test.py                      # ./scan-test and ./scan-test-answer-key.json
    python seed/make_scan_test.py C:/Users/you/Data360-test           # Windows (PowerShell)
    python3 seed/make_scan_test.py /mnt/c/Users/you/Data360-test      # WSL
(Use a folder you own: Windows does not let normal users write files at the top of C:\.)

Standard library only. All content is hypothetical. Running it again rebuilds the folder from scratch.
"""
from __future__ import annotations

import csv
import io
import json
import shutil
import sys
import zipfile
from email.message import EmailMessage
from pathlib import Path

SEED = Path(__file__).resolve().parent
SAMPLES = SEED / "sample-files"
BORROWERS = ["Orion Infrastructure Holdings Pte. Ltd.", "Meridian Renewables Limited", "Pacific Components Manufacturing Sdn. Bhd.",
             "Aster Logistics & Warehousing Co., Ltd.", "Nexus Digital Services Pte. Ltd.", "Haneda Consumer Products KK", "HarbourVest"]
NEW_BORROWER = "Kestrel Shipping Pte. Ltd."

# who keeps which internal system export
INTERNAL_OWNER = {
    "Loan systems": "grace.lee/Documents/System exports", "Risk platforms": "grace.lee/Documents/System exports",
    "Treasury systems": "grace.lee/Documents/System exports", "Market feeds": "grace.lee/Documents/System exports",
    "CRM tools": "amelia.tan/Documents/CRM", "Email archives": "amelia.tan/Documents/CRM",
    "Credit agencies": "rajesh.kumar/Documents/Ratings", "External news sources": "rajesh.kumar/Documents/Research",
    "Document repositories": "Shared/Credit/Document index", "Legal systems": "Shared/Legal",
    "Physical & hard-copy records": "Shared/Operations/Vault register",
}


def _docx(paragraphs: list[str]) -> bytes:
    """A minimal valid Word document."""
    body = "".join(f"<w:p><w:r><w:t xml:space=\"preserve\">{p.replace('&', '&amp;').replace('<', '&lt;')}</w:t></w:r></w:p>" for p in paragraphs)
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                               '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                               '<Default Extension="xml" ContentType="application/xml"/>'
                               '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/document.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                             f"<w:body>{body}</w:body></w:document>",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in files.items():
            z.writestr(k, v)
    return buf.getvalue()


def _pdf(lines: list[str]) -> bytes:
    """A minimal valid one-page PDF with text."""
    esc = lambda s: s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    text = "BT /F1 11 Tf 56 780 Td 14 TL " + " ".join(f"({esc(l)}) Tj T*" for l in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", f"<< /Length {len(text)} >>\nstream\n{text}\nendstream"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + "".join(f"{o:010d} 00000 n \n" for o in offs).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def _eml(subject: str, sender: str, to: str, date: str, body: str) -> bytes:
    m = EmailMessage()
    m["Subject"], m["From"], m["To"], m["Date"] = subject, sender, to, date
    m.set_content(body)
    return m.as_bytes()


def _csv(rows: list[list]) -> bytes:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue().encode("utf-8")


def build(dest: Path, key_path: Path) -> dict:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    key: list[dict] = []

    def put(rel: str, data: bytes, expect: str, why: str, borrowers: list[str] | None = None, group: str | None = None):
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        key.append({"path": rel, "expect": expect, "why": why, "borrowers": borrowers or [], "group": group})

    # ---- internal system exports: every borrower is in every dictionary
    for f in sorted((SAMPLES / "internal").glob("*.xlsx")):
        system = f.name.split(" - ")[0]
        put(f"{INTERNAL_OWNER[system]}/{f.name}", f.read_bytes(), "loaded", "Internal data dictionary export", BORROWERS, group=f.name)

    # ---- external vendor files, filed per client by the relationship managers and analysts
    for f in sorted((SAMPLES / "external").glob("*.xlsx")):
        b = next(x for x in BORROWERS if x in f.name)
        owner = "amelia.tan/Documents/Clients" if b in ("HarbourVest", "Meridian Renewables Limited", "Nexus Digital Services Pte. Ltd.") \
            else "rajesh.kumar/Documents/Portfolio"
        folder = b.split(" ")[0] if b != "HarbourVest" else "HarbourVest"
        put(f"{owner}/{folder}/{f.name}", f.read_bytes(), "loaded", "External vendor data for one client", [b], group=f.name)

    # ---- a vendor export in its own layout (different column names, short borrower names)
    refin = (SAMPLES / "other-layouts" / "Bank B vendor export - Refinitiv.csv").read_bytes()
    REFIN_B = ["HarbourVest", "Orion Infrastructure Holdings Pte. Ltd."]   # written there as "HarbourVest Inc." and "... Pte Ltd"
    put("amelia.tan/Downloads/Bank B vendor export - Refinitiv.csv", refin, "loaded", "Vendor CSV in another layout, short borrower names", REFIN_B, group="refinitiv")

    # ---- exact copies: one of each group should load, the rest are duplicates
    hv = (SAMPLES / "external" / "External - HarbourVest.xlsx").read_bytes()
    put("amelia.tan/Downloads/Copy of External - HarbourVest.xlsx", hv, "duplicate", "Renamed copy of a file already found", ["HarbourVest"], group="External - HarbourVest.xlsx")
    loan = (SAMPLES / "internal" / "Loan systems - Data Dictionary.xlsx").read_bytes()
    put("rajesh.kumar/Documents/old/Loan systems - Data Dictionary (old copy).xlsx", loan, "duplicate", "Copy kept in an old folder", BORROWERS, group="Loan systems - Data Dictionary.xlsx")
    put("Shared/Credit/Archive/2026/Refinitiv export.csv", refin, "duplicate", "Copy on the shared drive", REFIN_B, group="refinitiv")

    # ---- places the scan deliberately does not look
    put("grace.lee/AppData/Local/Excel/Loan systems - Data Dictionary.xlsx", loan, "skipped", "Inside a system folder (AppData)")
    put("grace.lee/.cache/External - HarbourVest.xlsx", hv, "skipped", "Inside a hidden folder")
    put("grace.lee/Documents/System exports/~$Loan systems - Data Dictionary.xlsx", b"\x00lock", "skipped", "Office lock file")
    put("Shared/Credit/logo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "skipped", "Not a data or document file")

    # ---- a genuine lender export for a borrower that is not in the sample set: should load as a new borrower
    put("Shared/Deals/Pipeline/Kestrel Shipping - lender export.csv", _csv([
        ["Obligor", "Provider", "Report Date", "Ctry", "Total Revenue", "EBITDA (USD)", "Facility Limit", "Drawn", "Credit Rating", "Sanctions Status", "Analyst comment"],
        [NEW_BORROWER, "Refinitiv", "2026-10-02", "Singapore", "640,000,000", "131,000,000", "220,000,000", "184,000,000", "BBB-", "No Match", "Hypothetical new-to-bank prospect"],
    ]), "loaded", "Loan data for a borrower that is new to Data360", [NEW_BORROWER])

    # ---- decoys: spreadsheets that are not loan data and must not load (or create borrowers)
    put("Shared/Finance/Office supplies inventory.csv", _csv([["Item", "Quantity", "Unit cost (SGD)", "Supplier"], ["A4 paper (box)", "40", "28.50", "OfficeMart"],
                                                             ["Toner TN-2480", "12", "96.00", "PrintCo"]]), "not_recognised", "Decoy: office inventory")
    put("Shared/HR/Staff roster Q4.csv", _csv([["Name", "Team", "Start date", "Desk"], ["Amelia Tan", "Coverage", "2023-02-01", "12-04"],
                                               ["Rajesh Kumar", "Credit", "2021-07-19", "12-11"]]), "not_recognised", "Decoy: staff roster")
    put("amelia.tan/Downloads/Team lunch budget.csv", _csv([["Month", "Budget (SGD)", "Spent (SGD)"], ["October", "600", "512.40"]]), "not_recognised", "Decoy: lunch budget")
    put("rajesh.kumar/Documents/FX rates.csv", _csv([["Currency", "Rate to USD", "Date"], ["SGD", "1.35", "2026-10-01"], ["JPY", "150.2", "2026-10-01"]]),
        "not_recognised", "Decoy: FX table with dates and numbers but no borrower")
    put("amelia.tan/Downloads/Harbour View Dental - bookings.csv", _csv([["Patient", "Appointment", "Dentist", "Fee (SGD)"], ["J. Lim", "2026-10-14 09:30", "Dr Wong", "120"]]),
        "not_recognised", "Decoy: name close to HarbourVest, not loan data")

    # ---- documents the AI Collector will read in step 2 (facts are hypothetical)
    put("Shared/Credit/Committee/2026/Facility agreement summary - HarbourVest.docx", _docx([
        "HYPOTHETICAL. Facility agreement summary: HarbourVest Partners, LLC (SMBC-ASI-007).",
        "Facility: USD 500,000,000 revolving credit facility. Drawn: USD 412,500,000.",
        "Final maturity: 31 December 2029. Margin: 150 bps over SOFR. Governing law: New York.",
        "Financial covenant: net leverage not above 4.25x, tested quarterly."]), "not_read_yet", "Word document for the AI Collector", ["HarbourVest"])
    put("rajesh.kumar/Documents/Ratings/Rating letter - Orion Infrastructure.pdf", _pdf([
        "HYPOTHETICAL rating letter", "Issuer: Orion Infrastructure Holdings Pte. Ltd.", "Long-term issuer rating: BBB+ (stable)",
        "Date: 15 September 2026"]), "not_read_yet", "PDF for the AI Collector", ["Orion Infrastructure Holdings Pte. Ltd."])
    put("amelia.tan/Mail/RE_ HarbourVest facility amendment.eml", _eml(
        "RE: HarbourVest facility amendment", "amelia.tan@bank.example", "credit.team@bank.example", "Mon, 05 Oct 2026 10:12:00 +0800",
        "Hypothetical. Agent confirms the HarbourVest RCF stays at USD 500m; maturity unchanged at 2029-12-31. "
        "Beneficial owner per KYC refresh: HarbourVest Partners, LLC."), "not_read_yet", "Email for the AI Collector", ["HarbourVest"])
    put("amelia.tan/Desktop/Call notes - Meridian.txt", (
        "Hypothetical call notes, 2 Oct 2026. Meridian Renewables: CFO says FY revenue around USD 1.12bn, "
        "EBITDA USD 265m. Asked about a USD 50m accordion.\n").encode(), "not_read_yet", "Text notes for the AI Collector", ["Meridian Renewables Limited"])

    truth = {"folder": str(dest), "borrowers": sorted([*BORROWERS, NEW_BORROWER]), "files": key,
             "note": "Hypothetical test data. Expected outcomes: loaded, duplicate (one copy of each group loads), not_recognised, not_read_yet, skipped."}
    try:
        key_path.write_text(json.dumps(truth, indent=1), encoding="utf-8")
    except PermissionError:   # e.g. next to a folder at the top of C:\, where Windows only lets admins write files
        key_path = Path.cwd() / key_path.name
        key_path.write_text(json.dumps(truth, indent=1), encoding="utf-8")
    truth["key_path"] = str(key_path)
    return truth


def main():
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "scan-test"
    dest = dest.resolve()
    key = dest.with_name(dest.name + "-answer-key.json")
    t = build(dest, key)
    n = {k: sum(1 for f in t["files"] if f["expect"] == k) for k in ("loaded", "duplicate", "not_recognised", "not_read_yet", "skipped")}
    print(f"Built {dest} with {len(t['files'])} files: " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in n.items()))
    print(f"Answer key: {t['key_path']} (outside the folder, so the scan cannot see it)")


if __name__ == "__main__":
    main()
