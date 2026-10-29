from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import audit, storage
from ..config import get_settings
from ..db import get_db
from ..engine.reference import FIELDS
from ..ingest.detect import detect, propose_for_sheet
from ..ingest.ingest import MappingError, ingest
from ..ingest.tabular import read_tables
from ..models import Borrower, Observation, Upload, User
from ..schemas import MappingIn, SheetPick
from ..security import can_edit, current_user

router = APIRouter(prefix="/api", tags=["uploads"])
ALLOWED = {".xlsx", ".xlsm", ".csv"}


def out(u: Upload, preview: bool = False) -> dict:
    d = {"id": u.id, "filename": u.filename, "status": u.status, "format": u.detected_format, "size": u.size_bytes,
         "created_at": u.created_at.isoformat(), "ingested_at": u.ingested_at.isoformat() if u.ingested_at else None,
         "summary": u.summary, "error": u.error, "mapping": u.mapping, "source_path": u.source_path}
    if preview and u.mapping.get("sheet"):
        try:
            t = next((x for x in read_tables(u.stored_path) if x.sheet == u.mapping["sheet"]), None)
            d["preview"] = {"headers": t.headers, "rows": [[None if c is None else str(c) for c in r] for r in t.rows[:8]]} if t else None
        except Exception as e:  # pragma: no cover - unreadable file
            d["preview"] = None
            d["error"] = str(e)
    return d


@router.get("/fields")
def fields(_: User = Depends(current_user)):
    return [{"key": k, "label": v[0], "type": v[1], "critical": v[2], "section": v[3], "synonyms": v[4]} for k, v in FIELDS.items()]


@router.get("/uploads")
def list_uploads(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [out(u) for u in db.scalars(select(Upload).order_by(Upload.id.desc())).all()]


@router.get("/uploads/{uid}")
def get_upload(uid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    u = db.get(Upload, uid)
    if not u:
        raise HTTPException(404, "No such upload")
    return out(u, preview=True)


def store_and_ingest(db: Session, user: User, name: str, data: bytes, borrower: str = "", source: str = "",
                     review: bool = False, origin: str | None = None) -> dict:
    """Store one file, detect its layout and ingest it if it maps cleanly. Used by uploads and the folder scan.

    Returns the upload as a dict; `duplicate: True` when the same bytes were already ingested.
    """
    if Path(name).suffix.lower() not in ALLOWED:
        return {"filename": name, "status": "failed", "error": "Only .xlsx, .xlsm and .csv files are supported"}
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        return {"filename": name, "status": "failed", "error": f"Larger than {get_settings().max_upload_mb} MB"}
    path, sha = storage.save(data, name)
    dup = db.scalar(select(Upload).where(Upload.sha256 == sha, Upload.status == "ingested"))
    if dup:
        return {**out(dup), "duplicate": True}
    u = Upload(filename=name, stored_path=path, sha256=sha, size_bytes=len(data), uploaded_by=user.id, source_path=origin)
    db.add(u)
    db.flush()
    try:
        p = detect(path, name)
    except Exception as e:
        u.status, u.error = "failed", f"Could not read the file: {e}"
        audit.log(db, user, "upload.failed", name, error=u.error)
        db.commit()
        return out(u)
    if borrower and "borrower" in p.get("missing", []):
        p["defaults"]["borrower"] = borrower
        p["missing"].remove("borrower")
    if source and "source" in p.get("missing", []):
        p["defaults"]["source"] = source
        p["missing"].remove("source")
    u.detected_format, u.mapping = p["format"], p
    audit.log(db, user, "upload", name, sha256=sha, format=p["format"], sheet=p.get("sheet"), **({"path": origin} if origin else {}))
    if p["format"] != "unknown" and not p["missing"] and not p.get("uncertain") and not review:
        try:
            ingest(db, u, p)
            audit.log(db, user, "ingest", name, **{k: v for k, v in u.summary.items() if k != "borrowers"})
        except MappingError as e:
            u.status, u.error = "needs_mapping", str(e)
    else:
        u.status = "needs_mapping" if p["format"] != "unknown" else "failed"
        u.error = p.get("error", "")
    db.commit()
    return out(u)


@router.post("/uploads")
async def upload(files: list[UploadFile] = File(...), borrower: str = Form(""), source: str = Form(""),
                 review: bool = Form(False), db: Session = Depends(get_db), user: User = Depends(can_edit)):
    """Store files, detect their layout and ingest the ones that map cleanly.

    Files that need a decision (borrower, source, uncertain columns) wait in `needs_mapping`.
    """
    return [store_and_ingest(db, user, Path(f.filename or "upload").name, await f.read(), borrower, source, review) for f in files]


@router.post("/uploads/{uid}/sheet")
def pick_sheet(uid: int, body: SheetPick, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    u = db.get(Upload, uid)
    if not u:
        raise HTTPException(404, "No such upload")
    try:
        u.mapping = propose_for_sheet(u.stored_path, u.filename, body.sheet)
    except ValueError as e:
        raise HTTPException(400, str(e))
    u.detected_format = u.mapping["format"]
    db.commit()
    return out(u, preview=True)


@router.post("/uploads/{uid}/ingest")
def confirm(uid: int, body: MappingIn, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    u = db.get(Upload, uid)
    if not u:
        raise HTTPException(404, "No such upload")
    m = body.mapping
    if m.get("format") not in ("records", "dictionary"):
        raise HTTPException(400, "Unknown format")
    try:
        ingest(db, u, m)
    except MappingError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    audit.log(db, user, "ingest", u.filename, manual=True, **{k: v for k, v in u.summary.items() if k != "borrowers"})
    db.commit()
    return out(u)


@router.delete("/uploads/{uid}")
def remove(uid: int, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    u = db.get(Upload, uid)
    if not u:
        raise HTTPException(404, "No such upload")
    db.execute(delete(Observation).where(Observation.upload_id == uid))
    audit.log(db, user, "upload.delete", u.filename)
    db.delete(u)
    db.flush()
    # drop borrowers that no longer have any data
    for b in db.scalars(select(Borrower)).all():
        if not db.scalar(select(Observation.id).where(Observation.borrower_id == b.id).limit(1)):
            db.delete(b)
    db.commit()
    return {"ok": True}
