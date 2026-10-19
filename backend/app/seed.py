"""Load the sample files through the normal upload path: `python -m app.seed [folder]`."""
import sys
from pathlib import Path

from sqlalchemy import select

from . import audit, storage
from .db import SessionLocal
from .ingest.detect import detect
from .ingest.ingest import ingest
from .main import ensure_admin
from .models import Upload, User

DEFAULT = Path(__file__).resolve().parents[2] / "seed" / "sample-files"


def run(folder: Path) -> None:
    ensure_admin()
    files = sorted(p for p in folder.rglob("*") if p.suffix.lower() in (".xlsx", ".csv") and not p.name.startswith("~$"))
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.role == "admin"))
        for f in files:
            data = f.read_bytes()
            path, sha = storage.save(data, f.name)
            if db.scalar(select(Upload.id).where(Upload.sha256 == sha, Upload.status == "ingested")):
                print(f"skip (already loaded)  {f.name}")
                continue
            u = Upload(filename=f.name, stored_path=path, sha256=sha, size_bytes=len(data), uploaded_by=admin.id)
            db.add(u)
            db.flush()
            p = detect(path, f.name)
            u.detected_format, u.mapping = p["format"], p
            if p["missing"]:
                u.status = "needs_mapping"
                print(f"needs mapping ({', '.join(p['missing'])})  {f.name}")
            else:
                s = ingest(db, u, p)
                print(f"loaded {s['observations']:>5} values  {f.name}")
            audit.log(db, admin, "seed", f.name)
            db.commit()


if __name__ == "__main__":
    run(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT)
