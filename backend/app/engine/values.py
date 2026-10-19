"""Parsing, comparing and validating values by field type."""
import re
from datetime import date, datetime

from .reference import FX, ISO_COUNTRY, MOODYS_TO_SP, RATING_SCALE, TYPE, norm_text

BLANK = {"", "none", "null", "nan", "n/a", "na", "-", "--", "blank", "not provided"}


def is_blank(v) -> bool:
    return v is None or str(v).strip().lower() in BLANK


_SCALE = {"k": 1e3, "m": 1e6, "mn": 1e6, "mm": 1e6, "bn": 1e9, "b": 1e9, "tn": 1e12}


def parse_number(v) -> float | None:
    """'1,240,000,000' / '1.24bn' / 'USD 175,000,000' / '358.5m' -> float in USD where a currency is given."""
    if is_blank(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    ccy = re.search(r"\b([A-Z]{3})\b", s)
    m = re.search(r"(-?[\d,]*\.?\d+)\s*(k|mn|mm|m|bn|b|tn)?\b", s, re.I)
    if not m:
        return None
    try:
        n = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    if m.group(2):
        n *= _SCALE[m.group(2).lower()]
    if ccy and ccy.group(1) in FX and ccy.group(1) != "USD":
        n /= FX[ccy.group(1)]
    return n


def parse_percent(v) -> float | None:
    """Returns a fraction: '2.68%' -> 0.0268, '250 bps' -> 0.025, 0.0268 -> 0.0268."""
    if is_blank(v):
        return None
    if isinstance(v, (int, float)):
        return float(v) / 100 if v > 1 else float(v)
    s = str(v).lower()
    n = parse_number(s)
    if n is None:
        return None
    if "bp" in s:
        return n / 10000
    if "%" in s or n > 1:
        return n / 100
    return n


def parse_date(v) -> date | None:
    if is_blank(v):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for f in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def norm_rating(v) -> str | None:
    if is_blank(v):
        return None
    s = str(v).strip()
    if s in MOODYS_TO_SP:
        return MOODYS_TO_SP[s]
    s = s.upper().replace(" ", "")
    return s if s in RATING_SCALE else None


def norm_country(v) -> str | None:
    if is_blank(v):
        return None
    s = str(v).strip()
    if re.fullmatch(r"[A-Z]{2}", s):
        return s
    return ISO_COUNTRY.get(norm_text(s))


def typed(field: str, v):
    """Value in comparable form for a canonical field."""
    t = TYPE.get(field, "text")
    if is_blank(v):
        return None
    if t in ("money", "number", "ratio", "score"):
        return parse_number(v)
    if t == "percent":
        return parse_percent(v)
    if t == "date":
        d = parse_date(v)
        return d.isoformat() if d else None
    if t == "rating":
        return norm_rating(v) or norm_text(v)
    if t == "country":
        return norm_country(v) or norm_text(v)
    return norm_text(v)


# relative tolerance before two numbers count as different
TOLERANCE = {"money": 0.02, "number": 0.02, "ratio": 0.02, "percent": 0.02}
FIELD_TOLERANCE = {"Facility_Amount": 0.001, "Outstanding_Principal": 0.005, "Leverage_Covenant": 0.001}


def differs(field: str, a, b) -> bool:
    """True if two raw values disagree for this field (blank never differs)."""
    x, y = typed(field, a), typed(field, b)
    if x is None or y is None:
        return False
    t = TYPE.get(field, "text")
    if t in TOLERANCE:
        return abs(x - y) / max(1e-9, abs(y)) > FIELD_TOLERANCE.get(field, TOLERANCE[t])
    if t == "score":
        return abs(x - y) > 5
    return x != y


def fmt(field: str, v) -> str:
    if is_blank(v):
        return "Blank"
    t = TYPE.get(field, "text")
    if t == "money":
        n = parse_number(v)
        return f"USD {n:,.0f}" if n is not None else str(v)
    if t == "percent":
        n = parse_percent(v)
        return f"{n * 100:.2f}%" if n is not None else str(v)
    if t == "ratio":
        n = parse_number(v)
        return f"{n:.2f}x" if n is not None else str(v)
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


# ---------------- validity ----------------
PLACEHOLDER = re.compile(r"(^|\s)(name|names|free text|text|amount|line-item value|price|score|country|isin|uetr|account number|"
                         r"account reference|policy no\.|registry reference|security doc reference|sha-256|conversation id|"
                         r"email address(es)?|person name|bank name|officer name)$", re.I)
ROLE_NAME = re.compile(r"^(Borrower|Client|Company|Entity|Project company|Sponsor holdco|Parent company|Parent group|"
                       r"Infrastructure fund|Participant institution|Participating bank|Hedging bank|Trustee|Independent valuer|"
                       r"Appraisal firm|Records storage vendor|Custodian|Insurer|Provider|Credit bureau|News outlet|Firm|"
                       r"Director|Agent bank|Selling lender|Buying lender|Legacy deal) name$", re.I)


def validate_element(dtype: str, v) -> str | None:
    """Reason a data-dictionary value is invalid for its declared data type, or None."""
    s = "" if v is None else str(v).strip()
    if not s:
        return "Empty"
    if PLACEHOLDER.search(s) or re.search(r"e\.g\.", s, re.I) or ROLE_NAME.match(s):
        return "Placeholder, not a real value"
    t = (dtype or "").strip()
    if t == "Code" and " / " in s:
        return "List of options, not a single value"
    if t == "Date" and not re.search(r"\d{4}-\d{2}-\d{2}|FY\d{4}|\d{4}-Q\d|^\d{4}$|v\d", s):
        return "Not a date"
    if t == "Date range" and not (re.search(r"\d{4}-\d{2}-\d{2}.*\d{4}-\d{2}-\d{2}", s) or re.fullmatch(r"\d{4}-\d{4}", s)):
        return "Not a date range"
    if t == "Amount" and not re.search(r"\d", s):
        return "No number"
    if t == "Amount" and not re.search(r"\b[A-Z]{3}\b", s):
        return "No currency"
    if t == "Percentage" and not re.search(r"%|bps", s):
        return "No % or bps unit"
    if t == "Boolean" and not re.match(r"^(Y|N)\b", s):
        return "Not Y/N"
    if t in ("Number", "Identifier") and not re.search(r"\d", s):
        return "Not a number" if t == "Number" else "Not an identifier"
    if t == "File" and not re.search(r"\.(pdf|xlsx|pptx|docx)$", s, re.I) and not re.match(r"^(PDF|XLSX|PPTX|Signed PDFs)", s):
        return "Not a file reference"
    return None


def validate_field(field: str, v) -> str | None:
    """Reason a canonical-field value is invalid, or None. Blank is not invalid (completeness covers it)."""
    if is_blank(v):
        return None
    t = TYPE.get(field, "text")
    if t in ("money", "number", "ratio", "score") and parse_number(v) is None:
        return "Not a number"
    if t == "money" and (parse_number(v) or 0) < 0:
        return "Negative amount"
    if t == "percent" and parse_percent(v) is None:
        return "Not a percentage"
    if t == "date" and parse_date(v) is None:
        return "Not a date"
    if t == "rating" and norm_rating(v) is None:
        return "Not on the rating scale"
    if t == "country" and norm_country(v) is None:
        return "Unknown country"
    if t == "score" and not (0 <= (parse_number(v) or 0) <= 100):
        return "Score outside 0-100"
    return None
