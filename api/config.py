"""Application configuration loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import List


@dataclass(frozen=True)
class Settings:
    """Runtime settings derived from environment variables."""

    storage_root: str
    redis_url: str
    queue_name: str
    max_file_size: int
    api_key: str
    cors_origins: List[str]
    rate_limit_per_minute: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache settings from the environment."""

    cors_origins_raw = os.getenv("CORS_ORIGINS")
    cors_origins = [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()] if cors_origins_raw else ["*"]

    return Settings(
        storage_root=os.getenv("STORAGE_ROOT", "/tmp/submissions"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        queue_name=os.getenv("QUEUE_NAME", "default"),
        max_file_size=int(os.getenv("MAX_FILE_SIZE", 50 * 1024 * 1024)),
        api_key=os.getenv("API_KEY", ""),
        cors_origins=cors_origins,
        rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "30")),
    )


__all__ = ["Settings", "get_settings"]
