"""Folder scan endpoints: see what the scan folder holds and load what Data360 can use."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import audit, scan
from ..db import get_db
from ..models import User
from ..security import can_edit, current_user
from ..workspace import setting_put

router = APIRouter(prefix="/api/scan", tags=["scan"])


@router.get("")
def scan_status(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return {**scan.status(), "last": scan.last(db)}


@router.post("")
def run_scan(db: Session = Depends(get_db), user: User = Depends(can_edit)):
    try:
        rep = scan.run(db, user)
    except FileNotFoundError as e:
        raise HTTPException(409, str(e))
    setting_put(db, "scan.last", rep)
    audit.log(db, user, "scan", rep["root"], found=rep["found"], **rep["counts"])
    db.commit()
    return rep
