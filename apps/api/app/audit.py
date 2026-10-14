import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import immutability  # noqa: F401  (registers listeners)
from .models import AuditEvent


def _digest(prev: str, seq: int, actor: str, action: str, entity: str, entity_id: int | None, payload: dict) -> str:
    body = json.dumps([prev, seq, actor, action, entity, entity_id, payload], sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def record(db: Session, actor: str, action: str, entity: str, entity_id: int | None = None,
           payload: dict | None = None) -> AuditEvent:
    """Written in the caller's transaction: the audit row commits or rolls back with the change it describes."""
    payload = json.loads(json.dumps(payload or {}, default=str))
    last = db.scalars(select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(1)).first()
    prev, seq = (last.hash, last.seq + 1) if last else ("", 1)
    row = AuditEvent(seq=seq, actor=actor, action=action, entity=entity, entity_id=entity_id, payload=payload,
                     prev_hash=prev, hash=_digest(prev, seq, actor, action, entity, entity_id, payload))
    db.add(row)
    db.flush()  # unique(seq) rejects a concurrent writer that picked the same seq
    return row


def verify_chain(db: Session) -> dict:
    prev, count = "", 0
    for row in db.scalars(select(AuditEvent).order_by(AuditEvent.seq)):
        expected = _digest(prev, row.seq, row.actor, row.action, row.entity, row.entity_id, row.payload)
        if row.prev_hash != prev or row.hash != expected or row.seq != count + 1:
            return {"valid": False, "broken_at": row.id, "checked": count}
        prev, count = row.hash, count + 1
    return {"valid": True, "broken_at": None, "checked": count}
