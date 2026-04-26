from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env", override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gradium_api_key: str = Field(..., alias="GRADIUM_API_KEY")
    ai_coustics_api_key: str = Field(..., alias="AI_COUSTICS_API_KEY")
    google_cloud_project: str | None = Field(None, alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field("us-central1", alias="GOOGLE_CLOUD_LOCATION")
    google_model: str = Field("gemini-2.5-flash", alias="GOOGLE_MODEL")
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(None, alias="OPENAI_BASE_URL")
    openai_model: str | None = Field(None, alias="OPENAI_MODEL")
    openai_transcription_model: str = "gpt-4o-mini-transcribe"
    triage_api_key: str | None = Field(None, alias="TRIAGE_API_KEY")
    triage_base_url: str = Field("https://api.pioneer.ai/v1", alias="TRIAGE_BASE_URL")
    triage_decoder_model: str | None = Field(None, alias="TRIAGE_DECODER_MODEL")
    triage_gliner_model: str | None = Field(None, alias="TRIAGE_GLINER_MODEL")
    triage_gliner_live_enabled: bool = Field(False, alias="TRIAGE_GLINER_LIVE_ENABLED")
    triage_gliner_timeout_s: float = Field(2.0, alias="TRIAGE_GLINER_TIMEOUT_S")
    triage_request_timeout_s: float = Field(15.0, alias="TRIAGE_REQUEST_TIMEOUT_S")
    deepgram_api_key: str | None = Field(None, alias="DEEPGRAM_API_KEY")
    soniox_api_key: str | None = Field(None, alias="SONIOX_API_KEY")
    stt_rescue_continuous_compare: bool = Field(False, alias="STT_RESCUE_CONTINUOUS_COMPARE")
    tavily_api_key: str | None = Field(None, alias="TAVILY_API_KEY")
    telli_api_key: str | None = Field(None, alias="TELLI_API_KEY")
    ai_coustics_model_id: str = "quail-vf-2.1-l-16khz"
    ai_coustics_model_dir: Path = REPO_ROOT / ".cache" / "ai-coustics-models"
    triage_engine: str = Field("heuristic", alias="TRIAGE_ENGINE")
    live_dispatch_mode: str = Field("slm", alias="LIVE_DISPATCH_MODE")


def get_settings() -> Settings:
    return Settings()
