"""Metadata about each source: system, owner, steward, refresh cycle and data flow.

Defaults are sample values (from the demo console); owners chosen in the Ownership task are
saved per source and override them. Sources not listed get sensible blanks, so a source
uploaded under a new name shows up as "no owner" until someone assigns one.
"""
INTERNAL = {
    "Risk platforms": {"system": "Credit Risk Engine", "owner": "Credit Risk Management", "steward": "Lim Hui Xin", "cycle": "Daily · end-of-day batch", "days": 1,
                       "flow": ["Loan systems · Market feeds", "Credit Risk Engine", "Regulatory reporting (MAS 610/637)"], "method": "Daily batch"},
    "CRM tools": {"system": "Client Relationship Manager", "owner": "Structured Debt Coverage", "steward": "Emily Ng", "cycle": "Real-time", "days": 0.1,
                  "flow": ["Onboarding and KYC", "Client Relationship Manager", "Pipeline reports"], "method": "API"},
    "Treasury systems": {"system": "Treasury Management System", "owner": "Group Treasury & ALM", "steward": "Michael Wong", "cycle": "Intraday", "days": 0.5,
                         "flow": ["Market feeds", "Treasury Management System", "Hedge accounting · ALM"], "method": "Intraday API"},
    "Legal systems": {"system": "Legal Matter & Contract Register", "owner": "Legal · Banking & Finance", "steward": "Grace Lee", "cycle": "Event-driven (on change)", "days": 7,
                      "flow": ["Signed documents", "Legal Matter & Contract Register", "Obligations tracker"], "method": "Event messages"},
    "Physical / hard-copy records": {"system": "Vault & Archive Register", "owner": "Loan Operations · Custody", "steward": "Ahmad Faizal", "cycle": "Manual · monthly reconciliation", "days": 31,
                                     "flow": ["Original documents", "Vault & Archive Register", "Digitisation queue (scan + OCR)"], "method": "Manual scan"},
    "Loan systems": {"system": "Loan Administration System", "owner": "Loan Operations", "steward": "Tan Wei Ming", "cycle": "Daily", "days": 1,
                     "flow": ["Credit approval", "Loan Administration System", "General ledger · Risk engine"], "method": "Daily batch file"},
    "Document repositories": {"system": "Deal Document Repository", "owner": "Credit Administration", "steward": "Arjun Mehta", "cycle": "On upload", "days": 1,
                              "flow": ["Deal team uploads", "Deal Document Repository", "Credit papers"], "method": "Document crawl"},
    "Email archives": {"system": "Email Journal Archive", "owner": "Compliance · Records", "steward": "Nurul Aisyah", "cycle": "Continuous", "days": 1,
                       "flow": ["Mailboxes", "Email Journal Archive", "eDiscovery index"], "method": "Archive export"},
    "Market feeds": {"system": "Market Data Platform", "owner": "Market Data Services", "steward": "Kenji Sato", "cycle": "Real-time", "days": 0.1,
                     "flow": ["Market data vendors", "Market Data Platform", "Treasury · Risk"], "method": "Streaming"},
    "Credit agencies": {"system": "Rating Agency Feeds", "owner": "Credit Risk Management", "steward": "Priya Nair", "cycle": "On rating action", "days": 30,
                        "flow": ["Rating agencies", "Rating Agency Feeds", "Credit Risk Engine"], "method": "Daily file"},
    "External news sources": {"system": "News & Media Monitoring", "owner": "Early Warning Unit", "steward": "Hiroshi Mori", "cycle": "Hourly", "days": 0.1,
                              "flow": ["Newswires", "News & Media Monitoring", "Early warning"], "method": "Hourly API"},
}
INTERNAL["Physical & hard-copy records"] = INTERNAL["Physical / hard-copy records"]

