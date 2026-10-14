import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from evolus import (EvolusClient, EvolusError, EvolusSettings, MockEvolusClient, build_evolus, settings_from_env)


class ContractServer:
    """Replays the response shapes published at evolus.ai/developers. `script` maps 'METHOD path' -> list of
    (status, headers, body) consumed in order; the last entry repeats."""

    def __init__(self, script):
        self.script, self.seen = script, []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _handle(self, method):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                outer.seen.append({"method": method, "path": self.path, "headers": dict(self.headers), "body": body})
                key = f"{method} {self.path.split('?')[0]}"
                queue = outer.script.get(key)
                if not queue:
                    status, headers, payload = 404, {}, {}
                else:
                    status, headers, payload = queue.pop(0) if len(queue) > 1 else queue[0]
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for k, v in headers.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            do_GET = lambda self: self._handle("GET")  # noqa: E731
            do_POST = lambda self: self._handle("POST")  # noqa: E731

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}/api/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture()
def serve():
    made = []

    def make(script):
        s = ContractServer(script)
        made.append(s)
        return s

    yield make
    for s in made:
        s.close()


def client(srv, **kw):
    cfg = dict(mode="live", base_url=srv.url, api_key="k-secret", application_id="app-1", workflow_id="wf-1",
               extractor_agent_id="ag-1", extractor_id="ex-1", timeout_s=2, max_retries=2, retry_backoff_s=0.01)
    cfg.update(kw)
    return EvolusClient(EvolusSettings(**cfg))


ACCEPTED = (202, {"X-Workflow-Execution-Id": "e-1"},
            {"jobId": "j-1", "executionId": "e-1", "enqueuedAt": "2026-10-14T00:00:00Z", "traceId": "t-1"})


def test_execute_workflow_contract(serve):
    srv = serve({"POST /api/v1/workflows/wf-1/execute": [ACCEPTED]})
    out = client(srv).execute_workflow("case text", {"candidate_id": 7, "rule": "R3"})
    assert (out.execution_id, out.job_id, out.trace_id) == ("e-1", "j-1", "t-1")
    req = srv.seen[0]
    assert req["headers"]["X-ApiKey"] == "k-secret" and req["headers"]["X-Application-Id"] == "app-1"
    assert "multipart/form-data" in req["headers"]["Content-Type"]
    assert b'name="input"' in req["body"] and b"case text" in req["body"]
    assert b'name="parameters"' in req["body"] and b'"candidate_id": 7' in req["body"]


def test_execution_id_falls_back_to_header(serve):
    srv = serve({"POST /api/v1/workflows/wf-1/execute": [(202, {"X-Workflow-Execution-Id": "e-9"}, {"jobId": "j"})]})
    assert client(srv).execute_workflow("x").execution_id == "e-9"


def test_missing_execution_id_is_a_contract_error(serve):
    srv = serve({"POST /api/v1/workflows/wf-1/execute": [(202, {}, {"jobId": "j"})]})
    with pytest.raises(EvolusError) as e:
        client(srv).execute_workflow("x")
    assert e.value.kind == "contract"


def test_nested_parameters_rejected_before_sending(serve):
    srv = serve({})
    with pytest.raises(EvolusError):
        client(srv).execute_workflow("x", {"a": {"b": 1}})
    assert srv.seen == []


def test_get_execution_statuses(serve):
    path = "GET /api/v1/workflows/wf-1/executions/e-1"
    srv = serve({path: [(200, {}, {"status": "Running"}), (200, {}, {"status": "Completed", "output": "ok"})]})
    c = client(srv)
    assert c.get_execution("e-1").terminal is False
    done = c.get_execution("e-1")
    assert done.status == "Completed" and done.terminal and done.raw["output"] == "ok"


def test_unknown_status_is_a_contract_error(serve):
    srv = serve({"GET /api/v1/workflows/wf-1/executions/e-1": [(200, {}, {"status": "Exploded"})]})
    with pytest.raises(EvolusError) as e:
        client(srv).get_execution("e-1")
    assert e.value.kind == "contract"


@pytest.mark.parametrize("status,kind", [(401, "auth"), (402, "credits"), (409, "conflict"), (400, "client")])
def test_errors_are_classified_and_not_retried(serve, status, kind):
    srv = serve({"POST /api/v1/workflows/wf-1/execute": [(status, {}, {})]})
    with pytest.raises(EvolusError) as e:
        client(srv).execute_workflow("x")
    assert e.value.kind == kind and len(srv.seen) == 1


