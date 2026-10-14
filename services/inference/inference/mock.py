"""MOCK extractor for development and tests. It is regex-based: it is NOT a model and NOT AMD inference."""
from __future__ import annotations

import hashlib
import re
import uuid

from .schemas import DocumentId, Evidenced, ExtractionPayload, ExtractionResult, HealthStatus

MOCK_MODEL = "mock-regex-v1"

_CUIT = re.compile(r"\b\d{2}-?\d{8}-?\d\b")
_DNI = re.compile(r"\bDNI\s*:?\s*(\d{7,8})\b", re.I)
_VOUCHER = re.compile(
    r"\b(?:COMPROBANTE|COMP|FACTURA|FAC|FC|RECIBO|REC)[\s.:]+(?:N[°ºO]?[\s.:]+)?([A-Z0-9][A-Z0-9\-]{3,})", re.I)
_REF = re.compile(r"\b(?:REFERENCIA|REF|OPERACION|OP|NRO)[\s.:]+([A-Z0-9][A-Z0-9\-]{3,})", re.I)
_NAME = re.compile(r"\b(?:DE|CLIENTE|ORDENANTE)\s+([A-ZÁÉÍÓÚÑ]{2,}(?:\s+[A-ZÁÉÍÓÚÑ]{2,}){1,3})\b")


_STOP = {"COMP", "COMPROBANTE", "FC", "FAC", "FACTURA", "REC", "RECIBO", "REF", "OP", "NRO", "CUIT", "DNI"}


def _names(text: str) -> list[Evidenced]:
    out = []
    for m in _NAME.finditer(text):
        words = m.group(1).split()
        while words and words[-1] in _STOP:
            words.pop()
        if len(words) >= 2:
            value = " ".join(words)
            out.append(Evidenced(value=value, evidence=text[m.start():m.start(1)] + value))
    return out


class MockExtractor:
    is_mock = True
    source = "mock"

    def extract(self, text: str) -> ExtractionResult:
        docs = [DocumentId(value=m.group(0), evidence=m.group(0), kind="CUIT") for m in _CUIT.finditer(text)]
        docs += [DocumentId(value=m.group(1), evidence=m.group(0), kind="DNI") for m in _DNI.finditer(text)]
        payload = ExtractionPayload(
            documents=docs[:10],
            vouchers=[Evidenced(value=m.group(1), evidence=m.group(0)) for m in _VOUCHER.finditer(text)][:10],
            references=[Evidenced(value=m.group(1), evidence=m.group(0)) for m in _REF.finditer(text)][:10],
            names=_names(text)[:10],
        )
        return ExtractionResult(
            request_id=str(uuid.uuid4()), source="mock", is_mock=True, model=MOCK_MODEL, status="ok",
            original_text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest(),
            extraction=payload, latency_ms=0.0, attempts=0,
        )

    def health(self) -> HealthStatus:
        return HealthStatus(status="ok", source="mock", is_mock=True, model=MOCK_MODEL,
                            detail="MOCK provider: no remote inference, not AMD hardware")
