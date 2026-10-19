"""Reference data the engine and the column mapper share.

FIELDS is the canonical credit-memo data model. Uploaded columns are mapped onto
these keys (by exact name, synonym or fuzzy match); anything that does not map is
kept under its own header so nothing is lost.
"""
import re
import unicodedata

# key: (label, type, critical, section, synonyms)
#   type: text | number | money | ratio | percent | date | rating | country | flag | score | id | status
FIELDS: dict[str, tuple[str, str, bool, str, list[str]]] = {
    "Record_ID": ("Record ID", "id", False, "Lineage", ["record id", "row id", "ref id"]),
    "Facility_ID": ("Facility ID", "id", False, "Facility", ["facility id", "facility ref", "deal id", "loan id", "facility number"]),
    "Borrower_Name": ("Borrower name", "text", True, "Identity", ["borrower", "borrower name", "obligor", "obligor name", "client name", "customer name", "company name", "entity name", "legal name", "counterparty name"]),
    "Country": ("Country", "country", True, "Identity", ["country", "country of incorporation", "domicile", "incorporation country", "country of risk"]),
    "Industry": ("Industry", "text", False, "Identity", ["industry", "sector", "industry sector", "gics sector"]),
    "External_Source": ("Source", "text", False, "Lineage", ["source", "data source", "external source", "provider", "vendor", "feed"]),
    "Source_Zone": ("Source zone", "text", False, "Lineage", ["zone", "source zone", "source type"]),
    "As_of_Date": ("As-of date", "date", False, "Lineage", ["as of date", "as of", "asof", "date", "report date", "data date", "valuation date", "snapshot date", "effective date"]),
    "Registration_Number": ("Registration number", "id", True, "Identity", ["registration number", "registration no", "reg no", "company number", "uen", "crn", "company registration number", "ein"]),
    "Beneficial_Owner": ("Beneficial owner", "text", True, "Identity", ["beneficial owner", "ubo", "ultimate beneficial owner", "owner", "ultimate owner"]),
    "Registry_Status": ("Registry status", "status", False, "Identity", ["registry status", "entity status", "company status", "legal status"]),
    "External_Rating": ("External rating", "rating", True, "Credit", ["external rating", "rating", "credit rating", "issuer rating", "agency rating", "long term rating"]),
    "Revenue": ("Revenue", "money", True, "Financials", ["revenue", "revenues", "total revenue", "sales", "turnover", "net sales"]),
    "EBITDA": ("EBITDA", "money", True, "Financials", ["ebitda", "adjusted ebitda", "operating ebitda"]),
    "Net_Debt": ("Net debt", "money", False, "Financials", ["net debt", "net borrowings"]),
    "Leverage": ("Leverage (reported)", "ratio", False, "Financials", ["leverage", "net leverage", "debt to ebitda", "debt ebitda", "leverage ratio"]),
    "Facility_Amount": ("Facility amount", "money", True, "Facility", ["facility amount", "commitment", "total commitment", "facility limit", "limit", "facility size", "committed amount"]),
    "Outstanding_Principal": ("Outstanding principal", "money", True, "Facility", ["outstanding principal", "outstanding", "drawn amount", "drawn", "utilisation", "utilization", "principal outstanding", "exposure drawn"]),
    "Interest_Rate": ("All-in interest rate", "percent", False, "Facility", ["interest rate", "all in rate", "all-in rate", "coupon"]),
    "Margin": ("Margin", "percent", False, "Facility", ["margin", "spread", "credit spread"]),
    "Maturity_Date": ("Maturity date", "date", True, "Facility", ["maturity date", "maturity", "final maturity", "final maturity date", "expiry date"]),
    "Currency": ("Currency", "text", False, "Facility", ["currency", "ccy", "facility currency"]),
    "Collateral_Value": ("Collateral value", "money", False, "Security", ["collateral value", "collateral", "security value", "valuation amount"]),
    "Leverage_Covenant": ("Leverage covenant", "ratio", False, "Covenants", ["leverage covenant", "covenant", "covenant level", "max leverage"]),
    "Current_Ratio": ("Current ratio", "ratio", False, "Financials", ["current ratio"]),
    "Default_Flag": ("Default flag", "flag", False, "Credit", ["default flag", "default", "in default", "defaulted"]),
    "Sanctions_Screening": ("Sanctions screening", "status", True, "Compliance", ["sanctions screening", "sanctions", "screening result", "sanctions status", "screening"]),
    "ESG_Score": ("ESG score", "score", False, "ESG", ["esg score", "esg", "esg rating", "sustainability score"]),
    "Country_Risk_Score": ("Country risk score", "score", False, "Country", ["country risk score", "country risk"]),
    "Data_Quality_Status": ("Provider quality flag", "status", False, "Lineage", ["data quality status", "dq status", "quality flag", "quality status"]),
    "Data_Confidence": ("Provider confidence", "status", False, "Lineage", ["data confidence", "confidence"]),
    "Source_Reference": ("Source reference", "id", False, "Lineage", ["source reference", "source ref", "reference"]),
    "Diagram_Source_Label": ("Source label", "text", False, "Lineage", ["diagram source label", "source label"]),
    "Notes": ("Notes", "text", False, "Lineage", ["notes", "comment", "comments", "remarks"]),
}
LABEL = {k: v[0] for k, v in FIELDS.items()}
TYPE = {k: v[1] for k, v in FIELDS.items()}
CRITICAL = [k for k, v in FIELDS.items() if v[2]]
SECTION = {k: v[3] for k, v in FIELDS.items()}
# fields that describe the row rather than the borrower
META_FIELDS = {"Record_ID", "External_Source", "Source_Zone", "As_of_Date", "Data_Quality_Status", "Data_Confidence",
               "Source_Reference", "Diagram_Source_Label", "Notes", "Facility_ID", "Borrower_Name"}