def test_rate_limit_and_5xx_are_retried(serve):
    srv = serve({"POST /api/v1/workflows/wf-1/execute": [(429, {"Retry-After": "0"}, {}), (503, {}, {}), ACCEPTED]})
    assert client(srv).execute_workflow("x").execution_id == "e-1" and len(srv.seen) == 3


def test_gives_up_after_retries(serve):
    srv = serve({"POST /api/v1/workflows/wf-1/execute": [(500, {}, {})]})
    with pytest.raises(EvolusError) as e:
        client(srv, max_retries=1).execute_workflow("x")
    assert e.value.kind == "server" and len(srv.seen) == 2


def test_ai_tool_run_contract(serve):
    srv = serve({"POST /api/v1/ai-tools/summarize/run": [
        (200, {}, {"tool": "summarize", "output": "short", "creditsConsumed": 2, "truncated": False})]})
    r = client(srv).run_ai_tool("summarize", "long text", options={"length": "short"})
    assert (r.output, r.credits_consumed, r.truncated) == ("short", 2, False)
    assert json.loads(srv.seen[0]["body"]) == {"text": "long text", "options": {"length": "short"}}


def test_ai_tool_unknown_name_and_bad_shape(serve):
    srv = serve({"POST /api/v1/ai-tools/summarize/run": [(200, {}, {"nope": 1})]})
    with pytest.raises(EvolusError):
        client(srv).run_ai_tool("not-a-tool", "x")
    with pytest.raises(EvolusError) as e:
        client(srv).run_ai_tool("summarize", "x")
    assert e.value.kind == "contract"


def test_document_extractor_ask_file(serve):
    srv = serve({"POST /api/v1/agents/ag-1/json/ex-1/ask-file": [
        (200, {"X-AskFile-Execution-Id": "x-1", "X-AskFile-Audit-Id": "a-1"}, {"rows": []})]})
    r = client(srv).extract_document("statement.pdf", b"%PDF-1.4 fake")
    assert r.data == {"rows": []} and (r.execution_id, r.audit_id) == ("x-1", "a-1")
    assert "useWebhook=false" in srv.seen[0]["path"] and b'name="file"' in srv.seen[0]["body"]


def test_not_configured_ids(serve):
    c = client(serve({}), workflow_id="", extractor_id="")
    for call in (lambda: c.execute_workflow("x"), lambda: c.get_execution("e"), lambda: c.extract_document("a", b"")):
        with pytest.raises(EvolusError) as e:
            call()
        assert e.value.kind == "not_configured"


def test_settings_and_factory():
    assert build_evolus(settings_from_env({})) is None  # disabled by default
    with pytest.raises(ValueError):
        settings_from_env({"EVOLUS_MODE": "live"})
    s = settings_from_env({"EVOLUS_MODE": "live", "EVOLUS_API_KEY": "topsecret", "EVOLUS_APPLICATION_ID": "a"})
    assert "topsecret" not in repr(s) and s.base_url == "https://api.evolus.ai/api/v1"
    assert isinstance(build_evolus(settings_from_env({"EVOLUS_MODE": "mock"})), MockEvolusClient)


def test_mock_is_flagged_as_simulated():
    m = MockEvolusClient()
    start = m.execute_workflow("x")
    assert start.execution_id.startswith("mock-") and m.get_execution(start.execution_id).raw["simulated"] is True
    assert "SIMULATED" in m.run_ai_tool("summarize", "x").output


@pytest.mark.skipif(os.environ.get("EVOLUS_INTEGRATION") != "1",
                    reason="set EVOLUS_INTEGRATION=1 with EVOLUS_* credentials to hit the real Evolus API")
def test_real_evolus_integration():
    s = settings_from_env()
    assert s.mode == "live"
    c = EvolusClient(s)
    r = c.run_ai_tool("summarize", "Bank transfer of 100.00 received on 2026-10-14 for invoice FC 0001-00000001.")
    assert r.tool == "summarize" and r.output
    if s.workflow_id:
        start = c.execute_workflow("ReconcileAI integration check", {"source": "integration-test"})
        assert c.get_execution(start.execution_id).status in ("Pending", "Running", "Completed", "Failed")
