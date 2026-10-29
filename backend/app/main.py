from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from .api import assistant, auth, borrowers, reset, scan, uploads, workspace
from .config import get_settings
from .db import SessionLocal, engine
from .models import User
from .security import hash_password


def ensure_admin() -> None:
    s = get_settings()
    with SessionLocal() as db:
        if not db.scalar(select(User.id).limit(1)):
            db.add(User(email=s.admin_email.lower(), name="Administrator", role="admin", password_hash=hash_password(s.admin_password)))
            db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.environment == "production" and s.jwt_secret == "change-me-in-production":
        raise RuntimeError("Set JWT_SECRET to a long random value before running in production")
    ensure_admin()
    yield


app = FastAPI(title="Data360 API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router)
app.include_router(uploads.router)
app.include_router(scan.router)
app.include_router(assistant.router)
app.include_router(reset.router)
app.include_router(workspace.router)  # before borrowers: its /borrowers/{id}/{step} would match first
app.include_router(borrowers.router)


@app.get("/api/health")
def health():
    with engine.connect() as c:
        c.execute(text("select 1"))
    return {"ok": True, "app": get_settings().app_name}
