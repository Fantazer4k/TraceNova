"""
Application configuration
"""

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    app_name: str = "TraceNova"
    debug: bool = _env_bool("DEBUG", False)
    api_version: str = "0.1.0"
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))
    max_concurrent_analyses: int = max(1, int(os.getenv("MAX_CONCURRENT_ANALYSES", "8")))
    cors_origins: list[str] = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]


@lru_cache()
def get_settings():
    return Settings()
