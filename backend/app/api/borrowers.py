from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..engine import assess as A, clean as C, normalise as N, picks as PK, source as SRC
from ..engine.core import apply_changes
from ..engine.export import data_pack
from ..engine.reference import LABEL, VALUE_FIELDS
from ..models import Borrower, Observation, Run, Setting, User
from ..schemas import StepRun
from ..services import context, current_dataset, data_version, latest_run, load_dataset, ref_date, scope, step_status, uploads_for
from ..security import can_edit, current_user

router = APIRouter(prefix="/api", tags=["borrowers"])
STEPS = ("collect", "seek", "assess", "clean", "normalise")


def _b(db, bid) -> Borrower:
    b = db.get(Borrower, bid)
    if not b:
        raise HTTPException(404, "No such borrower")
    return b


def _ref(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise HTTPException(400, "ref_date must be YYYY-MM-DD")


def _run_out(r: Run | None, db: Session, b: Borrower) -> dict | None:
    if not r:
        return None
    st = step_status(db, b).get(r.step) or {}
    return {"id": r.id, "step": r.step, "at": r.created_at.isoformat(), "by": r.user.email if r.user else None,
            "params": r.params, "result": r.result, "stale": st.get("stale", False), "stale_reason": st.get("stale_reason")}


@router.get("/meta")
def meta(_: User = Depends(current_user)):
    return {"assess": A.DIMS, "clean": C.ACTIONS, "normalise": N.ITEMS, "reference_date": ref_date().isoformat(),
            "outputs": {k: v["desc"] for k, v in SRC.OUTPUTS.items()}, "standard_outputs": SRC.STANDARD_OUTPUTS,
            "attributes": {k: v.get("note", "") for k, v in SRC.ATTRS.items()}, "standard_attributes": SRC.STANDARD_ATTRS,
            "pick_sources": SRC.PICK_CATS, "picks": PK.catalogue()}


@router.get("/borrowers")
def borrowers(db: Session = Depends(get_db), _: User = Depends(current_user)):
    counts = dict(db.execute(select(Observation.borrower_id, func.count()).group_by(Observation.borrower_id)).all())
    srcs = dict(db.execute(select(Observation.borrower_id, func.count(func.distinct(Observation.source))).group_by(Observation.borrower_id)).all())
    out = []
    for b in db.scalars(select(Borrower).order_by(Borrower.name)).all():
        a = latest_run(db, b.id, "assess")
        out.append({"id": b.id, "name": b.name, "aliases": b.aliases, "facility_ids": b.facility_ids,
                    "observations": counts.get(b.id, 0), "sources": srcs.get(b.id, 0), "steps": step_status(db, b),
                    "confidence": a.result["overall"] if a else None})
    return out


@router.get("/borrowers/{bid}")
def borrower(bid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    b = _b(db, bid)
    raw, _, _ = current_dataset(db, b, full=True)
    _, cleaned, _ = current_dataset(db, b)
    sc = scope(db, b)
    by = {}
    for r in raw.records:
        s = by.setdefault(r.source, {"source": r.source, "zone": r.zone, "records": 0, "elements": 0, "newest": None, "flags": 0})
        s["records"] += 1
        if r.as_of and (not s["newest"] or r.as_of.isoformat() > s["newest"]):
            s["newest"] = r.as_of.isoformat()
        s["flags"] += 1 if r.flag and r.flag != "VALIDATED" else 0
    for e in raw.elements:
        s = by.setdefault(e.source, {"source": e.source, "zone": "Internal", "records": 0, "elements": 0, "newest": None, "flags": 0})
        s["elements"] += 1
    return {"id": b.id, "name": b.name, "aliases": b.aliases, "facility_ids": b.facility_ids,
            "sources": sorted(by.values(), key=lambda s: (s["zone"] != "Internal", s["source"])),
            "uploads": [{"id": u.id, "filename": u.filename, "at": u.created_at.isoformat()} for u in uploads_for(db, b.id)],
            "steps": step_status(db, b), "version": (cleaned or raw).version, "reference_date": raw.ref_date.isoformat(),
            "scope": sc}


@router.get("/borrowers/{bid}/records")
def records(bid: int, source: str | None = None, cleaned: bool = False, db: Session = Depends(get_db), _: User = Depends(current_user)):
    b = _b(db, bid)
    raw, cl, _ = current_dataset(db, b, full=not cleaned)
    ds = cl if cleaned and cl else raw
    recs = [r for r in ds.records if (not source or r.source == source)]
    els = [e for e in ds.elements if (not source or e.source == source)]
    return {"version": ds.version, "fields": [{"key": f, "label": LABEL[f]} for f in VALUE_FIELDS],
            "records": [{"key": r.key, "id": r.rid, "source": r.source, "zone": r.zone, "as_of": r.as_of.isoformat() if r.as_of else None,
                         "flag": r.flag, "status": r.status, "removed": r.removed, "stale": ds.is_stale(r),
                         "fields": {f: r.fields.get(f) for f in VALUE_FIELDS if r.fields.get(f) is not None}} for r in recs],
            "elements": [{"key": e.key, "source": e.source, "category": e.label, "element": e.element, "type": e.dtype,
                          "value": e.value, "sensitivity": e.sensitivity, "removed": e.removed} for e in els[:2000]],
            "elements_total": len(els)}


@router.get("/borrowers/{bid}/{step}")
def get_step(bid: int, step: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    if step not in STEPS:
        raise HTTPException(404, "Unknown step")
    b = _b(db, bid)
    return _run_out(latest_run(db, b.id, step), db, b)


@router.post("/borrowers/{bid}/{step}")
def run_step(bid: int, step: str, body: StepRun, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    if step not in STEPS:
        raise HTTPException(404, "Unknown step")
    b = _b(db, bid)
    ref = _ref(body.ref_date)
    ctx = context(db, b)
    if step == "collect":
        raw = load_dataset(db, b, ref)
        result = SRC.collect(raw, body.sources, body.outputs)
    elif step == "seek":
        raw = load_dataset(db, b, ref)
        result = SRC.seek(raw, body.attributes, body.requested)
    elif step == "clean":
        raw, _, _ = current_dataset(db, b, ref)
        result = C.clean(raw, body.selected, user=user.email, ctx=ctx, extra=body.extra)
    elif step == "assess":
        raw, cleaned, _ = current_dataset(db, b, ref)
        result = A.assess(raw, cleaned, body.selected, ctx)
        full = load_dataset(db, b, ref)
        owners = (db.scalar(select(Setting).where(Setting.key == "source_owners")) or Setting(value={})).value
        result["crit"] = {n: PK.score_crit(n, cleaned or raw, full, {**ctx, "owners": owners}) for n in dict.fromkeys(body.extra or []) if n in PK.CRIT}
    else:
        raw, cleaned, cr = current_dataset(db, b, ref)
        ar = latest_run(db, b.id, "assess")
        result = N.normalise(cleaned or raw, ar.result if ar else None, cr.result if cr and cleaned else None, body.selected)
        nb = db.scalar(select(func.count()).select_from(Borrower))
        result["picks"] = {n: PK.norm_pick(n, cleaned or raw, result["out"], ar.result if ar else None, nb) for n in dict.fromkeys(body.extra or []) if n in PK.NORM_ACT}
    if not raw.records and not raw.elements:
        raise HTTPException(400, "No data for this borrower yet")
    r = Run(borrower_id=b.id, step=step, params=body.model_dump(), result=result, data_version=data_version(db, b.id), created_by=user.id)
    db.add(r)
    audit.log(db, user, f"run.{step}", b.name, run_selected=result.get("selected"),
              score=result.get("overall", {}).get("score") if step == "assess" else None,
              changes=len(result["log"]) if step == "clean" else None,
              sources=result.get("sources") if step == "collect" else None,
              attributes=len(result["attributes"]) if step == "seek" else None)
    db.commit()
    db.refresh(r)
    return _run_out(r, db, b)


@router.get("/borrowers/{bid}/export/datapack.xlsx")
def datapack(bid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    b = _b(db, bid)
    raw, cleaned, cr = current_dataset(db, b)
    ar = latest_run(db, b.id, "assess")
    blob = data_pack(cleaned or raw, ar.result if ar else None, cr.result if cr and cleaned else None, user.email, context(db, b))
    audit.log(db, user, "export.datapack", b.name, version=(cleaned or raw).version)
    db.commit()
    name = f"Data360 data pack - {b.name} - {(cleaned or raw).version.split()[0]}.xlsx".replace("/", "-")
    return Response(blob, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
