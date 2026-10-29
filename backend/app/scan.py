"""Folder scan: find the files Data360 can use in one folder tree and load them.

Read-only by design. The folder is mounted read-only in Docker, and this code only lists and reads files.
Every file found gets an outcome:
  loaded          spreadsheet or CSV ingested (same path as a browser upload)
  duplicate       the same bytes were already loaded (from an upload, an earlier scan or another path)
  not_recognised  a spreadsheet or CSV whose layout or borrower could not be worked out (not loaded;
                  upload it by hand to map it)
  not_read_yet    a document type the scanner finds but cannot read yet (PDF, Word, email, text): the
                  AI Collector in the next step reads these
  failed          could not be opened, or too large
Hidden folders, system folders, Office lock files and other file types are skipped and only counted.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from .config import get_settings
from .models import Upload, User

TABULAR = {".xlsx", ".xlsm", ".csv"}
DOCUMENTS = {".pdf", ".docx", ".doc", ".eml", ".msg", ".txt", ".pptx", ".rtf", ".md"}
SKIP_DIRS = {"node_modules", "__pycache__", "venv", ".venv", "appdata", "$recycle.bin", "system volume information",
             "windows", "program files", "program files (x86)", "programdata"}
KIND = {**{e: "spreadsheet" for e in (".xlsx", ".xlsm")}, ".csv": "csv", ".pdf": "pdf", ".docx": "word", ".doc": "word",
        ".eml": "email", ".msg": "email", ".txt": "text", ".md": "text", ".rtf": "text", ".pptx": "slides"}


def root() -> Path:
    return Path(get_settings().scan_root)


def status() -> dict:
    r = root()
    ok = r.is_dir()
    return {"root": str(r), "available": ok and os.access(r, os.R_OK),
            "readonly": ok and not os.access(r, os.W_OK),
            "note": "" if ok else "No folder mounted. Set SCAN_HOST_DIR in .env to the folder to scan and restart."}


def _walk(base: Path, limit: int):
    """Yield (path, skipped_reason) for every file under base, pruning hidden and system folders."""
    n = 0
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d.lower() not in SKIP_DIRS)
        for f in sorted(filenames):
            p = Path(dirpath) / f
            if f.startswith(".") or f.startswith("~$") or p.is_symlink():
                yield p, "hidden, lock or link file"
                continue
            n += 1
            if n > limit:
                yield p, "limit"
                return
            yield p, ""


def run(db: Session, user: User) -> dict:
    from .api.uploads import store_and_ingest   # late import: the API module imports this one's callers

    s = get_settings()
    base = root()
    st = status()
    if not st["available"]:
        raise FileNotFoundError(st["note"] or f"Cannot read {base}")
    t0 = time.monotonic()
    files, skipped, seen = [], {"hidden or lock files": 0, "other file types": 0}, set()
    truncated = False
    # spreadsheets before CSVs: full exports carry the proper legal names, so borrowers are created
    # under those rather than a vendor's short form ("HarbourVest Inc.")
    walked = sorted(_walk(base, s.scan_max_files), key=lambda pw: (pw[1] == "limit", pw[0].suffix.lower() == ".csv"))
    for p, why in walked:
        if why == "limit":
            truncated = True
            break
        if why:
            skipped["hidden or lock files"] += 1
            continue
        ext = p.suffix.lower()
        if ext not in TABULAR and ext not in DOCUMENTS:
            skipped["other file types"] += 1
            continue
        rel = p.relative_to(base).as_posix()
        try:
            stt = p.stat()
        except OSError as e:
            files.append({"path": rel, "kind": KIND.get(ext, ext), "outcome": "failed", "note": f"Cannot read: {e.strerror}"})
            continue
        row = {"path": rel, "kind": KIND.get(ext, ext), "size": stt.st_size,
               "modified": datetime.fromtimestamp(stt.st_mtime, timezone.utc).date().isoformat()}
        if ext in DOCUMENTS:
            files.append({**row, "outcome": "not_read_yet", "note": "Found; the AI Collector will read this type"})
            continue
        if stt.st_size > s.max_upload_mb * 1024 * 1024:
            files.append({**row, "outcome": "failed", "note": f"Larger than {s.max_upload_mb} MB"})
            continue
        try:
            data = p.read_bytes()
        except OSError as e:
            files.append({**row, "outcome": "failed", "note": f"Cannot read: {e.strerror}"})
            continue
        r = store_and_ingest(db, user, p.name, data, origin=rel)
        if r.get("duplicate"):
            first = r.get("source_path") or r.get("filename")
            files.append({**row, "outcome": "duplicate", "upload_id": r["id"], "note": f"Same file as {first}",
                          "borrowers": [b["name"] for b in (r.get("summary") or {}).get("borrowers", [])]})
        elif r.get("status") == "ingested":
            sm = r.get("summary") or {}
            files.append({**row, "outcome": "loaded", "upload_id": r["id"], "borrowers": [b["name"] for b in sm.get("borrowers", [])],
                          "sources": sm.get("sources", []), "values": sm.get("observations", 0), "format": r.get("format")})
            seen.add(r["id"])
        else:
            # not confident enough to load: drop the stored row so scans do not pile up half-mapped files
            if r.get("id"):
                u = db.get(Upload, r["id"])
                if u is not None and u.status != "ingested":
                    db.delete(u)
                    db.commit()
            files.append({**row, "outcome": "not_recognised" if r.get("status") == "needs_mapping" or r.get("format") == "unknown" else "failed",
                          "note": r.get("error") or "Layout or borrower not recognised"})
    files.sort(key=lambda f: f["path"].lower())
    counts = {k: sum(1 for f in files if f["outcome"] == k) for k in ("loaded", "duplicate", "not_recognised", "not_read_yet", "failed")}
    borrowers = sorted({b for f in files if f["outcome"] in ("loaded", "duplicate") for b in f.get("borrowers", [])})
    return {"root": str(base), "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "by": user.email,
            "seconds": round(time.monotonic() - t0, 1), "found": len(files), "counts": counts, "skipped": skipped,
            "truncated": truncated, "borrowers": borrowers, "files": files}


def last(db: Session) -> dict | None:
    from .workspace import setting_get
    return setting_get(db, "scan.last", None)

