from functools import lru_cache

from evolus import EvolusSettings
from inference import InferenceSettings
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./reconcileai.db"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    demo_dir: str = "demo"

    # Deterministic engine
    window_days: int = 3
    ai_window_days: int = 30
    auto_match_rules: str = "R1"  # comma list; R4 (AI) is never auto-matched regardless of this value
    ai_extraction_enabled: bool = True

    # Inference ("mock" or "vllm"); see services/inference/inference/settings.py
    inference_provider: str = "mock"
    inference_base_url: str = ""
    inference_api_key: str = ""
    inference_model: str = ""
    inference_timeout_s: float = 30.0
    inference_max_retries: int = 2
    inference_retry_backoff_s: float = 0.5
    inference_json_mode: bool = True
    inference_hardware_label: str = ""

    # Evolus: "disabled" (default), "live" (real API, needs credentials) or "mock" (SIMULATED)
    evolus_mode: str = "disabled"
    evolus_base_url: str = "https://api.evolus.ai/api/v1"
    evolus_api_key: str = ""
    evolus_application_id: str = ""
    evolus_workflow_id: str = ""
    evolus_extractor_agent_id: str = ""
    evolus_extractor_id: str = ""
    evolus_timeout_s: float = 30.0
    evolus_max_retries: int = 2
    agent_api_token: str = ""  # bearer token the Evolus workflow/agent uses to call /agent/*; empty = API off

    def evolus_settings(self) -> EvolusSettings:
        return EvolusSettings(
            mode=self.evolus_mode.strip().lower(), base_url=self.evolus_base_url.strip(), api_key=self.evolus_api_key,
            application_id=self.evolus_application_id.strip(), workflow_id=self.evolus_workflow_id.strip(),
            extractor_agent_id=self.evolus_extractor_agent_id.strip(), extractor_id=self.evolus_extractor_id.strip(),
            timeout_s=self.evolus_timeout_s, max_retries=self.evolus_max_retries)

    def inference_settings(self) -> InferenceSettings:
        return InferenceSettings(
            provider=self.inference_provider.strip().lower(), base_url=self.inference_base_url.strip().rstrip("/"),
            api_key=self.inference_api_key, model=self.inference_model.strip(), timeout_s=self.inference_timeout_s,
            max_retries=self.inference_max_retries, retry_backoff_s=self.inference_retry_backoff_s,
            json_mode=self.inference_json_mode, hardware_label=self.inference_hardware_label)


@lru_cache
def get_settings() -> Settings:
    return Settings()
