"""Evolus integration tests. They run against a contract double (a fake client), NOT the real Evolus API."""
import pytest
from evolus import AiToolResult, EvolusError, WorkflowExecution, WorkflowStart

from app.config import get_settings
from app.evolus_routes import get_evolus, mask
from app.main import app
from conftest import H, csv_bytes, upload

TOKEN = "agent-secret-token"
AGENT = {"Authorization": f"Bearer {TOKEN}"}


class FakeEvolus:
    is_mock = False

    def __init__(self):
        self.workflow_calls, self.tool_calls, self.fail_tool = [], [], None
        self.status = "Running"

    def run_ai_tool(self, tool, text, secondary_text=None, options=None):
        self.tool_calls.append((tool, text))
        if self.fail_tool:
            raise self.fail_tool
        return AiToolResult(tool=tool, output="Short summary for the reviewer", credits_consumed=1.5)

    def execute_workflow(self, text, parameters=None, workflow_id=None):
        self.workflow_calls.append((text, parameters))
        return WorkflowStart(execution_id=f"exec-{len(self.workflow_calls)}", trace_id="trace-1")

    def get_execution(self, execution_id, workflow_id=None):
        return WorkflowExecution(execution_id=execution_id, status=self.status, raw={"status": self.status})


@pytest.fixture()
def evo(client, monkeypatch):
    fake = FakeEvolus()
    app.dependency_overrides[get_evolus] = lambda: fake
    monkeypatch.setattr(get_settings(), "agent_api_token", TOKEN)
    return fake


def setup_cases(client):
    upload(client, "bank", csv_bytes("B1,2025-03-10,500.00,PAGO 20123456786,20123456786,",
                                     "B2,2025-03-10,10.00,x,,", "B3,2025-03-10,99.00,y,,V-1"))
    upload(client, "deposits", csv_bytes("D1,2025-03-10,500.00,x,,", "D2,2025-03-11,500.00,x,,",
                                         "D3,2025-03-10,10.00,x,,", "D4,2025-03-10,99.00,y,,V-1"))
    client.post("/reconcile/run", headers=H)
    cs = client.get("/candidates", params={"limit": 50}).json()
    return {c["bank"]["external_id"]: c for c in cs}


def only_auto_matched(client):
    """The only MATCHED candidate is B3's exact voucher match, made by the engine at reconcile time."""
    m = client.get("/candidates", params={"status": "MATCHED"}).json()
    return [(c["bank"]["external_id"], c["rule"]) for c in m] == [("B3", "R1")]


