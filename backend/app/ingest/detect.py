"""Work out what an uploaded file is and propose how its columns map to the data model.

Two layouts are understood:
  dictionary  one row per data element (ID, data source, category, data element, data type, value ...)
  records     one row per source record, one column per field (borrower, source, as-of date, revenue ...)
Anything else is offered as `records` with a column-mapping proposal the user confirms.
"""
import re
from pathlib import Path

from rapidfuzz import fuzz, process

from ..engine.reference import FIELDS, LABEL, META_FIELDS, header_key
from .tabular import Table, read_tables

DICT_COLS = {
    "id": ["id", "element id", "de id"],
    "source": ["data source", "source", "system"],
    "category": ["category"],
    "subcategory": ["sub category", "subcategory", "sub-category"],
    "element": ["data element", "element", "field name", "attribute"],
    "dtype": ["data type", "type"],
    "value": ["example value", "value", "field value"],
    "structure": ["structure"],
    "sensitivity": ["sensitivity", "classification"],
    "borrower": ["borrower name", "borrower", "client", "obligor"],
}

_SYN: dict[str, str] = {}
for _k, (_label, _t, _c, _s, _syns) in FIELDS.items():
    _SYN[header_key(_k)] = _k
    _SYN[header_key(_label)] = _k
    for _x in _syns:
        _SYN.setdefault(header_key(_x), _k)
_SYN_KEYS = list(_SYN)

# sheets that summarise or explain rather than hold source data
SKIP_SHEET = re.compile(r"readme|legend|glossary|summary|crosswalk|coverage|defect|snapshot|instructions|notes", re.I)


def map_header(h: str) -> tuple[str | None, float, str]:
    k = header_key(h)
    if not k:
        return None, 0.0, "none"
    if k in _SYN:
        exact = k in (header_key(_SYN[k]), header_key(LABEL[_SYN[k]]))
        return _SYN[k], 1.0 if exact else 0.95, "exact" if exact else "synonym"
    best = process.extractOne(k, _SYN_KEYS, scorer=fuzz.token_sort_ratio)
    if best and best[1] >= 86:
        return _SYN[best[0]], round(best[1] / 100, 2), "fuzzy"
    return None, 0.0, "none"


def _dict_columns(headers: list[str]) -> dict[str, int]:
    keys = [header_key(h) for h in headers]
    found = {}
    for role, names in DICT_COLS.items():
        for i, k in enumerate(keys):
            if k in names and i not in found.values():
                found[role] = i
                break
    return found


def _guess_source(filename: str) -> str:
    stem = Path(filename).stem
    m = re.match(r"^\s*(?:\d+\s+)?(.+?)\s*-\s*data dictionary", stem, re.I)
    if m:
        return m.group(1).strip()
    return ""


def _guess_borrower(filename: str) -> str:
    m = re.match(r"^(?:External|Internal(?: & External)?)\s*-\s*(.+)$", Path(filename).stem, re.I)
    return m.group(1).strip() if m else ""


def propose(t: Table, filename: str) -> dict:
    """A mapping proposal for one table."""
    dc = _dict_columns(t.headers)
    if {"element", "value"} <= dc.keys():
        missing = []
        defaults = {"source": "" if "source" in dc else _guess_source(filename), "zone": "Internal", "borrower": ""}
        if "borrower" not in dc:
            missing.append("borrower")
        if "source" not in dc and not defaults["source"]:
            missing.append("source")
        return {"format": "dictionary", "sheet": t.sheet, "header_row": t.header_row,
                "columns": [{"header": h, "role": next((r for r, i in dc.items() if i == j), None)} for j, h in enumerate(t.headers)],
                "defaults": defaults, "missing": missing, "rows": len(t.rows)}

    cols, used = [], {}
    for j, h in enumerate(t.headers):
        f, conf, how = map_header(h)
        cols.append({"header": h, "field": f, "confidence": conf, "how": how})
        if f and (f not in used or conf > cols[used[f]]["confidence"]):
            if f in used:
                cols[used[f]].update(field=None, confidence=0.0, how="duplicate")
            used[f] = j
        elif f:
            cols[j].update(field=None, confidence=0.0, how="duplicate")
    mapped = {c["field"] for c in cols if c["field"]}
    defaults = {"source": "", "zone": "External", "borrower": "" if "Borrower_Name" in mapped else _guess_borrower(filename)}
    missing = []
    if "Borrower_Name" not in mapped and not defaults["borrower"]:
        missing.append("borrower")
    if "External_Source" not in mapped:
        missing.append("source")
    if not (mapped - META_FIELDS):
        missing.append("fields")
    return {"format": "records", "sheet": t.sheet, "header_row": t.header_row, "columns": cols,
            "defaults": defaults, "missing": missing, "rows": len(t.rows),
            "uncertain": [c["header"] for c in cols if c["how"] == "fuzzy"]}


def _score(p: dict, t: Table) -> float:
    if SKIP_SHEET.search(t.sheet):
        return -1
    if p["format"] == "dictionary":
        return 1000 + len(t.rows)
    n = sum(1 for c in p["columns"] if c["field"] and c["field"] not in META_FIELDS)
    return n * 10 + min(len(t.rows), 500) / 100 - len(p["missing"]) * 5


def detect(path: str | Path, filename: str) -> dict:
    tables = read_tables(path)
    if not tables:
        return {"format": "unknown", "sheets": [], "missing": ["fields"], "error": "No table with a header row found"}
    props = [(propose(t, filename), t) for t in tables]
    best = max(props, key=lambda x: _score(*x))[0]
    best["sheets"] = [{"name": t.sheet, "rows": len(t.rows), "format": p["format"]} for p, t in props]
    return best


def propose_for_sheet(path: str | Path, filename: str, sheet: str) -> dict:
    tables = read_tables(path)
    t = next((x for x in tables if x.sheet == sheet), None)
    if not t:
        raise ValueError(f"Sheet {sheet!r} not found")
    p = propose(t, filename)
    p["sheets"] = [{"name": x.sheet, "rows": len(x.rows)} for x in tables]
    return p
