from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    sakura_ai_base_url: str = "https://api.ai.sakura.ad.jp/v1"
    sakura_ai_api_key: str = ""
    sakura_ai_model: str = "gpt-oss-120b"
    sakura_ai_timeout_sec: float = 90.0

    monthly_request_limit: int = 2500
    ip_daily_limit: int = 5
    ip_minute_limit: int = 1
    max_ingredients_chars: int = 2000

    sqlite_db_path: str = "data/app.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
