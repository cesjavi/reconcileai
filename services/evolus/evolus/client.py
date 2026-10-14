"""HTTP client for the documented Evolus REST endpoints.

  POST /workflows/{workflowId}/execute                 multipart: input, parameters(JSON), file...  -> 202
  GET  /workflows/{workflowId}/executions/{executionId}                                             -> status
  POST /ai-tools/{tool}/run                            JSON {text, secondaryText, options}
  POST /agents/{agentId}/json/{extractorId}/ask-file?useWebhook=false    multipart: file

Auth: X-ApiKey + X-Application-Id. Safe logging: ids, status and latency only; never keys or document text.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from .models import AI_TOOLS, AiToolResult, EvolusSettings, ExtractResult, WorkflowExecution, WorkflowStart

log = logging.getLogger("evolus")
_RETRYABLE = {429, 500, 502, 503, 504}


class EvolusError(Exception):
    """kind: auth | credits | conflict | rate_limited | server | timeout | contract | client | not_configured"""

    def __init__(self, kind: str, message: str, status: int | None = None):
        super().__init__(f"{kind}: {message}")
        self.kind, self.message, self.status = kind, message, status


def _kind(status: int) -> str:
    return {401: "auth", 403: "auth", 402: "credits", 409: "conflict", 429: "rate_limited"}.get(
        status, "server" if status >= 500 else "client")


class EvolusClient:
    is_mock = False

    def __init__(self, settings: EvolusSettings, transport: httpx.BaseTransport | None = None):
        self.s = settings
        self._http = httpx.Client(timeout=settings.timeout_s, transport=transport)

    def close(self) -> None:
        self._http.close()

    def _headers(self) -> dict[str, str]:
        return {"X-ApiKey": self.s.api_key.get_secret_value(), "X-Application-Id": self.s.application_id}

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        url = f"{self.s.base_url.rstrip('/')}{path}"
        start, attempt = time.perf_counter(), 0
        while True:
            attempt += 1
            try:
                r = self._http.request(method, url, headers=self._headers(), **kw)
            except httpx.TimeoutException as exc:
                err = EvolusError("timeout", type(exc).__name__)
            except httpx.TransportError as exc:
                err = EvolusError("server", type(exc).__name__)
            else:
                if r.status_code < 400:
                    log.info("evolus_call", extra={"method": method, "path": path.split("?")[0].rsplit("/", 1)[0],
                                                   "status": r.status_code, "attempts": attempt,
                                                   "ms": round((time.perf_counter() - start) * 1000, 1)})
                    return r
                err = EvolusError(_kind(r.status_code), f"http {r.status_code}", r.status_code)
                if r.status_code in _RETRYABLE and attempt <= self.s.max_retries:
                    ra = r.headers.get("Retry-After")
                    time.sleep(min(float(ra), 30) if ra and ra.replace(".", "", 1).isdigit()
                               else self.s.retry_backoff_s * 2 ** (attempt - 1))
                    continue
                raise err
            if attempt > self.s.max_retries:
                raise err
            time.sleep(self.s.retry_backoff_s * 2 ** (attempt - 1))

    # ---- workflows ----
    def execute_workflow(self, text: str, parameters: dict[str, Any] | None = None,
                         workflow_id: str | None = None) -> WorkflowStart:
        wid = workflow_id or self.s.workflow_id
        if not wid:
            raise EvolusError("not_configured", "EVOLUS_WORKFLOW_ID is not set")
        fields = {"input": (None, text)}
        if parameters:  # documented as a flat JSON object
            if any(isinstance(v, (dict, list)) for v in parameters.values()):
                raise EvolusError("client", "workflow parameters must be a flat JSON object")
            fields["parameters"] = (None, json.dumps(parameters))
        r = self._request("POST", f"/workflows/{wid}/execute", files=fields)
        try:
            body = r.json()
            start = WorkflowStart(job_id=body.get("jobId"), execution_id=str(
                body.get("executionId") or r.headers.get("X-Workflow-Execution-Id") or ""),
                enqueued_at=body.get("enqueuedAt"), trace_id=body.get("traceId"))
        except (ValueError, AttributeError) as exc:
            raise EvolusError("contract", "unparseable 202 body") from exc
        if not start.execution_id:
            raise EvolusError("contract", "no executionId in body or X-Workflow-Execution-Id header")
        return start

    def get_execution(self, execution_id: str, workflow_id: str | None = None) -> WorkflowExecution:
        wid = workflow_id or self.s.workflow_id
        if not wid:
            raise EvolusError("not_configured", "EVOLUS_WORKFLOW_ID is not set")
        body = self._request("GET", f"/workflows/{wid}/executions/{execution_id}").json()
        status = body.get("status") if isinstance(body, dict) else None
        if status not in ("Pending", "Running", "Completed", "Failed"):
            raise EvolusError("contract", f"unexpected execution status {status!r}")
        return WorkflowExecution(execution_id=execution_id, status=status, raw=body)

    # ---- AI Tools ----
    def run_ai_tool(self, tool: str, text: str, secondary_text: str | None = None,
                    options: dict[str, Any] | None = None) -> AiToolResult:
        if tool not in AI_TOOLS:
            raise EvolusError("client", f"unknown AI tool {tool!r}")
        body: dict[str, Any] = {"text": text}
        if secondary_text is not None:
            body["secondaryText"] = secondary_text
        if options:
            body["options"] = options
        data = self._request("POST", f"/ai-tools/{tool}/run", json=body).json()
        try:
            return AiToolResult(tool=data["tool"], output=data["output"],
                                credits_consumed=data.get("creditsConsumed"), truncated=bool(data.get("truncated")))
        except (KeyError, TypeError, ValueError) as exc:
            raise EvolusError("contract", "AI tool response lacks tool/output") from exc

    # ---- document extractor ----
    def extract_document(self, filename: str, content: bytes, content_type: str = "application/pdf",
                         agent_id: str | None = None, extractor_id: str | None = None) -> ExtractResult:
        aid, eid = agent_id or self.s.extractor_agent_id, extractor_id or self.s.extractor_id
        if not (aid and eid):
            raise EvolusError("not_configured", "EVOLUS_EXTRACTOR_AGENT_ID / EVOLUS_EXTRACTOR_ID not set")
        r = self._request("POST", f"/agents/{aid}/json/{eid}/ask-file", params={"useWebhook": "false"},
                          files={"file": (filename, content, content_type)})
        try:
            data = r.json()
        except ValueError as exc:
            raise EvolusError("contract", "extractor returned non-JSON") from exc
        return ExtractResult(data=data, execution_id=r.headers.get("X-AskFile-Execution-Id"),
                             audit_id=r.headers.get("X-AskFile-Audit-Id"))
