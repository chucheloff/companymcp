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
    mcp_port: int = 8081
    mcp_path: str = "/mcp"

    tavily_api_key: str | None = Field(default=None)
    openrouter_api_key: str | None = Field(default=None)
    valkey_url: str = "redis://valkey:6379/0"


settings = Settings()
