"""SIMULATED Evolus for development without credentials. Same interface as EvolusClient.

Nothing here talks to Evolus. Every id is prefixed `mock-` and every result carries `simulated: true`, so a
simulated run can never be mistaken for a real Evolus execution.
"""
from __future__ import annotations

import itertools
from typing import Any

from .client import EvolusError
from .models import AI_TOOLS, AiToolResult, ExtractResult, WorkflowExecution, WorkflowStart


class MockEvolusClient:
    is_mock = True

    def __init__(self) -> None:
        self._n = itertools.count(1)
        self._inputs: dict[str, str] = {}

    def execute_workflow(self, text: str, parameters: dict[str, Any] | None = None,
                         workflow_id: str | None = None) -> WorkflowStart:
        eid = f"mock-exec-{next(self._n)}"
        self._inputs[eid] = text
        return WorkflowStart(job_id=f"mock-job-{eid}", execution_id=eid, trace_id=f"mock-trace-{eid}")

    def get_execution(self, execution_id: str, workflow_id: str | None = None) -> WorkflowExecution:
        if execution_id not in self._inputs:
            raise EvolusError("client", "unknown simulated execution", 404)
        return WorkflowExecution(execution_id=execution_id, status="Completed", raw={
            "simulated": True, "output": "SIMULATED advisory: evidence reviewed; human decision required."})

    def run_ai_tool(self, tool: str, text: str, secondary_text: str | None = None,
                    options: dict[str, Any] | None = None) -> AiToolResult:
        if tool not in AI_TOOLS:
            raise EvolusError("client", f"unknown AI tool {tool!r}")
        return AiToolResult(tool=tool, output=f"[SIMULATED {tool}] {text[:200]}", credits_consumed=0.0)

    def extract_document(self, filename: str, content: bytes, **_: Any) -> ExtractResult:
        return ExtractResult(data={"simulated": True, "rows": []}, execution_id="mock-askfile-1")
