"""Inference configuration, read only from environment variables."""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, SecretStr, model_validator


class InferenceSettings(BaseModel):
    provider: Literal["mock", "vllm"] = "mock"
    # OpenAI-compatible root, e.g. http://<host>:8000/v1. No default: an endpoint is never invented.
    base_url: str = ""
    api_key: SecretStr = SecretStr("")
    model: str = ""
    timeout_s: float = 30.0
    max_retries: int = 2
    retry_backoff_s: float = 0.5
    json_mode: bool = True
    # Free text declared by the operator (e.g. "AMD Developer Cloud, ROCm"). NOT verified by this code.
    hardware_label: str = ""

    @model_validator(mode="after")
    def _check(self):
        if self.provider == "vllm":
            if not self.base_url.startswith(("http://", "https://")):
                raise ValueError("INFERENCE_BASE_URL (http/https) is required when INFERENCE_PROVIDER=vllm")
            if not self.model:
                raise ValueError("INFERENCE_MODEL is required when INFERENCE_PROVIDER=vllm")
        if self.max_retries < 0 or self.timeout_s <= 0:
            raise ValueError("INFERENCE_MAX_RETRIES must be >= 0 and INFERENCE_TIMEOUT_S > 0")
        return self

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "InferenceSettings":
        e = os.environ if env is None else env
        return cls(
            provider=e.get("INFERENCE_PROVIDER", "mock").strip().lower(),
            base_url=e.get("INFERENCE_BASE_URL", "").strip().rstrip("/"),
            api_key=e.get("INFERENCE_API_KEY", ""),
            model=e.get("INFERENCE_MODEL", "").strip(),
            timeout_s=e.get("INFERENCE_TIMEOUT_S", "30"),
            max_retries=e.get("INFERENCE_MAX_RETRIES", "2"),
            retry_backoff_s=e.get("INFERENCE_RETRY_BACKOFF_S", "0.5"),
            json_mode=e.get("INFERENCE_JSON_MODE", "true").strip().lower() not in ("0", "false", "no"),
            hardware_label=e.get("INFERENCE_HARDWARE_LABEL", "").strip(),
        )
