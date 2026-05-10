from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://liwang:liwang@localhost:5432/liwang"
    session_secret: str = "dev-only-change-me"
    run_migrations_on_startup: bool = True

    files_root: Path = Path("./var/files")

    dashscope_api_key: str = ""
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    # DeepSeek pricing (¥ per 1K tokens) — used for cost estimation in usage_monthly
    deepseek_input_cny_per_1k: float = 0.00027
    deepseek_output_cny_per_1k: float = 0.0011
    chat_top_k: int = 4
    chat_max_history: int = 10  # trailing turns to include in context

    embed_model: str = "text-embedding-v3"
    embed_dim: int = 1024
    embed_batch_size: int = 10
    chunk_size: int = 512
    chunk_overlap: int = 64

    default_storage_quota_mb: int = 100

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def default_storage_quota_bytes(self) -> int:
        return self.default_storage_quota_mb * 1024 * 1024


settings = Settings()
settings.files_root.mkdir(parents=True, exist_ok=True)
