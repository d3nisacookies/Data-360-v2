"""Glue between the database and the engine."""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .engine.core import Dataset, apply_changes, from_observations
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


def current_dataset(db: Session, b: Borrower, ref: date | None = None) -> tuple[Dataset, Dataset | None, Run | None]:
    """(as sourced, as cleaned or None, the clean run used). A clean run only applies if no newer files arrived."""
    raw = load_dataset(db, b, ref)
    cr = latest_run(db, b.id, "clean")
    if cr and cr.data_version == data_version(db, b.id):
        return raw, apply_changes(raw, cr.result["changes"]), cr
    return raw, None, cr


def step_status(db: Session, b: Borrower) -> dict:
    v = data_version(db, b.id)
    out = {}
    for s in ("assess", "clean", "normalise"):
        r = latest_run(db, b.id, s)
        out[s] = None if not r else {"run_id": r.id, "at": r.created_at.isoformat(), "stale": r.data_version != v,
                                     "by": r.user.email if r.user else None}
    # Assess is out of date if Clean ran after it
    if out["assess"] and out["clean"] and out["clean"]["run_id"] > out["assess"]["run_id"]:
        out["assess"]["stale"] = True
        out["assess"]["stale_reason"] = "Clean ran after this assessment"
    if out["normalise"] and out["clean"] and out["clean"]["run_id"] > out["normalise"]["run_id"]:
        out["normalise"]["stale"] = True
        out["normalise"]["stale_reason"] = "Clean ran after Normalise"
    return out


def uploads_for(db: Session, borrower_id: int) -> list[Upload]:
    ids = db.scalars(select(Observation.upload_id).where(Observation.borrower_id == borrower_id).distinct()).all()
    return db.scalars(select(Upload).where(Upload.id.in_(ids)).order_by(Upload.id)).all() if ids else []
