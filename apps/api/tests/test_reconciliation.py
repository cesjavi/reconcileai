import json
import threading
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db import get_engine
from app.immutability import ImmutableRecordError
from app.models import AuditEvent, MatchCandidate, ReconciliationDecision
from conftest import H, csv_bytes, upload

DEMO = Path(__file__).resolve().parents[3] / "demo"
EXPECTED = json.loads((DEMO / "expected.json").read_text(encoding="utf-8"))


def seed_and_run(client):
    assert client.post("/demo/seed", headers=H).status_code == 200
    r = client.post("/reconcile/run", headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def candidates(client, **params):
    return client.get("/candidates", params={"limit": 500, **params}).json()


def pair_setup(client, banks, deposits):
    upload(client, "bank", csv_bytes(*banks))
    upload(client, "deposits", csv_bytes(*deposits))
    return client.post("/reconcile/run", headers=H).json()


# ---------- synthetic dataset vs. expected results ----------
def test_demo_dataset_size_and_expected_results(client):
    out = client.post("/demo/seed", headers=H).json()
    assert out["bank"]["imported"] >= 100 and out["deposits"]["imported"] >= 100
    assert out["bank"]["duplicates_in_file"] == EXPECTED["rows"]["duplicates_in_file"]
    client.post("/reconcile/run", headers=H)

    banks = {b["external_id"]: b for b in client.get("/bank-transactions", params={"limit": 500}).json()}
    deps = {d["external_id"]: d for d in client.get("/deposits", params={"limit": 500}).json()}
    cands = candidates(client)
    by_bank: dict[str, list[dict]] = {}
    for c in cands:
        by_bank.setdefault(c["bank"]["external_id"], []).append(c)

    wrong = []
    for ext, exp in EXPECTED["bank"].items():
        got_status = banks[ext]["status"]
        got = by_bank.get(ext, [])
        got_rules = {c["rule"] for c in got}
        got_deps = sorted(c["deposit"]["external_id"] for c in got)
        if got_status != exp["status"] or got_deps != sorted(exp["deposits"]) or (
                exp["rule"] and got_rules != {exp["rule"]}):
            wrong.append((ext, exp, got_status, got_rules, got_deps))
    assert not wrong, wrong[:5]
    for ext, exp in EXPECTED["deposits"].items():
        assert deps[ext]["status"] == exp["status"], ext

    def tally(items):
        t = {}
        for i in items:
            t[i["status"]] = t.get(i["status"], 0) + 1
        return t
    assert tally(banks.values()) == EXPECTED["bank_status_counts"]
    assert tally(deps.values()) == EXPECTED["deposit_status_counts"]


def test_only_exact_voucher_matches_are_automatic(client):
    seed_and_run(client)
    matched = candidates(client, status="MATCHED")
    assert matched and all(c["rule"] == "R1" for c in matched)
    assert all(c["rule"] != "R4" for c in matched)


def test_rerun_is_idempotent(client):
    seed_and_run(client)
    snap1 = [(c["id"], c["status"], c["rule"]) for c in candidates(client)]
    audit1 = len(client.get("/audit", params={"limit": 500}).json())
    again = client.post("/reconcile/run", headers=H).json()
    snap2 = [(c["id"], c["status"], c["rule"]) for c in candidates(client)]
    assert snap1 == snap2
    assert again["MATCHED"] == 0  # nothing new to auto-match
    assert len(client.get("/audit", params={"limit": 500}).json()) == audit1 + 1  # only the run itself is logged
    assert len({(c["bank"]["id"], c["deposit"]["id"]) for c in candidates(client)}) == len(snap2)


def test_seed_twice_does_not_duplicate(client):
    client.post("/demo/seed", headers=H)
    second = client.post("/demo/seed", headers=H).json()
    assert second["bank"]["duplicate_file"] and second["deposits"]["duplicate_file"]
    assert len(client.get("/bank-transactions", params={"limit": 500}).json()) == EXPECTED["rows"]["bank_unique"]


# ---------- equal amounts, window boundaries, ambiguity ----------
def test_equal_amounts_without_other_evidence_are_ambiguous(client):
    pair_setup(client, ["B1,2025-03-10,500.00,x,,"],
               ["D1,2025-03-10,500.00,x,,", "D2,2025-03-11,500.00,x,,"])
    cs = candidates(client)
    assert len(cs) == 2 and {c["status"] for c in cs} == {"AMBIGUOUS"}
    assert client.get("/bank-transactions").json()[0]["status"] == "AMBIGUOUS"


def test_date_window_boundary(client):
    pair_setup(client, ["B1,2025-03-10,10.00,x,,", "B2,2025-03-10,20.00,x,,"],
               ["D1,2025-03-13,10.00,x,,", "D2,2025-03-14,20.00,x,,"])  # 3 days vs 4 days
    got = {c["bank"]["external_id"]: c for c in candidates(client)}
    assert set(got) == {"B1"} and got["B1"]["rule"] == "R3"


def test_voucher_with_different_amount_is_not_matched(client):
    pair_setup(client, ["B1,2025-03-10,10.00,x,,V-1001"], ["D1,2025-03-10,10.01,x,,V-1001"])
    assert candidates(client) == []
    assert client.get("/bank-transactions").json()[0]["status"] == "UNMATCHED"


def test_ambiguous_requires_a_note_and_resolves_siblings(client):
    pair_setup(client, ["B1,2025-03-10,500.00,x,,"], ["D1,2025-03-10,500.00,x,,", "D2,2025-03-11,500.00,x,,"])
    first, second = candidates(client)
    assert client.post(f"/candidates/{first['id']}/approve", json={}, headers=H).status_code == 422
    ok = client.post(f"/candidates/{first['id']}/approve", json={"note": "checked receipt"}, headers=H)
    assert ok.status_code == 200
    assert [c["id"] for c in candidates(client)] == [first["id"]]  # rival candidate superseded
    deps = {d["external_id"]: d["status"] for d in client.get("/deposits").json()}
    assert deps == {"D1": "MATCHED", "D2": "UNMATCHED"}


# ---------- approve / reject ----------
def test_approve_reject_flow_and_finality(client):
    seed_and_run(client)
    sug = candidates(client, status="SUGGESTED")
    a, r = sug[0], sug[1]
    assert client.post(f"/candidates/{a['id']}/approve", json={}, headers={}).status_code == 400
    assert client.post(f"/candidates/{a['id']}/approve", json={}, headers=H).json()["status"] == "MATCHED"
    assert client.post(f"/candidates/{r['id']}/reject", json={"note": "wrong customer"}, headers=H).json()["status"] == "REJECTED"
    for cid in (a["id"], r["id"]):
        assert client.post(f"/candidates/{cid}/approve", json={}, headers=H).status_code == 409
        assert client.post(f"/candidates/{cid}/reject", json={}, headers=H).status_code == 409
    assert client.post("/candidates/999999/approve", json={}, headers=H).status_code == 404


def test_rejected_pair_is_never_proposed_again_and_bank_becomes_rejected(client):
    pair_setup(client, ["B1,2025-03-10,10.00,x,,"], ["D1,2025-03-10,10.00,x,,"])
    cid = candidates(client)[0]["id"]
    client.post(f"/candidates/{cid}/reject", json={"note": "no"}, headers=H)
    assert client.get("/bank-transactions").json()[0]["status"] == "REJECTED"
    client.post("/reconcile/run", headers=H)
    cs = candidates(client)
    assert [c["status"] for c in cs] == ["REJECTED"]  # still the same single rejected pair
    assert client.get("/summary").json()["review_queue"] == 0


def test_rejecting_one_of_two_ambiguous_leaves_the_other_decidable(client):
    pair_setup(client, ["B1,2025-03-10,500.00,x,,"], ["D1,2025-03-10,500.00,x,,", "D2,2025-03-11,500.00,x,,"])
    first = candidates(client)[0]
    client.post(f"/candidates/{first['id']}/reject", json={}, headers=H)
    client.post("/reconcile/run", headers=H)
    pending = candidates(client, status="SUGGESTED")  # no longer ambiguous after the rejection
    assert len(pending) == 1 and pending[0]["deposit"]["external_id"] == "D2"


def test_approval_revalidates_deterministically(client):
    pair_setup(client, ["B1,2025-03-10,10.00,x,,"], ["D1,2025-03-10,10.00,x,,"])
    cid = candidates(client)[0]["id"]
    with get_engine().begin() as conn:  # simulate a corrupted/stale candidate: amount no longer equal
        conn.execute(text("UPDATE system_deposits SET amount = 11.00"))
    r = client.post(f"/candidates/{cid}/approve", json={}, headers=H)
    assert r.status_code == 422 and "amounts differ" in r.json()["detail"]


# ---------- AI never bypasses deterministic validation ----------
def test_ai_reference_suggested_but_never_auto_matched(client, fake_extractor):
    fake_extractor.refs_by_text["TRANSF REF 000777 CLIENTE"] = ["000777"]
    pair_setup(client, ["B1,2025-03-01,100.00,TRANSF REF 000777 CLIENTE,,"], ["D1,2025-03-20,100.00,x,,777"])
    c = candidates(client)[0]
    assert (c["rule"], c["status"], c["evidence"]["source"]) == ("R4", "SUGGESTED", "ai_verified")
    logs = client.get("/inference/logs").json()
    assert logs[0]["accepted"] is True and logs[0]["original_text"] == "TRANSF REF 000777 CLIENTE"
    assert logs[0]["model"] == "fake-model" and logs[0]["latency_ms"] == 12.5


def test_ai_hallucination_cannot_create_a_match(client, fake_extractor):
    desc = "TRANSF CLIENTE SA"
    fake_extractor.refs_by_text[desc] = ["999888"]  # exists as a deposit voucher but NOT in the bank text
    pair_setup(client, [f"B1,2025-03-01,100.00,{desc},,"], ["D1,2025-03-20,100.00,x,,999888"])
    assert candidates(client) == []
    log = client.get("/inference/logs").json()[0]
    assert log["accepted"] is False


def test_ai_not_called_when_deterministic_rules_resolve(client, fake_extractor):
    pair_setup(client, ["B1,2025-03-01,100.00,whatever,,V-5555"], ["D1,2025-03-01,100.00,x,,V-5555"])
    assert fake_extractor.calls == []


def test_ai_candidate_cannot_be_approved_if_amount_changed(client, fake_extractor):
    fake_extractor.refs_by_text["REF 000777 X"] = ["000777"]
    pair_setup(client, ["B1,2025-03-01,100.00,REF 000777 X,,"], ["D1,2025-03-20,100.00,x,,777"])
    cid = candidates(client)[0]["id"]
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE system_deposits SET amount = 100.50"))
    assert client.post(f"/candidates/{cid}/approve", json={}, headers=H).status_code == 422


def test_misconfigured_vllm_does_not_fall_back_to_mock(client, monkeypatch):
    import app.main as m
    m._extractor.cache_clear()
    monkeypatch.setattr(m.get_settings(), "inference_provider", "vllm")
    monkeypatch.setattr(m.get_settings(), "inference_base_url", "")
    r = client.post("/reconcile/run", headers=H)
    m._extractor.cache_clear()
    assert r.status_code == 503 and "misconfigured" in r.json()["detail"]


# ---------- uniqueness / concurrency ----------
def test_database_forbids_two_effective_links(client):
    pair_setup(client, ["B1,2025-03-10,500.00,x,,"], ["D1,2025-03-10,500.00,x,,", "D2,2025-03-11,500.00,x,,"])
    ids = [c["id"] for c in candidates(client)]
    from sqlalchemy.orm import Session
    with Session(get_engine()) as s:
        for cid in ids:
            s.get(MatchCandidate, cid).status = "MATCHED"
        try:
            s.commit()
            raised = False
        except IntegrityError:
            raised = True
    assert raised, "partial unique index must reject two MATCHED candidates for one bank transaction"


def test_concurrent_approvals_of_competing_candidates_only_one_wins(client):
    pair_setup(client, ["B1,2025-03-10,500.00,x,,", "B2,2025-03-10,500.00,y,,"], ["D1,2025-03-10,500.00,x,,"])
    cs = candidates(client)
    assert len(cs) == 2
    results, barrier = [], threading.Barrier(2)
    from fastapi.testclient import TestClient
    from app.main import app

    def worker(cid):
        c = TestClient(app)
        barrier.wait()
        results.append(c.post(f"/candidates/{cid}/approve", json={"note": "race"}, headers=H).status_code)

    threads = [threading.Thread(target=worker, args=(c["id"],)) for c in cs]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results)[0] == 200 and results.count(200) == 1, results
    assert all(code in (200, 404, 409) for code in results)
    assert len(candidates(client, status="MATCHED")) == 1
    assert client.get("/audit/verify").json()["valid"] is True


