from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "company-mcp"
    app_version: str = "0.1.0"
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    mcp_path: str = "/mcp"

    tavily_api_key: str | None = Field(default=None)
    openrouter_enabled: bool = True
    openrouter_api_key: str | None = Field(default=None)
    openrouter_model_tier: str = "free"
    openrouter_free_extraction_model: str = "openrouter/free"
    openrouter_free_quality_model: str = "openrouter/free"
    openrouter_extraction_model: str = "openai/gpt-5-mini"
    openrouter_quality_model: str = "openai/gpt-5.1"
    valkey_url: str = "redis://valkey:6379/0"
    valkey_retry_seconds: float = 5.0
    browser_timeout_ms: int = 12_000


settings = Settings()
