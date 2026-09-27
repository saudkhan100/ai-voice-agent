from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (or .env in development)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["dev", "prod"] = "dev"
    public_base_url: str = "http://localhost:8000"  # must be https in prod; Twilio calls back here
    secret_key: str = Field("change-me", repr=False)
    lead_api_key: str = Field("change-me", repr=False)

    database_url: str = Field(
        "postgresql+asyncpg://dealer:dealer@localhost:5432/dealer_ai", repr=False
    )

    # Dealership facts used in the agent prompt (move to dealership_settings once the dashboard exists)
    dealership_name: str = "the dealership"
    agent_name: str = "Maroof"

    # Twilio
    twilio_enabled: bool = True
    twilio_account_sid: str = ""
    twilio_auth_token: str = Field("", repr=False)
    twilio_from_number: str = Field(
        default="", validation_alias=AliasChoices("twilio_from_number", "twilio_from")
    )
    twilio_record_calls: bool = True
    twilio_validate_signatures: bool = True

    # Voice engine: switch engines by config only. Empty model = Pipecat's default for that engine.
    voice_engine: Literal["gemini", "openai"] = "gemini"
    google_api_key: str = Field("", repr=False)
    gemini_live_model: str = ""
    gemini_voice: str = "Charon"
    gemini_analysis_model: str = "gemini-2.5-flash"
    openai_api_key: str = Field("", repr=False)
    openai_realtime_model: str = ""

    max_concurrent_calls: int = 2
    max_call_seconds: int = 600

    @property
    def ws_base_url(self) -> str:
        return self.public_base_url.replace("https://", "wss://").replace("http://", "ws://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