VALUE_FIELDS = [k for k in FIELDS if k not in META_FIELDS or k == "Borrower_Name"]

# Which source wins for each field (survivorship). First listed = golden source.
GOLD_PRIORITY: dict[str, list[str]] = {
    "Borrower_Name": ["Corporate Registry"],
    "Registration_Number": ["Corporate Registry"],
    "Registry_Status": ["Corporate Registry"],
    "Beneficial_Owner": ["Corporate Registry", "Bureau van Dijk"],
    "Country": ["Corporate Registry"],
    "Industry": ["Corporate Registry"],
    "External_Rating": ["Moody's", "Capital IQ"],
    "Revenue": ["Bureau van Dijk", "Capital IQ"],
    "EBITDA": ["Bureau van Dijk", "Capital IQ"],
    "Net_Debt": ["Bureau van Dijk", "Capital IQ"],
    "Leverage": ["Bureau van Dijk", "Capital IQ"],
    "Current_Ratio": ["Bureau van Dijk", "Capital IQ"],
    "Facility_Amount": ["Bloomberg", "Capital IQ"],
    "Outstanding_Principal": ["Bloomberg", "Capital IQ"],
    "Maturity_Date": ["Bloomberg", "Capital IQ"],
    "Interest_Rate": ["Bloomberg", "Refinitiv"],
    "Margin": ["Bloomberg", "Refinitiv"],
    "Currency": ["Bloomberg", "Capital IQ"],
    "Collateral_Value": ["Bureau van Dijk", "Capital IQ"],
    "Leverage_Covenant": ["Capital IQ"],
    "Sanctions_Screening": ["Regulatory / Sanctions Feed"],
    "ESG_Score": ["ESG Database"],
    "Country_Risk_Score": ["Country Risk Database"],
    "Default_Flag": ["Capital IQ", "Bureau van Dijk"],
}
# Golden values come from record-level feeds. Internal data-dictionary elements are
# checked against the golden record (they are often held per facility, not per borrower).

