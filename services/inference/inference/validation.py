"""The model only proposes. Items whose evidence is not literally in the original text are dropped."""
from __future__ import annotations

import re

from .schemas import ExtractionPayload, alnum


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


def verify_against_text(payload: ExtractionPayload, text: str) -> tuple[ExtractionPayload, list[str]]:
    dropped: list[str] = []
    norm_text = _norm(text)

    def keep(items, label):
        out = []
        for it in items:
            if _norm(it.evidence) not in norm_text:
                dropped.append(f"{label}:{it.value!r}: evidence not in original text")
            elif alnum(it.value) not in alnum(it.evidence):
                dropped.append(f"{label}:{it.value!r}: value not contained in evidence")
            else:
                out.append(it)
        return out

    clean = ExtractionPayload(
        documents=keep(payload.documents, "document"),
        vouchers=keep(payload.vouchers, "voucher"),
        references=keep(payload.references, "reference"),
        names=keep(payload.names, "name"),
    )
    return clean, dropped
