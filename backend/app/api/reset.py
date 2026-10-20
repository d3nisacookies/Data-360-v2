"""Start again: clear step results and later-phase work for one client or for every client.
Uploaded files are kept unless asked; users and the audit log are never touched."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import audit
from .. import workspace as W
from ..db import get_db
from ..models import Borrower, Observation, Run, Setting, Upload, User, Workspace
from ..security import is_admin

router = APIRouter(prefix="/api", tags=["reset"])


class ResetIn(BaseModel):
    uploads: bool = False     # all clients only: also delete uploaded files and the data read from them
    settings: bool = False    # all clients only: also reset rules & policies, source owners and assistant switches


def _clear_client(db: Session, bid: int) -> dict:
    runs = db.execute(delete(Run).where(Run.borrower_id == bid)).rowcount
    ws = db.execute(delete(Workspace).where(Workspace.borrower_id == bid)).rowcount
    return {"runs": runs, "workspaces": ws}


@router.post("/borrowers/{bid}/reset")
def reset_client(bid: int, db: Session = Depends(get_db), user: User = Depends(is_admin)):
    b = db.get(Borrower, bid)
    if not b:
        raise HTTPException(404, "No such borrower")
    out = _clear_client(db, bid)
    ai = W.setting_get(db, "ai_clients", {})
    if ai.pop(str(bid), None) is not None:
        W.setting_put(db, "ai_clients", ai)
    audit.log(db, user, "reset.client", b.name, **out)
    db.commit()
    return out


@router.post("/reset")
def reset_all(body: ResetIn, db: Session = Depends(get_db), user: User = Depends(is_admin)):
    out = {"runs": db.execute(delete(Run)).rowcount, "workspaces": db.execute(delete(Workspace)).rowcount}
    if body.settings:
        out["settings"] = db.execute(delete(Setting)).rowcount
    else:
        W.setting_put(db, "ai_clients", {})
    if body.uploads:
        paths = [p for p in db.scalars(select(Upload.stored_path)).all() if p]
        db.execute(delete(Observation))
        out["uploads"] = db.execute(delete(Upload)).rowcount
        out["borrowers"] = db.execute(delete(Borrower)).rowcount
        for p in paths:
            try:
                os.remove(p)
            except OSError:
                pass
    audit.log(db, user, "reset.all", "", **out)
    db.commit()
    return out
