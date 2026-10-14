from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Evidenced(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(min_length=1, max_length=64)
    evidence: str = Field(min_length=1, max_length=255)  # verbatim snippet of the original text


class DocumentId(Evidenced):
    kind: Literal["CUIT", "DNI", "UNKNOWN"] = "UNKNOWN"


class ExtractionPayload(BaseModel):
    """What the model is allowed to return. Anything else is rejected."""

    model_config = ConfigDict(extra="forbid")
    documents: list[DocumentId] = Field(default_factory=list, max_length=10)
    vouchers: list[Evidenced] = Field(default_factory=list, max_length=10)
    references: list[Evidenced] = Field(default_factory=list, max_length=10)
    names: list[Evidenced] = Field(default_factory=list, max_length=10)


def alnum(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


class ExtractionResult(BaseModel):
    request_id: str
    source: Literal["mock", "vllm"]
    is_mock: bool
    model: str
    hardware_label: str = ""
    status: Literal["ok", "invalid_output", "error"]
    original_text: str  # kept as evidence
    text_sha256: str
    extraction: ExtractionPayload = Field(default_factory=ExtractionPayload)
    dropped: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    attempts: int = 0
    error: str | None = None
    raw_output: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def candidate_refs(self) -> list[str]:
        """Raw proposals (documents, vouchers, references). The deterministic engine must still verify them."""
        e = self.extraction
        vals = [d.value for d in e.documents] + [v.value for v in e.vouchers] + [r.value for r in e.references]
        return list(dict.fromkeys(vals))


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded", "down"]
    source: Literal["mock", "vllm"]
    is_mock: bool
    model: str
    model_listed: bool | None = None
    latency_ms: float | None = None
    hardware_label: str = ""
    detail: str = ""