# How much each source type is trusted (0-1), used for tie-breaks and the reliability criterion.
RELIABILITY = {
    "Corporate Registry": 0.95, "Moody's": 0.95, "Regulatory / Sanctions Feed": 0.9, "Bureau van Dijk": 0.8,
    "Capital IQ": 0.8, "D&B": 0.75, "Bloomberg": 0.85, "Refinitiv": 0.85, "ESG Database": 0.6,
    "Country Risk Database": 0.7, "Loan systems": 0.9, "Risk platforms": 0.85, "Treasury systems": 0.85,
    "Legal systems": 0.85, "CRM tools": 0.65, "Physical & hard-copy records": 0.9, "Physical / hard-copy records": 0.9, "Document repositories": 0.8,
    "Email archives": 0.45, "Market feeds": 0.8, "Credit agencies": 0.9, "External news sources": 0.4,
}
DEFAULT_RELIABILITY = 0.6

# Data-dictionary element names that carry a canonical field.
ELEMENT_FIELD = {
    "legal name": "Borrower_Name", "client legal name": "Borrower_Name",
    "company registration number (uen)": "Registration_Number", "company registration number": "Registration_Number",
    "country of incorporation": "Country", "issuer rating": "External_Rating",
    "total commitment": "Facility_Amount", "drawn amount": "Outstanding_Principal",
    "final maturity date": "Maturity_Date", "screening result": "Sanctions_Screening",
}

RATING_SCALE = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-",
                "CCC+", "CCC", "CCC-", "CC", "C", "D"]
MOODYS_TO_SP = {"Aaa": "AAA", "Aa1": "AA+", "Aa2": "AA", "Aa3": "AA-", "A1": "A+", "A2": "A", "A3": "A-", "Baa1": "BBB+",
                "Baa2": "BBB", "Baa3": "BBB-", "Ba1": "BB+", "Ba2": "BB", "Ba3": "BB-", "B1": "B+", "B2": "B", "B3": "B-"}
# agency scale -> internal grade (sample mapping; confirm with Credit Risk)
INTERNAL_GRADE = {"A+": "3", "A": "4+", "A-": "4", "BBB+": "4-", "BBB": "5+", "BBB-": "5", "BB+": "5-", "BB": "6+", "BB-": "6"}

ISO_COUNTRY = {"united states": "US", "usa": "US", "us": "US", "singapore": "SG", "hong kong": "HK", "malaysia": "MY",
               "thailand": "TH", "japan": "JP", "vietnam": "VN", "indonesia": "ID", "philippines": "PH", "india": "IN",
               "australia": "AU", "united kingdom": "GB", "uk": "GB", "china": "CN", "korea": "KR", "south korea": "KR",
               "taiwan": "TW", "germany": "DE", "france": "FR", "netherlands": "NL", "luxembourg": "LU", "cayman islands": "KY"}

# units per USD (sample reference rates; replace with the bank's rate source)
FX = {"USD": 1, "SGD": 1.35, "JPY": 150, "EUR": 0.92, "HKD": 7.8, "MYR": 4.5, "THB": 35, "IDR": 16000, "GBP": 0.79, "AUD": 1.52}

# refresh cycle in days per source, used for "feed behind cycle"
REFRESH_DAYS = {"Corporate Registry": 31, "D&B": 31, "Bureau van Dijk": 92, "Capital IQ": 31, "Bloomberg": 1,
                "Refinitiv": 1, "Moody's": 90, "ESG Database": 365, "Country Risk Database": 92,
                "Regulatory / Sanctions Feed": 1}

# owners used when escalating (sample; editable per bank later)
OWNER = {"Sanctions_Screening": "Financial Crime Compliance", "Beneficial_Owner": "KYC Operations",
         "Registration_Number": "KYC Operations", "Registry_Status": "KYC Operations"}
DEFAULT_OWNER = "Credit analyst"

LEGAL_SUFFIX = re.compile(r"\b(pte|ltd|limited|llc|inc|incorporated|corp|corporation|co|company|plc|sdn|bhd|kk|"
                          r"k\.k|gmbh|ag|sa|nv|bv|lp|llp|holdings?|group|the)\b\.?", re.I)


def norm_text(v) -> str:
    s = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def name_key(name: str) -> str:
    """Key for matching company names: no case, punctuation or legal suffixes."""
    k = LEGAL_SUFFIX.sub(" ", norm_text(name))
    return re.sub(r"\s+", " ", k).strip() or norm_text(name)


def header_key(h) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(h).replace("_", " ").lower()).strip()
