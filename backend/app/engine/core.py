"""Dataset model shared by every step, and the golden record.

A Dataset is one borrower's data as plain Python objects:
  records   one per source row (wide files): source, as-of date, provider flag, fields
  elements  one per data-dictionary element (internal systems)
Clean returns changes (removed records, field corrections) that `apply_changes` replays,
so every step can run on "as sourced" or "as cleaned" data.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date, timedelta

from .reference import ELEMENT_FIELD, GOLD_PRIORITY, LABEL, RELIABILITY, DEFAULT_RELIABILITY, VALUE_FIELDS
from .values import differs, fmt, is_blank, typed

BAD_FLAGS = {"WRONG", "INCONSISTENT", "STALE"}


@dataclass
class Rec:
    key: str
    source: str
    zone: str
    as_of: date | None
    flag: str
    upload_id: int
    row: int
    fields: dict[str, str] = field(default_factory=dict)
    status: str = ""  # "" | CORRECTED | RECONCILED
    removed: bool = False

    @property
    def rid(self) -> str:
        return self.fields.get("Record_ID") or self.key.split(":", 1)[-1]


@dataclass
class El:
    key: str
    source: str
    element: str
    value: str | None
    dtype: str
    sensitivity: str
    category: str
    label: str
    upload_id: int
    removed: bool = False

    @property
    def canonical(self) -> str | None:
        return ELEMENT_FIELD.get(self.element.strip().lower())


@dataclass
class Dataset:
    borrower: str
    records: list[Rec]
    elements: list[El]
    facility_ids: list[str]
    aliases: list[str]
    ref_date: date
    stale_days: int = 90
    version: str = "v1.0 (as sourced)"

    def live(self) -> list[Rec]:
        return [r for r in self.records if not r.removed]

    def live_elements(self) -> list[El]:
        return [e for e in self.elements if not e.removed]

    def is_stale(self, r: Rec) -> bool:
        return r.flag == "STALE" or (r.as_of is not None and (self.ref_date - r.as_of) > timedelta(days=self.stale_days))

    def sources(self) -> list[str]:
        return sorted({r.source for r in self.records} | {e.source for e in self.elements})


def from_observations(borrower, observations, ref_date: date, stale_days: int) -> Dataset:
    recs: dict[str, Rec] = {}
    els: list[El] = []
    for o in observations:
        if o.kind == "record":
            r = recs.get(o.record_key)
            if r is None:
                r = recs[o.record_key] = Rec(key=o.record_key, source=o.source, zone=o.zone, as_of=o.as_of,
                                             flag=o.provider_flag or "", upload_id=o.upload_id, row=o.row_number)
            r.fields[o.field] = o.value
        else:
            els.append(El(key=o.record_key, source=o.source, element=o.field, value=o.value, dtype=o.data_type,
                          sensitivity=o.sensitivity, category=o.category, label=o.label, upload_id=o.upload_id))
    recs_l = sorted(recs.values(), key=lambda r: (r.source, str(r.as_of or ""), r.key))
    return Dataset(borrower=borrower.name, records=recs_l, elements=els, facility_ids=list(borrower.facility_ids or []),
                   aliases=list(borrower.aliases or []), ref_date=ref_date, stale_days=stale_days)


def apply_changes(ds: Dataset, changes: dict) -> Dataset:
    """Replay a Clean run's changes onto a fresh copy of the dataset."""
    out = copy.deepcopy(ds)
    rm, rm_el = set(changes.get("removed", [])), set(changes.get("removed_elements", []))
    by = {r.key: r for r in out.records}
    for r in out.records:
        if r.key in rm:
            r.removed = True
    for e in out.elements:
        if e.key in rm_el:
            e.removed = True
    for c in changes.get("set", []):
        r = by.get(c["key"])
        if r:
            r.fields[c["field"]] = c["to"]
    for k, s in changes.get("status", {}).items():
        if k in by:
            by[k].status = s
    out.version = "v1.1 (cleaned)"
    return out


def eligible(r: Rec) -> bool:
    """Can this record supply a golden value? Correction clears a wrong/inconsistent flag, never staleness."""
    if r.removed or r.flag == "STALE":
        return False
    return r.status in ("CORRECTED", "RECONCILED") or r.flag not in BAD_FLAGS


def reliability(src: str) -> float:
    return RELIABILITY.get(src, DEFAULT_RELIABILITY)


def golden(ds: Dataset, fields=VALUE_FIELDS) -> dict:
    """Best value per field.

    1. Latest eligible value from the golden source(s) for that field (survivorship rule).
    2. Otherwise the value with the most reliability-weighted support across sources.
    3. Otherwise a value held only in internal data-dictionary elements.
    """
    G: dict[str, dict | None] = {}
    live = [r for r in ds.records if eligible(r)]
    for f in fields:
        cand = [r for r in live if not is_blank(r.fields.get(f)) and typed(f, r.fields.get(f)) is not None]
        pick, why, rule = None, "", ""
        for src in GOLD_PRIORITY.get(f, []):
            c = sorted([r for r in cand if r.source == src], key=lambda r: str(r.as_of or ""), reverse=True)
            if c:
                pick, rule = c[0], "golden-source"
                why = f"{src} is the golden source for {LABEL[f].lower()}; latest eligible record"
                break
        if not pick and cand:
            groups: dict = {}
            for r in cand:
                k = typed(f, r.fields[f])
                k = round(k, 4) if isinstance(k, float) else k
                groups.setdefault(k, []).append(r)
            best = max(groups.values(), key=lambda g: (sum(reliability(r.source) for r in g), max(str(r.as_of or "") for r in g)))
            best.sort(key=lambda r: str(r.as_of or ""), reverse=True)
            pick, rule = best[0], "consensus"
            why = f"No golden-source record; best-supported value ({len(best)} of {len(cand)} records)"
        if pick:
            agree = {r.source for r in cand if not differs(f, r.fields[f], pick.fields[f])}
            G[f] = {"value": pick.fields[f], "display": fmt(f, pick.fields[f]), "source": pick.source, "record": pick.rid,
                    "key": pick.key, "as_of": pick.as_of.isoformat() if pick.as_of else None, "why": why, "rule": rule,
                    "support": sorted(agree), "candidates": len(cand)}
            continue
        els = [e for e in ds.live_elements() if e.canonical == f and not is_blank(e.value) and typed(f, e.value) is not None]
        if els:
            e = els[0]
            G[f] = {"value": e.value, "display": fmt(f, e.value), "source": e.source, "record": e.key.split(":")[1],
                    "key": e.key, "as_of": None, "why": f"Only held in {e.source} (internal)", "rule": "internal-only",
                    "support": sorted({x.source for x in els}), "candidates": len(els)}
        else:
            G[f] = None
    return G


def disagreements(ds: Dataset, G: dict, rec: Rec) -> list[str]:
    return [f for f in VALUE_FIELDS if G.get(f) and G[f]["key"] != rec.key and differs(f, rec.fields.get(f), G[f]["value"])]


def mean(xs):
    v = [x for x in xs if x is not None]
    return sum(v) / len(v) if v else None


def pct(x):
    return None if x is None else round(x * 100)
