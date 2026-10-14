from decimal import Decimal

import pytest

from app.importing import cuit_is_valid, parse_amount, parse_date, parse_document
from conftest import H, csv_bytes, upload

VALID_CUIT = "20123456786"  # check digit computed with the AFIP mod-11 algorithm


def test_parsers_normalise():
    assert parse_amount("1.234,56") == Decimal("1234.56")
    assert parse_amount("1,234.56") == Decimal("1234.56")
    assert parse_amount("-10,5") == Decimal("-10.50")
    assert str(parse_date("03/04/2025")) == "2025-04-03"
    assert parse_document("20-12345678-6") == VALID_CUIT
    assert parse_document("12.345.678") == "12345678"
    assert parse_document("") == ""
    assert cuit_is_valid(VALID_CUIT)


@pytest.mark.parametrize("bad", ["abc", "1.234", "NaN", "Infinity", "1e999", ""])
def test_bad_amounts_rejected(bad):
    with pytest.raises(ValueError):
        parse_amount(bad)


@pytest.mark.parametrize("bad", ["20123456787", "123", "20-123-4"])
def test_bad_documents_rejected(bad):
    with pytest.raises(ValueError):
        parse_document(bad)


def test_import_ok_and_normalised_storage(client):
    r = upload(client, "bank", csv_bytes(f"B1,03/04/2025,\"1.234,56\",Pago FC  A-1,20-12345678-6,fc a-0001-000123"))
    assert r.status_code == 200 and r.json()["imported"] == 1
    b = client.get("/bank-transactions").json()[0]
    assert (b["date"], b["amount"], b["document"], b["voucher"]) == ("2025-04-03", "1234.56", VALID_CUIT, "FCA0001000123")
    assert b["description"] == "Pago FC A-1"


def test_schema_validation(client):
    assert upload(client, "bank", b"id,date\n1,2025-01-01\n").status_code == 422
    assert upload(client, "bank", b"id,date,amount,secret\n1,2025-01-01,1,x\n").status_code == 422
    assert upload(client, "bank", b"id,date,amount\n").status_code == 422
    assert upload(client, "bank", b"\xff\xfe").status_code == 422


def test_import_is_atomic_one_bad_row_rejects_all(client):
    r = upload(client, "bank", csv_bytes("B1,2025-01-01,10.00,ok,,", "B2,2025-13-45,10.00,bad date,,",
                                         "B3,2025-01-01,10.00,bad cuit,20123456787,"))
    assert r.status_code == 422
    errs = r.json()["detail"]["errors"]
    assert {e["line"] for e in errs} == {3, 4}
    assert client.get("/bank-transactions").json() == []


def test_same_file_twice_is_idempotent(client):
    content = csv_bytes("B1,2025-01-01,10.00,x,,")
    first = upload(client, "bank", content).json()
    second = upload(client, "bank", content).json()
    assert second["duplicate_file"] is True and second["batch_id"] == first["batch_id"]
    assert len(client.get("/bank-transactions").json()) == 1
    assert len(client.get("/batches").json()) == 1


def test_overlapping_file_skips_known_rows_and_rejects_conflicts(client):
    upload(client, "bank", csv_bytes("B1,2025-01-01,10.00,x,,"))
    r = upload(client, "bank", csv_bytes("B1,2025-01-01,10.00,x,,", "B2,2025-01-02,20.00,y,,"))
    assert r.json()["imported"] == 1 and r.json()["skipped_existing"] == 1
    conflict = upload(client, "bank", csv_bytes("B1,2025-01-01,99.00,changed,,"))
    assert conflict.status_code == 409 and len(client.get("/bank-transactions").json()) == 2


def test_duplicate_lines_inside_file(client):
    ok = upload(client, "bank", csv_bytes("B1,2025-01-01,10.00,x,,", "B1,2025-01-01,10.00,x,,"))
    assert ok.json()["duplicates_in_file"] == 1 and ok.json()["imported"] == 1
    bad = upload(client, "deposits", csv_bytes("D1,2025-01-01,10.00,x,,", "D1,2025-01-01,11.00,x,,"))
    assert bad.status_code == 422


def test_actor_required_for_writes(client):
    assert upload(client, "bank", csv_bytes("B1,2025-01-01,10.00,x,,"), headers={}).status_code == 400
