"""File storage for uploads. Local disk (a Docker volume); swap for S3/Blob behind the same two functions."""
import hashlib
from pathlib import Path

from .config import get_settings


def root() -> Path:
    p = Path(get_settings().storage_dir) / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def save(data: bytes, filename: str) -> tuple[str, str]:
    sha = hashlib.sha256(data).hexdigest()
    ext = Path(filename).suffix.lower()
    d = root() / sha[:2]
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{sha}{ext}"
    if not path.exists():
        path.write_bytes(data)
    return str(path), sha
