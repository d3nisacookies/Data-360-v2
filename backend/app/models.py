"""Database tables.

Every source value lands in `observations` in a long format (one row per value),
whatever layout the uploaded file had. The engine works on observations only, so
new file layouts need a new mapping, not new engine code.
"""
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="analyst")  # admin | analyst | viewer
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Borrower(Base):
    __tablename__ = "borrowers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    name_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    facility_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(500))
    stored_path: Mapped[str] = mapped_column(String(1000))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    # detected | needs_mapping | ingested | failed
    status: Mapped[str] = mapped_column(String(20), default="detected")
    detected_format: Mapped[str] = mapped_column(String(40), default="unknown")
    # proposal: {sheet, format, columns:[{header, field, confidence, how}], defaults:{source, zone, borrower}}
    mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True)
    borrower_id: Mapped[int] = mapped_column(ForeignKey("borrowers.id", ondelete="CASCADE"), index=True)
    # one record = one row of the source file (wide) or one data element (dictionary)
    record_key: Mapped[str] = mapped_column(String(200), index=True)
    source: Mapped[str] = mapped_column(String(120))
    zone: Mapped[str] = mapped_column(String(40))  # Internal | External | Internal / External
    kind: Mapped[str] = mapped_column(String(20))  # record | element
    field: Mapped[str] = mapped_column(String(200))  # canonical field key, or element name
    label: Mapped[str] = mapped_column(String(300), default="")
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[str] = mapped_column(String(40), default="")
    category: Mapped[str] = mapped_column(String(200), default="")
    sensitivity: Mapped[str] = mapped_column(String(120), default="")
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    provider_flag: Mapped[str] = mapped_column(String(40), default="")
    row_number: Mapped[int] = mapped_column(Integer, default=0)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    borrower_id: Mapped[int] = mapped_column(ForeignKey("borrowers.id", ondelete="CASCADE"), index=True)
    step: Mapped[str] = mapped_column(String(20))  # assess | clean | normalise
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    # max upload id included, so the UI can tell when newer files arrived
    data_version: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    user: Mapped[User | None] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    user_email: Mapped[str] = mapped_column(String(255), default="system")
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(300), default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Setting(Base):
    """Key/value settings, e.g. golden-source priorities, editable by admins later."""
    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120))
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class Workspace(Base):
    """Per-borrower working state for the later steps: the credit memo (step 5), Phase 2 and Phase 3."""
    __tablename__ = "workspaces"
    __table_args__ = (UniqueConstraint("borrower_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    borrower_id: Mapped[int] = mapped_column(ForeignKey("borrowers.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(40))  # memo | p2 | p3
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
