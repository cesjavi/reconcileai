"""Typed views over the Evolus REST contract.

Only fields documented at https://evolus.ai/developers are modelled as required. Everything the public docs
leave unspecified (full execution body, webhook payload, extractor schema) is kept as `raw` and treated as
opaque, advisory data.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, SecretStr, model_validator

WORKFLOW_STATUSES = ("Pending", "Running", "Completed", "Failed")
AI_TOOLS = ("doc-structure", "tables", "translate", "anonymize", "summarize", "minutes", "email", "rewrite",
            "simplify", "sentiment", "compare")


class EvolusSettings(BaseModel):
    mode: Literal["disabled", "live", "mock"] = "disabled"
    base_url: str = "https://api.evolus.ai/api/v1"  # documented REST base
    api_key: SecretStr = SecretStr("")
    application_id: str = ""
    workflow_id: str = ""
    extractor_agent_id: str = ""
    extractor_id: str = ""
    timeout_s: float = 30.0
    max_retries: int = 2
    retry_backoff_s: float = 1.0

    @model_validator(mode="after")
    def _check(self):
        if self.mode == "live" and not (self.api_key.get_secret_value() and self.application_id):
            raise ValueError("EVOLUS_API_KEY and EVOLUS_APPLICATION_ID are required when EVOLUS_MODE=live")
        return self


class WorkflowStart(BaseModel):
    model_config = ConfigDict(extra="ignore")
    job_id: str | None = None
    execution_id: str
    enqueued_at: str | None = None
    trace_id: str | None = None


class WorkflowExecution(BaseModel):
    execution_id: str
    status: Literal["Pending", "Running", "Completed", "Failed"]
    raw: dict[str, Any]

    @property
    def terminal(self) -> bool:
        return self.status in ("Completed", "Failed")


class AiToolResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tool: str
    output: Any
    credits_consumed: float | None = None
    truncated: bool = False


class ExtractResult(BaseModel):
    data: Any
    execution_id: str | None = None
    audit_id: str | None = None
