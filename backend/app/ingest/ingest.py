"""Turn an uploaded file plus a confirmed mapping into observations."""
from datetime import datetime, timezone

from rapidfuzz import fuzz
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..engine.reference import name_key
from ..engine.values import is_blank, parse_date
from ..models import Borrower, Observation, Upload
from .tabular import read_tables


class MappingError(ValueError):
    pass


def resolve_borrower(db: Session, name: str, facility_id: str | None = None, cache: dict | None = None) -> Borrower:
    """Find the borrower a name refers to (ignoring case, punctuation and legal suffixes), or create it."""
    key = name_key(name)
    if cache is not None and key in cache:
        b = cache[key]
    else:
        b = db.scalar(select(Borrower).where(Borrower.name_key == key))
        if not b:
            all_b = db.scalars(select(Borrower)).all()
            scored = sorted(((fuzz.token_sort_ratio(key, x.name_key), x) for x in all_b), key=lambda s: -s[0])
            if scored and scored[0][0] >= 92:
                b = scored[0][1]
            elif facility_id:
                b = next((x for x in all_b if facility_id in (x.facility_ids or [])), None)
        if not b:
            b = Borrower(name=str(name).strip(), name_key=key, aliases=[], facility_ids=[])
            db.add(b)
            db.flush()
        if cache is not None:
            cache[key] = b
    raw = str(name).strip()
    if raw != b.name and raw not in (b.aliases or []):
        b.aliases = [*(b.aliases or []), raw]
    if facility_id and facility_id not in (b.facility_ids or []):
        b.facility_ids = [*(b.facility_ids or []), facility_id]
    return b


def _s(v) -> str | None:
    if is_blank(v):
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, datetime):
        return v.date().isoformat()
    return str(v).strip()


def ingest(db: Session, up: Upload, mapping: dict) -> dict:
    """Replace this upload's observations with ones built from `mapping`. Returns a summary."""
    tables = read_tables(up.stored_path)
    t = next((x for x in tables if x.sheet == mapping.get("sheet")), None)
    if not t:
        raise MappingError(f"Sheet {mapping.get('sheet')!r} not found in the file")
    d = mapping.get("defaults", {})
    db.execute(delete(Observation).where(Observation.upload_id == up.id))
    cache: dict = {}
    obs: list[Observation] = []
    borrowers: dict[int, str] = {}
    skipped = 0

    if mapping["format"] == "dictionary":
        role = {c["role"]: i for i, c in enumerate(mapping["columns"]) if c.get("role")}
        if "element" not in role or "value" not in role:
            raise MappingError("Map the data element and value columns")
        if "borrower" not in role and not d.get("borrower"):
            raise MappingError("Choose which borrower this file is for")
        if "source" not in role and not d.get("source"):
            raise MappingError("Name the source system this file comes from")
        get = lambda r, k: _s(r[role[k]]) if k in role and role[k] < len(r) else None
        for n, r in enumerate(t.rows):
            el = get(r, "element")
            if not el:
                continue  # record separators like "Record 1"
            bname = get(r, "borrower") or d.get("borrower")
            if not bname:
                skipped += 1
                continue
            b = resolve_borrower(db, bname, None, cache)
            borrowers[b.id] = b.name
            src = get(r, "source") or d.get("source")
            deid = get(r, "id") or f"row{t.first_data_row + n}"
            obs.append(Observation(upload_id=up.id, borrower_id=b.id, record_key=f"u{up.id}:{deid}:{t.first_data_row + n}",
                                   source=src, zone=d.get("zone") or "Internal", kind="element", field=el,
                                   label=" / ".join(x for x in (get(r, "category"), get(r, "subcategory")) if x),
                                   value=get(r, "value"), data_type=get(r, "dtype") or "", category=get(r, "category") or "",
                                   sensitivity=get(r, "sensitivity") or "", row_number=t.first_data_row + n))
    else:
        cols = [(i, c["field"] or ("x:" + c["header"])) for i, c in enumerate(mapping["columns"]) if c.get("header") and c.get("include", True)]
        fidx = {f: i for i, f in cols}
        if "Borrower_Name" not in fidx and not d.get("borrower"):
            raise MappingError("Map a borrower column or choose the borrower")
        if "External_Source" not in fidx and not d.get("source"):
            raise MappingError("Map a source column or name the source")
        get = lambda r, f: _s(r[fidx[f]]) if f in fidx and fidx[f] < len(r) else None
        for n, r in enumerate(t.rows):
            rown = t.first_data_row + n
            bname = get(r, "Borrower_Name") or d.get("borrower")
            if not bname:
                skipped += 1
                continue
            fac = get(r, "Facility_ID")
            b = resolve_borrower(db, bname, fac, cache)
            borrowers[b.id] = b.name
            src = get(r, "External_Source") or d.get("source")
            zone = get(r, "Source_Zone") or d.get("zone") or "External"
            as_of = parse_date(get(r, "As_of_Date"))
            flag = (get(r, "Data_Quality_Status") or "").upper()
            rid = get(r, "Record_ID") or f"{src}-{rown}"
            key = f"u{up.id}:{rid}"
            for i, f in cols:
                v = _s(r[i]) if i < len(r) else None
                if v is None:
                    continue
                obs.append(Observation(upload_id=up.id, borrower_id=b.id, record_key=key, source=src, zone=zone, kind="record",
                                       field=f, label=mapping["columns"][i]["header"], value=v, as_of=as_of,
                                       provider_flag=flag, row_number=rown))
    db.add_all(obs)
    up.status = "ingested"
    up.ingested_at = datetime.now(timezone.utc)
    up.mapping = mapping
    up.summary = {"observations": len(obs), "records": len({o.record_key for o in obs}), "skipped_rows": skipped,
                  "borrowers": [{"id": k, "name": v} for k, v in borrowers.items()],
                  "sources": sorted({o.source for o in obs})}
    up.error = ""
    return up.summary
