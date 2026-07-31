"""
Application configuration
"""

import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()

class Settings:
    app_name: str = "TraceNova"
    debug: bool = os.getenv("DEBUG", "True") == "True"
    api_version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8000

@lru_cache()
def get_settings():
    return Settings()