def test_concurrent_identical_imports_create_one_batch(client):
    content = csv_bytes("B1,2025-03-10,10.00,x,,")
    codes, barrier = [], threading.Barrier(4)
    from fastapi.testclient import TestClient
    from app.main import app

    def worker():
        c = TestClient(app)
        barrier.wait()
        codes.append(upload(c, "bank", content).status_code)

    ts = [threading.Thread(target=worker) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert all(c in (200, 409) for c in codes) and 200 in codes, codes
    assert len(client.get("/bank-transactions").json()) == 1
    assert len([b for b in client.get("/batches").json() if b["kind"] == "BANK"]) == 1
    assert client.get("/audit/verify").json()["valid"] is True


def test_concurrent_runs_keep_state_consistent(client):
    client.post("/demo/seed", headers=H)
    codes, barrier = [], threading.Barrier(3)
    from fastapi.testclient import TestClient
    from app.main import app

    def worker():
        c = TestClient(app)
        barrier.wait()
        codes.append(c.post("/reconcile/run", headers=H).status_code)

    ts = [threading.Thread(target=worker) for _ in range(3)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert all(c in (200, 409) for c in codes) and 200 in codes, codes
    client.post("/reconcile/run", headers=H)  # settle
    cs = candidates(client)
    assert len({(c["bank"]["id"], c["deposit"]["id"]) for c in cs}) == len(cs)
    matched = [c for c in cs if c["status"] == "MATCHED"]
    assert len({c["bank"]["id"] for c in matched}) == len(matched) == len({c["deposit"]["id"] for c in matched})
    assert client.get("/audit/verify").json()["valid"] is True


# ---------- immutable audit ----------
def test_audit_chain_and_application_level_immutability(client):
    seed_and_run(client)
    assert client.get("/audit/verify").json()["valid"] is True
    from sqlalchemy import delete, update
    from sqlalchemy.orm import Session
    with Session(get_engine()) as s:
        ev = s.scalars(select(AuditEvent)).first()
        ev.actor = "mallory"
        try:
            s.flush()
            raise AssertionError("ORM update of AuditEvent must fail")
        except ImmutableRecordError:
            s.rollback()
        for stmt in (update(AuditEvent).values(actor="x"), delete(AuditEvent),
                     delete(ReconciliationDecision)):
            try:
                s.execute(stmt)
                raise AssertionError("bulk statement must fail")
            except ImmutableRecordError:
                s.rollback()
    with get_engine().begin() as conn:  # bypassing the app (raw SQL) is detected by the hash chain
        conn.execute(text("UPDATE audit_events SET actor='mallory' WHERE seq=2"))
    v = client.get("/audit/verify").json()
    assert v["valid"] is False


def test_every_state_change_is_audited(client):
    seed_and_run(client)
    actions = {a["action"] for a in client.get("/audit", params={"limit": 500}).json()}
    assert {"import_bank", "import_deposit", "reconcile_run", "auto_match"} <= actions
    cid = candidates(client, status="SUGGESTED")[0]["id"]
    client.post(f"/candidates/{cid}/approve", json={"note": "ok"}, headers=H)
    top = client.get("/audit", params={"limit": 1}).json()[0]
    assert top["action"] == "candidate_approved" and top["actor"] == "tester" and top["payload"]["note"] == "ok"
    from sqlalchemy.orm import Session
    with Session(get_engine()) as s:
        assert s.scalars(select(ReconciliationDecision).where(ReconciliationDecision.action == "APPROVE")).first()


def test_inference_metrics_do_not_count_mock_as_real(client):
    seed_and_run(client)  # default provider is mock
    m = client.get("/inference/metrics").json()
    assert m["has_real_inference"] is False and m["real_calls"] == 0 and m["mock_calls"] > 0
    assert m["real_latency_ms"]["avg"] is None
    h = client.get("/inference/health").json()
    assert h["is_mock"] is True and "not AMD" in h["detail"]
