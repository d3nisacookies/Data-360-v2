"""Replace client names, identifiers and personal data with tokens before text leaves the server."""
from __future__ import annotations

import json
import re

EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
PHONE = re.compile(r"(?<![\w-])\+?\d[\d ()-]{7,}\d(?![\w-])")
LEI = re.compile(r"\b[A-Z0-9]{18}\d{2}\b")
PERSON_LIKE = re.compile(r"^[A-Z][a-z]+(?:[ -][A-Z][a-z'’-]+){1,3}$")
COMPANY = re.compile(r"\b(LLC|Ltd|Limited|Inc|Corp|Pte|Bhd|PLC|LP|GmbH|KK|Partners|Holdings|Group|Bank|Capital|Fund)\b", re.I)
PERSON_EL = re.compile(r"name|signator|contact|ubo|owner|director|officer|guarantor name|beneficial|rm\b|relationship manager|approver|person", re.I)


class Redactor:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.fwd: dict[str, str] = {}   # original (lower) -> token
        self.orig: dict[str, str] = {}  # token -> original
        self.n: dict[str, int] = {}
        self._rx = None

    def add(self, value, kind: str) -> str | None:
        v = str(value or "").strip()
        if not self.enabled or len(v) < 3 or v.lower() in self.fwd:
            return self.fwd.get(v.lower())
        self.n[kind] = self.n.get(kind, 0) + 1
        tok = f"[{kind}-{self.n[kind]}]"
        self.fwd[v.lower()] = tok
        self.orig[tok] = v
        self._rx = None
        return tok

    def _pattern(self):
        if self._rx is None and self.fwd:
            terms = sorted(self.fwd, key=len, reverse=True)
            self._rx = re.compile("|".join(re.escape(t) for t in terms), re.I)
        return self._rx

    def text(self, s: str) -> str:
        if not self.enabled or not s:
            return s
        rx = self._pattern()
        if rx:
            s = rx.sub(lambda m: self.fwd[m.group(0).lower()], s)
        s = EMAIL.sub(lambda m: self.add(m.group(0), "EMAIL") or "[EMAIL]", s)
        s = LEI.sub(lambda m: self.add(m.group(0), "ID") or "[ID]", s)
        s = PHONE.sub(lambda m: self.add(m.group(0), "PHONE") or "[PHONE]" if sum(c.isdigit() for c in m.group(0)) >= 8 and not re.match(r"^\d{4}-\d{2}-\d{2}", m.group(0).strip()) else m.group(0), s)
        return s

    def obj(self, o) -> str:
        return self.text(json.dumps(o, ensure_ascii=False, default=str))

    def restore(self, s: str) -> str:
        if not self.orig or not s:
            return s
        return re.sub(r"\[(?:CLIENT|ENTITY|ID|PERSON|EMAIL|PHONE)-\d+\]", lambda m: self.orig.get(m.group(0), m.group(0)), s)


def for_borrower(db, borrower, ds, enabled: bool = True) -> Redactor:
    """Tokens for this client (CLIENT-1), every other client, identifiers and the people in the data."""
    from sqlalchemy import select
    from ..engine.values import validate_element
    from ..models import Borrower
    R = Redactor(enabled)
    if not enabled:
        return R
    for name in [borrower.name, *(borrower.aliases or [])]:
        R.fwd.setdefault(name.lower(), "[CLIENT-1]")
    R.orig["[CLIENT-1]"] = borrower.name
    R.n["CLIENT"] = 1
    for b in db.scalars(select(Borrower).where(Borrower.id != borrower.id)).all():
        tok = R.add(b.name, "CLIENT")
        for a in b.aliases or []:
            R.fwd.setdefault(a.lower(), tok)
    for f in borrower.facility_ids or []:
        R.add(f, "ID")
    for r in ds.records:
        for f in ("Registration_Number", "Tax_ID", "LEI"):
            if r.fields.get(f):
                R.add(r.fields[f], "ID")
        o = str(r.fields.get("Beneficial_Owner") or "").strip()
        if o:
            R.add(o, "ENTITY" if COMPANY.search(o) else "PERSON")
    for e in ds.elements:
        v = str(e.value or "").strip()
        if not v or len(v) > 80 or validate_element(e.dtype, v):
            continue
        if re.search(r"\d", v) and e.dtype == "Identifier" or re.search(r"\d", v) and re.search(r"registration number|\buen\b|\blei\b|tax id|account number|passport|customer id", e.element, re.I):
            R.add(v, "ID")
        elif "personal" in (e.sensitivity or "").lower() and PERSON_EL.search(e.element) and PERSON_LIKE.match(v) and not COMPANY.search(v):
            R.add(v, "PERSON")
    R._rx = None
    return R