def test_review_calls_ai_tool_and_workflow_and_records_ids(client, evo):
    cs = setup_cases(client)
    cid = cs["B2"]["id"]
    r = client.post(f"/candidates/{cid}/evolus-review", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["remote_execution_id"] == "exec-1" and body["trace_id"] == "trace-1"
    assert body["status"] == "Pending" and body["simulated"] is False
    assert body["advisory_text"] == "Short summary for the reviewer" and body["credits_consumed"] == 1.5
    assert evo.tool_calls[0][0] == "summarize"
    text, params = evo.workflow_calls[0]
    assert params == {"candidate_id": cid, "rule": "R3", "engine_status": "SUGGESTED"}
    assert all(not isinstance(v, (dict, list)) for v in params.values())  # flat, as the contract requires


def test_review_masks_documents_before_leaving(client, evo):
    cs = setup_cases(client)
    client.post(f"/candidates/{cs['B1']['id']}/evolus-review", headers=H)
    sent = evo.workflow_calls[0][0] + evo.tool_calls[0][1]
    assert "20123456786" not in sent and "***786" in sent
    assert mask("CUIT 20123456786 ref 12") == "CUIT ***786 ref 12"


def test_review_is_idempotent(client, evo):
    cid = setup_cases(client)["B2"]["id"]
    first = client.post(f"/candidates/{cid}/evolus-review", headers=H).json()
    second = client.post(f"/candidates/{cid}/evolus-review", headers=H).json()
    assert second["reused"] is True and second["id"] == first["id"]
    assert len(evo.workflow_calls) == 1


def test_failed_review_is_recorded_and_retryable(client, evo):
    cid = setup_cases(client)["B2"]["id"]
    evo.fail_tool = EvolusError("credits", "http 402", 402)
    r = client.post(f"/candidates/{cid}/evolus-review", headers=H)
    assert r.status_code == 502 and r.json()["status"] == "Error" and "credits" in r.json()["error"]
    assert client.get("/evolus/executions").json()[0]["error"].startswith("credits")
    assert evo.workflow_calls == []  # nothing was started after the tool failed
    evo.fail_tool = None
    ok = client.post(f"/candidates/{cid}/evolus-review", headers=H)
    assert ok.status_code == 200 and ok.json()["status"] == "Pending"
    assert len(client.get("/evolus/executions").json()) == 1  # same row retried, no duplicates


def test_refresh_tracks_status_and_audits_terminal_state(client, evo):
    cid = setup_cases(client)["B2"]["id"]
    ex = client.post(f"/candidates/{cid}/evolus-review", headers=H).json()
    assert client.post(f"/evolus/executions/{ex['id']}/refresh", headers=H).json()["status"] == "Running"
    evo.status = "Completed"
    assert client.post(f"/evolus/executions/{ex['id']}/refresh", headers=H).json()["status"] == "Completed"
    actions = [a["action"] for a in client.get("/audit", params={"limit": 20}).json()]
    assert "evolus_execution_completed" in actions and "evolus_review_started" in actions
    assert client.get("/audit/verify").json()["valid"] is True


def test_evolus_result_never_changes_candidate_state(client, evo):
    cid = setup_cases(client)["B2"]["id"]
    ex = client.post(f"/candidates/{cid}/evolus-review", headers=H).json()
    evo.status = "Completed"
    client.post(f"/evolus/executions/{ex['id']}/refresh", headers=H)
    assert client.get("/candidates", params={"status": "SUGGESTED"}).json()[0]["id"] == cid
    assert only_auto_matched(client)


def test_disabled_evolus_is_explicit(client):
    app.dependency_overrides[get_evolus] = lambda: None
    cid = setup_cases(client)["B2"]["id"]
    assert client.post(f"/candidates/{cid}/evolus-review", headers=H).status_code == 503
    st = client.get("/evolus/status").json()
    assert st["enabled"] is False and st["simulated"] is False


# ---------- inbound agent API ----------
def test_agent_api_requires_token(client, evo, monkeypatch):
    setup_cases(client)
    assert client.get("/agent/cases").status_code == 401
    assert client.get("/agent/cases", headers={"Authorization": "Bearer wrong"}).status_code == 401
    monkeypatch.setattr(get_settings(), "agent_api_token", "")
    assert client.get("/agent/cases", headers=AGENT).status_code == 503


def test_agent_cases_are_masked_and_pending_only(client, evo):
    setup_cases(client)
    cases = client.get("/agent/cases", headers=AGENT).json()
    assert cases and all(c["status"] in ("SUGGESTED", "AMBIGUOUS") for c in cases)
    assert "20123456786" not in str(cases)


def test_agent_cannot_recommend_approving_ambiguous(client, evo):
    amb = setup_cases(client)["B1"]
    assert amb["status"] == "AMBIGUOUS"
    h = {**AGENT, "Idempotency-Key": "key-0001"}
    r = client.post(f"/agent/cases/{amb['id']}/recommendation", json={"recommendation": "APPROVE"}, headers=h)
    assert r.status_code == 422
    ok = client.post(f"/agent/cases/{amb['id']}/recommendation",
                     json={"recommendation": "NEEDS_HUMAN", "rationale": "two deposits tie"},
                     headers={**AGENT, "Idempotency-Key": "key-0002"})
    assert ok.status_code == 200


def test_agent_recommendation_is_idempotent_and_advisory_only(client, evo):
    c = setup_cases(client)["B2"]
    h = {**AGENT, "Idempotency-Key": "retry-key-1"}
    body = {"recommendation": "APPROVE", "rationale": "voucher and amount agree"}
    a = client.post(f"/agent/cases/{c['id']}/recommendation", json=body, headers=h).json()
    b = client.post(f"/agent/cases/{c['id']}/recommendation", json=body, headers=h).json()
    assert a["id"] == b["id"] and b["reused"] is True
    assert client.get(f"/candidates/{c['id']}/insights").json()["recommendations"][0]["recommendation"] == "APPROVE"
    still = client.get("/candidates", params={"status": "SUGGESTED"}).json()
    assert c["id"] in [x["id"] for x in still]  # APPROVE recommendation did not approve anything


def test_agent_token_cannot_reach_human_decision_endpoints(client, evo):
    c = setup_cases(client)["B2"]
    for path in ("approve", "reject"):  # agent bearer token is not an identity: X-Actor is still required
        r = client.post(f"/candidates/{c['id']}/{path}", json={}, headers=AGENT)
        assert r.status_code == 400
    assert only_auto_matched(client)


def test_agent_cannot_recommend_on_decided_candidates(client, evo):
    c = setup_cases(client)["B2"]
    client.post(f"/candidates/{c['id']}/approve", json={}, headers=H)
    r = client.post(f"/agent/cases/{c['id']}/recommendation", json={"recommendation": "REJECT"},
                    headers={**AGENT, "Idempotency-Key": "late-key-1"})
    assert r.status_code == 409
