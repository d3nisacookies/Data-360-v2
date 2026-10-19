from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..models import AuditEvent, User
from ..schemas import TokenOut, UserCreate, UserOut, UserPatch
from ..security import ROLES, current_user, hash_password, is_admin, make_token, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == form.username.strip().lower()))
    if not u or not u.active or not verify_password(form.password, u.password_hash):
        raise HTTPException(401, "Wrong email or password")
    audit.log(db, u, "login")
    db.commit()
    return TokenOut(access_token=make_token(u), user=UserOut.model_validate(u))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.get("/users", response_model=list[UserOut])
def users(db: Session = Depends(get_db), _: User = Depends(is_admin)):
    return db.scalars(select(User).order_by(User.id)).all()


@router.post("/users", response_model=UserOut)
def create_user(body: UserCreate, db: Session = Depends(get_db), admin: User = Depends(is_admin)):
    if body.role not in ROLES:
        raise HTTPException(400, f"Role must be one of {', '.join(ROLES)}")
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "A user with that email exists")
    u = User(email=email, name=body.name, role=body.role, password_hash=hash_password(body.password))
    db.add(u)
    audit.log(db, admin, "user.create", email, role=body.role)
    db.commit()
    return u


@router.patch("/users/{uid}", response_model=UserOut)
def patch_user(uid: int, body: UserPatch, db: Session = Depends(get_db), admin: User = Depends(is_admin)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "No such user")
    if body.role is not None:
        if body.role not in ROLES:
            raise HTTPException(400, "Unknown role")
        u.role = body.role
    if body.name is not None:
        u.name = body.name
    if body.active is not None:
        if u.id == admin.id and not body.active:
            raise HTTPException(400, "You cannot deactivate yourself")
        u.active = body.active
    if body.password:
        u.password_hash = hash_password(body.password)
    audit.log(db, admin, "user.update", u.email, **body.model_dump(exclude={"password"}, exclude_none=True))
    db.commit()
    return u


@router.get("/audit")
def audit_events(limit: int = 200, db: Session = Depends(get_db), _: User = Depends(is_admin)):
    ev = db.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(min(limit, 1000))).all()
    return [{"id": e.id, "at": e.at.isoformat(), "user": e.user_email, "action": e.action, "target": e.target, "details": e.details} for e in ev]
