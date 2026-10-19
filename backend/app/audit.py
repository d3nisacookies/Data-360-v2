from sqlalchemy.orm import Session

from .models import AuditEvent, User


def log(db: Session, user: User | None, action: str, target: str = "", **details) -> None:
    """Append an audit event. Callers commit."""
    db.add(AuditEvent(user_id=user.id if user else None, user_email=user.email if user else "system",
                      action=action, target=target, details=details))
