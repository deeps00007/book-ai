from functools import lru_cache
import os
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    @field_validator("*", mode="before")
    @classmethod
    def _clean_env_value(cls, v):
        # Defensive: values piped in on Windows can become "value\r\nn"
        # (CRLF + the answer to an interactive prompt). Keep only the first
        # line, stripped of stray CR/LF/whitespace.
        if isinstance(v, str):
            return v.split("\n")[0].replace("\r", "").strip()
        return v

    fireworks_api_key: str = ""
    fireworks_base_url: str = "https://api.fireworks.ai/inference/v1"
    openai_api_key: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""
    anthropic_api_key: str = ""

    database_url: str = ""
    use_sqlite: bool = False
    sqlite_path: str = "./bookai.db"

    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = "dev-secret-key-change-in-production"
    access_token_expire_minutes: int = 1440

    upload_dir: str = "/tmp/uploads"

    embedding_model: str = "nomic-ai/nomic-embed-text-v1.5"
    embedding_dimension: int = 768
    chunk_size: int = 500
    chunk_overlap: int = 80

    default_llm_model: str = "accounts/fireworks/models/deepseek-v4p1-flash"
    default_llm_provider: str = "fireworks"
    temperature: float = 0.2
    max_tokens: int = 4096

    environment: str = "development"

    google_service_account_json: str = ""
    google_drive_folder_id: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""

    github_token: str = ""
    github_repo: str = "deeps00007/book-ai"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings: Settings = Settings()
