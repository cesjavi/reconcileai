"""CSV import: schema validation, Decimal amounts, normalised dates/documents/vouchers, de-duplication.

Imports are all-or-nothing: one invalid row rejects the whole file, so a batch is never half loaded.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from reconciliation import norm_ref
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit
from .models import BankTransaction, ReconciliationBatch, SystemDeposit

REQUIRED = {"id", "date", "amount"}
OPTIONAL = {"description", "document", "voucher"}
MAX_BYTES = 5_000_000
MAX_ROWS = 50_000
_CUIT_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


class ImportError_(Exception):
    def __init__(self, message: str, errors: list[dict] | None = None, status: int = 422):
        super().__init__(message)
        self.message, self.errors, self.status = message, errors or [], status


def parse_amount(raw: str) -> Decimal:
    s = raw.strip().replace(" ", "")
    if "," in s and "." in s:  # 1.234,56 (es-AR) or 1,234.56
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation as exc:
        raise ValueError("invalid amount") from exc
    if not d.is_finite():
        raise ValueError("invalid amount")
    if abs(d) >= Decimal("1e12"):
        raise ValueError("amount out of range")
    q = d.quantize(Decimal("0.01"))
    if q != d:
        raise ValueError("more than 2 decimals")
    return q


def parse_date(raw: str) -> date:
    s = raw.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError("invalid date (use YYYY-MM-DD or DD/MM/YYYY)")


def cuit_is_valid(d: str) -> bool:
    if len(d) != 11:
        return False
    check = 11 - sum(int(c) * w for c, w in zip(d[:10], _CUIT_WEIGHTS)) % 11
    check = {11: 0}.get(check, check)
    return check != 10 and check == int(d[10])


def parse_document(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if len(digits) in (7, 8):
        return digits  # DNI
    if len(digits) == 11 and cuit_is_valid(digits):
        return digits
    raise ValueError("invalid CUIT/DNI")


@dataclass
class Row:
    external_id: str
    date: date
    amount: Decimal
    description: str
    document: str
    voucher: str
    row_hash: str


@dataclass
class ParsedFile:
    rows: list[Row] = field(default_factory=list)
    duplicates_in_file: int = 0


def row_hash(r: dict) -> str:
    key = "|".join([str(r["date"]), str(r["amount"]), r["document"], r["voucher"], r["description"]])
    return hashlib.sha256(key.encode()).hexdigest()


def parse_csv(raw: bytes) -> ParsedFile:
    if len(raw) > MAX_BYTES:
        raise ImportError_("file too large", status=413)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportError_("file must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text))
    cols = set(reader.fieldnames or [])
    if REQUIRED - cols:
        raise ImportError_(f"missing columns: {sorted(REQUIRED - cols)}")
    if cols - REQUIRED - OPTIONAL:
        raise ImportError_(f"unknown columns: {sorted(cols - REQUIRED - OPTIONAL)}")
    out, errors, seen = ParsedFile(), [], {}
    for line, r in enumerate(reader, start=2):
        if len(seen) + out.duplicates_in_file >= MAX_ROWS:
            raise ImportError_("too many rows", status=413)
        try:
            ext = (r.get("id") or "").strip()
            if not ext or len(ext) > 64:
                raise ValueError("id required (max 64 chars)")
            vals = {
                "date": parse_date(r["date"] or ""), "amount": parse_amount(r["amount"] or ""),
                "description": " ".join((r.get("description") or "").split())[:255],
                "document": parse_document(r.get("document") or ""),
                "voucher": norm_ref(r.get("voucher") or "")[:40],
            }
        except (ValueError, TypeError) as exc:
            errors.append({"line": line, "error": str(exc)})
            continue
        h = row_hash(vals)
        if ext in seen:
            if seen[ext] == h:
                out.duplicates_in_file += 1
            else:
                errors.append({"line": line, "error": f"id {ext!r} repeated with different content"})
            continue
        seen[ext] = h
        out.rows.append(Row(ext, vals["date"], vals["amount"], vals["description"], vals["document"],
                            vals["voucher"], h))
    if errors:
        raise ImportError_(f"{len(errors)} invalid row(s); nothing was imported", errors[:50])
    if not out.rows:
        raise ImportError_("file has no data rows")
    return out


def import_file(db: Session, kind: str, filename: str, raw: bytes, actor: str) -> dict:
    """kind: BANK | DEPOSIT. Idempotent: the same file (hash) twice returns the first batch untouched."""
    file_hash = hashlib.sha256(raw).hexdigest()
    existing = db.scalars(select(ReconciliationBatch).where(
        ReconciliationBatch.kind == kind, ReconciliationBatch.file_hash == file_hash)).first()
    if existing:
        return {"batch_id": existing.id, "duplicate_file": True, **existing.stats}

    parsed = parse_csv(raw)
    model = BankTransaction if kind == "BANK" else SystemDeposit
    datecol = "tx_date" if kind == "BANK" else "deposit_date"
    known = dict(db.execute(select(model.external_id, model.row_hash).where(
        model.external_id.in_([r.external_id for r in parsed.rows]))).all())
    conflicts = [{"id": r.external_id, "error": "id already imported with different content"}
                 for r in parsed.rows if r.external_id in known and known[r.external_id] != r.row_hash]
    if conflicts:
        raise ImportError_("id conflicts with previously imported data; nothing was imported", conflicts[:50], 409)

    batch = ReconciliationBatch(kind=kind, filename=filename[:255], file_hash=file_hash, created_by=actor)
    db.add(batch)
    db.flush()
    new = [r for r in parsed.rows if r.external_id not in known]
    for r in new:
        db.add(model(batch_id=batch.id, external_id=r.external_id, description=r.description,
                     amount=r.amount, document=r.document, voucher=r.voucher, row_hash=r.row_hash,
                     **{datecol: r.date}))
    batch.stats = {"rows": len(parsed.rows), "imported": len(new),
                   "skipped_existing": len(parsed.rows) - len(new), "duplicates_in_file": parsed.duplicates_in_file}
    audit.record(db, actor, f"import_{kind.lower()}", "batch", batch.id, {**batch.stats, "file_hash": file_hash})
    db.flush()
    return {"batch_id": batch.id, "duplicate_file": False, **batch.stats}
