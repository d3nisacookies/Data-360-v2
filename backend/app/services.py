"""Glue between the database and the engine."""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .engine.core import Dataset, apply_changes, from_observations, scoped
from .models import Borrower, Observation, Run, Upload


def ref_date(override: str | None = None) -> date:
    s = override or get_settings().reference_date
    return date.fromisoformat(s) if s else date.today()


def data_version(db: Session, borrower_id: int) -> int:
    return db.scalar(select(func.max(Observation.upload_id)).where(Observation.borrower_id == borrower_id)) or 0


def load_dataset(db: Session, b: Borrower, ref: date | None = None) -> Dataset:
    obs = db.scalars(select(Observation).where(Observation.borrower_id == b.id).order_by(Observation.id)).all()
    return from_observations(b, obs, ref or ref_date(), get_settings().stale_days)


def latest_run(db: Session, borrower_id: int, step: str) -> Run | None:
    return db.scalar(select(Run).where(Run.borrower_id == borrower_id, Run.step == step).order_by(Run.id.desc()).limit(1))


def context(db: Session, b: Borrower) -> dict:
    """Latest Collector and Seeker results (if any) that feed the later steps."""
    out = {}
    for s in ("collect", "seek"):
        r = latest_run(db, b.id, s)
        if r:
            out[s] = r.result
    return out


def scope(db: Session, b: Borrower) -> list[str] | None:
    r = latest_run(db, b.id, "collect")
    return r.result.get("sources") if r else None


def current_dataset(db: Session, b: Borrower, ref: date | None = None, full: bool = False) -> tuple[Dataset, Dataset | None, Run | None]:
    """(as sourced, as cleaned or None, the clean run used), limited to the Collector's scope unless full=True.
    A clean run only applies if no newer files arrived and the scope has not changed since."""
    raw = load_dataset(db, b, ref)
    if not full:
        raw = scoped(raw, scope(db, b))
    cr = latest_run(db, b.id, "clean")
    if cr and cr.data_version == data_version(db, b.id) and not step_status(db, b)["clean"]["stale"]:
        return raw, apply_changes(raw, cr.result["changes"]), cr
    return raw, None, cr


def step_status(db: Session, b: Borrower) -> dict:
    v = data_version(db, b.id)
    out = {}
    for s in ("collect", "seek", "assess", "clean", "normalise"):
        r = latest_run(db, b.id, s)
        out[s] = None if not r else {"run_id": r.id, "at": r.created_at.isoformat(), "stale": r.data_version != v,
                                     "by": r.user.email if r.user else None}
        if out[s] and out[s]["stale"]:
            out[s]["stale_reason"] = "New files were uploaded after this run"
    # a step is out of date when a step it depends on ran after it
    deps = {"clean": ["collect"], "assess": ["collect", "seek", "clean"], "normalise": ["collect", "clean", "assess"]}
    names = {"collect": "The Collector", "seek": "The Seeker", "clean": "Clean", "assess": "Assess"}
    for s, ds in deps.items():
        if not out[s] or out[s]["stale"]:
            continue
        for d in ds:
            if out[d] and out[d]["run_id"] > out[s]["run_id"]:
                out[s]["stale"] = True
                out[s]["stale_reason"] = f"{names[d]} ran after this run"
                break
    return out


def uploads_for(db: Session, borrower_id: int) -> list[Upload]:
    ids = db.scalars(select(Observation.upload_id).where(Observation.borrower_id == borrower_id).distinct()).all()
    return db.scalars(select(Upload).where(Upload.id.in_(ids)).order_by(Upload.id)).all() if ids else []