EXTERNAL = {
    "Corporate Registry": {"owner": "KYC Operations", "steward": "Daniel Koh", "cycle": "Monthly", "days": 31, "flow": ["Registry APIs", "Corporate Registry feed"], "method": "Vendor API"},
    "D&B": {"owner": "", "steward": "", "cycle": "Monthly", "days": 31, "flow": ["Dun & Bradstreet", "D&B Direct+ feed"], "method": "Vendor API"},
    "Bureau van Dijk": {"owner": "", "steward": "", "cycle": "Quarterly", "days": 92, "flow": ["Bureau van Dijk", "Orbis extract"], "method": "SFTP file"},
    "Capital IQ": {"owner": "Credit Risk Management", "steward": "Priya Nair", "cycle": "Monthly", "days": 31, "flow": ["S&P Capital IQ", "Capital IQ feed"], "method": "Vendor API"},
    "Bloomberg": {"owner": "Market Data Services", "steward": "Kenji Sato", "cycle": "Daily", "days": 1, "flow": ["Bloomberg", "Bloomberg Data License"], "method": "SFTP file"},
    "Refinitiv": {"owner": "Market Data Services", "steward": "Kenji Sato", "cycle": "Daily", "days": 1, "flow": ["LSEG Refinitiv", "Refinitiv DataScope"], "method": "Vendor API"},
    "Moody's": {"owner": "Credit Risk Management", "steward": "Priya Nair", "cycle": "On rating action", "days": 90, "flow": ["Moody's", "Rating feed"], "method": "Daily file"},
    "ESG Database": {"owner": "", "steward": "", "cycle": "Annual", "days": 365, "flow": ["ESG provider", "ESG extract"], "method": "SFTP file"},
    "Country Risk Database": {"owner": "", "steward": "", "cycle": "Quarterly", "days": 92, "flow": ["Country risk provider", "Country risk extract"], "method": "Manual upload"},
    "Regulatory / Sanctions Feed": {"owner": "Financial Crime Compliance", "steward": "Siti Rahman", "cycle": "Daily", "days": 1,
                                    "flow": ["Sanctions list publishers", "Screening engine"], "method": "Streaming"},
}
OWNER_CHOICES = ["Credit Risk Management", "KYC Operations", "Market Data Services", "Financial Crime Compliance", "Structured Debt Coverage",
                 "Data Governance Office", "Group Treasury & ALM", "Loan Operations", "Credit Administration", "Legal · Banking & Finance"]
REPORT_CATS = ["Regulatory reporting", "Credit documents", "Research", "Internal", "Default and recovery data"]
DOC_CATS = ["Deal documents", "Due diligence", "Borrower deliverables", "Transaction records", "Attachments", "Security originals", "Collateral title documents",
            "Execution formalities", "Hedging and insurance originals", "KYC and authority originals", "Notices and legal service",
            "Working papers and legacy files", "Contracts", "Custody records", "Digitisation metadata"]


def meta(source: str, kind: str, owners: dict | None = None) -> dict:
    """Metadata for one source; `owners` = {source: owner} chosen by users."""
    base = INTERNAL.get(source) if kind == "Internal" else EXTERNAL.get(source)
    if base is None:
        base = INTERNAL.get(source) or EXTERNAL.get(source) or {}
    m = {"system": base.get("system", "Vendor feed" if kind != "Internal" else source), "owner": base.get("owner", ""),
         "steward": base.get("steward", ""), "cycle": base.get("cycle", "Not agreed"), "days": base.get("days"),
         "flow": list(base.get("flow") or ([source, "Vendor feed"] if kind != "Internal" else [source, source + " system"])),
         "method": base.get("method", "File upload"), "assigned": "on record" if base.get("owner") else ""}
    if owners and owners.get(source):
        m.update(owner=owners[source], steward=m["steward"] or "To be named", assigned="by you")
    return m


def owner_of(source: str, owners: dict | None = None) -> str:
    kind = "Internal" if source in INTERNAL else "External"
    m = meta(source, kind, owners)
    if kind == "Internal":
        return f"{m['steward']} (steward)" if m["steward"] else (m["owner"] or "Unassigned")
    return m["owner"] or "Unassigned"
