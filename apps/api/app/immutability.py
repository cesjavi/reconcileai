"""Application-level immutability for audit-grade tables (ORM updates/deletes and bulk statements)."""
from sqlalchemy import event
from sqlalchemy.orm import Session

from .models import AgentRecommendation, AuditEvent, InferenceLog, ReconciliationDecision

IMMUTABLE = (AuditEvent, ReconciliationDecision, InferenceLog, AgentRecommendation)


class ImmutableRecordError(RuntimeError):
    pass


def _forbid(mapper, connection, target):
    raise ImmutableRecordError(f"{type(target).__name__} is append-only")


for _cls in IMMUTABLE:
    event.listen(_cls, "before_update", _forbid)
    event.listen(_cls, "before_delete", _forbid)


@event.listens_for(Session, "do_orm_execute")
def _block_bulk(state):
    if (state.is_update or state.is_delete) and state.bind_mapper is not None:
        if state.bind_mapper.class_ in IMMUTABLE:
            raise ImmutableRecordError(f"{state.bind_mapper.class_.__name__} is append-only")
