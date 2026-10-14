import os
from collections.abc import Mapping

from .client import EvolusClient, EvolusError
from .mock import MockEvolusClient
from .models import (AI_TOOLS, AiToolResult, EvolusSettings, ExtractResult, WorkflowExecution, WorkflowStart)


def settings_from_env(env: Mapping[str, str] | None = None) -> EvolusSettings:
    e = os.environ if env is None else env
    kw = {
        "mode": e.get("EVOLUS_MODE", "disabled").strip().lower(),
        "api_key": e.get("EVOLUS_API_KEY", ""),
        "application_id": e.get("EVOLUS_APPLICATION_ID", "").strip(),
        "workflow_id": e.get("EVOLUS_WORKFLOW_ID", "").strip(),
        "extractor_agent_id": e.get("EVOLUS_EXTRACTOR_AGENT_ID", "").strip(),
        "extractor_id": e.get("EVOLUS_EXTRACTOR_ID", "").strip(),
        "timeout_s": e.get("EVOLUS_TIMEOUT_S", "30"),
        "max_retries": e.get("EVOLUS_MAX_RETRIES", "2"),
    }
    if e.get("EVOLUS_BASE_URL", "").strip():
        kw["base_url"] = e["EVOLUS_BASE_URL"].strip()
    return EvolusSettings(**kw)


def build_evolus(settings: EvolusSettings | None = None):
    """Returns None when disabled. `mock` is simulated and flagged as such; `live` needs real credentials."""
    s = settings or settings_from_env()
    if s.mode == "disabled":
        return None
    return MockEvolusClient() if s.mode == "mock" else EvolusClient(s)


__all__ = ["EvolusClient", "EvolusError", "MockEvolusClient", "EvolusSettings", "AiToolResult", "ExtractResult",
           "WorkflowExecution", "WorkflowStart", "AI_TOOLS", "settings_from_env", "build_evolus"]
