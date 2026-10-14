import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from inference import InferenceSettings, MockExtractor, VllmClient, build_client

TEXT = "TRANSF DE JUAN PEREZ COMP 000123 CUIT 20-12345678-6"
GOOD = {
    "documents": [{"value": "20-12345678-6", "evidence": "CUIT 20-12345678-6", "kind": "CUIT"}],
    "vouchers": [{"value": "000123", "evidence": "COMP 000123"}],
    "references": [],
    "names": [{"value": "JUAN PEREZ", "evidence": "DE JUAN PEREZ"}],
}


class FakeVllm:
    """Scripted OpenAI-compatible server. `script` is a list of (status, body|callable|'hang') consumed in order."""

    def __init__(self, script, models=("test-model",)):
        self.script, self.models, self.requests, self.auth = list(script), models, [], []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, payload):
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                outer.auth.append(self.headers.get("Authorization"))
                if self.path == "/v1/models":
                    self._send(200, {"data": [{"id": m} for m in outer.models]})
                else:
                    self._send(404, {})

            def do_POST(self):
                outer.auth.append(self.headers.get("Authorization"))
                outer.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                status, body = outer.script.pop(0) if outer.script else (500, {})
                if body == "hang":
                    threading.Event().wait(1.5)
                    return
                if isinstance(body, dict) and "content" in body:
                    body = {"choices": [{"message": {"content": body["content"]}}]}
                self._send(status, body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture()
def fake():
    servers = []

    def make(script, **kw):
        s = FakeVllm(script, **kw)
        servers.append(s)
        return s

    yield make
    for s in servers:
        s.close()


def client(url, **kw):
    cfg = dict(provider="vllm", base_url=url, model="test-model", api_key="secret-key", timeout_s=0.5,
               max_retries=2, retry_backoff_s=0.01)
    cfg.update(kw)
    return VllmClient(InferenceSettings(**cfg))


def test_success_validates_and_keeps_evidence(fake):
    srv = fake([(200, {"content": json.dumps(GOOD)})])
    r = client(srv.url).extract(TEXT)
    assert r.status == "ok" and not r.is_mock and r.source == "vllm"
    assert r.original_text == TEXT and r.latency_ms > 0 and r.attempts == 1
    assert "000123" in r.candidate_refs()
    req = srv.requests[0]
    assert req["model"] == "test-model" and req["temperature"] == 0
    assert srv.auth[0] == "Bearer secret-key"


def test_hallucinated_values_are_dropped(fake):
    bad = dict(GOOD, vouchers=[{"value": "999999", "evidence": "COMP 999999"},
                               {"value": "777777", "evidence": "COMP 000123"}])
    r = client(fake([(200, {"content": json.dumps(bad)})]).url).extract(TEXT)
    assert r.status == "ok" and r.extraction.vouchers == [] and len(r.dropped) == 2
    assert "999999" not in r.candidate_refs()


@pytest.mark.parametrize("content", ["not json", json.dumps({"documents": "x"}),
                                     json.dumps({**GOOD, "extra_key": 1})])
def test_invalid_output_is_flagged_not_trusted(fake, content):
    r = client(fake([(200, {"content": content})]).url).extract(TEXT)
    assert r.status == "invalid_output" and r.candidate_refs() == [] and r.raw_output == content


def test_retries_on_5xx_then_succeeds(fake):
    srv = fake([(503, {}), (500, {}), (200, {"content": json.dumps(GOOD)})])
    r = client(srv.url).extract(TEXT)
    assert r.status == "ok" and r.attempts == 3


def test_gives_up_after_max_retries(fake):
    r = client(fake([(500, {})] * 5).url, max_retries=1).extract(TEXT)
    assert r.status == "error" and r.attempts == 2 and r.error == "http_500"


def test_auth_error_not_retried(fake):
    srv = fake([(401, {})] * 3)
    r = client(srv.url).extract(TEXT)
    assert r.status == "error" and r.attempts == 1 and len(srv.requests) == 1


def test_timeout_is_an_error_result_not_an_exception(fake):
    r = client(fake([(200, "hang")] * 3).url, timeout_s=0.1, max_retries=0).extract(TEXT)
    assert r.status == "error" and r.error == "ReadTimeout"


def test_unreachable_endpoint(fake):
    r = client("http://127.0.0.1:9/v1", max_retries=0).extract(TEXT)
    assert r.status == "error"


def test_health_ok_degraded_down(fake):
    assert client(fake([]).url).health().status == "ok"
    h = client(fake([], models=("other",)).url).health()
    assert h.status == "degraded" and h.model_listed is False
    assert client("http://127.0.0.1:9/v1").health().status == "down"


def test_logs_never_contain_secrets_or_text(fake, caplog):
    with caplog.at_level(logging.DEBUG, logger="inference"):
        client(fake([(200, {"content": json.dumps(GOOD)})]).url).extract(TEXT)
        client(fake([(500, {})] * 3).url, max_retries=0).extract(TEXT)
    blob = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert "secret-key" not in blob and "JUAN PEREZ" not in blob and "20-12345678-6" not in blob


def test_settings_validation_and_no_silent_mock():
    with pytest.raises(ValueError):
        InferenceSettings.from_env({"INFERENCE_PROVIDER": "vllm"})
    s = InferenceSettings.from_env({"INFERENCE_PROVIDER": "vllm", "INFERENCE_BASE_URL": "http://h:8000/v1/",
                                    "INFERENCE_MODEL": "m", "INFERENCE_API_KEY": "topsecret"})
    assert s.base_url == "http://h:8000/v1" and "topsecret" not in repr(s)
    assert isinstance(build_client(s), VllmClient)
    assert build_client(InferenceSettings.from_env({})).is_mock


def test_mock_is_clearly_identified():
    r = MockExtractor().extract(TEXT)
    assert r.is_mock and r.source == "mock" and r.model.startswith("mock")
    assert "000123" in r.candidate_refs() and r.extraction.names[0].value == "JUAN PEREZ"
    assert "not AMD" in MockExtractor().health().detail


@pytest.mark.skipif(os.environ.get("INFERENCE_INTEGRATION") != "1",
                    reason="set INFERENCE_INTEGRATION=1 plus INFERENCE_* to test a real vLLM endpoint")
def test_real_endpoint_integration():
    s = InferenceSettings.from_env()
    assert s.provider == "vllm", "INFERENCE_PROVIDER must be vllm for the integration test"
    c = VllmClient(s)
    assert c.health().status == "ok"
    r = c.extract(TEXT)
    assert r.status in ("ok", "invalid_output")  # a real model may format badly; never a crash
    assert r.latency_ms > 0 and r.original_text == TEXT
