"""Read configuration from environment variables, validated once per cold start.

Values come from ``provider.environment`` + ``functions.<fn>.environment`` in
pskit.yml (resolved per stage), or from ``.env`` when running locally.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    stage: str
    table_name: str
    log_level: str
    feature_new_checkout: bool
    api_base_url: str
    payment_api_key_set: bool  # never expose the secret itself


def _bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        stage=os.environ.get("PSKIT_STAGE", "local"),
        table_name=os.environ["TABLE_NAME"],
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        feature_new_checkout=_bool(os.environ.get("FEATURE_NEW_CHECKOUT", "false")),
        api_base_url=os.environ.get("API_BASE_URL", ""),
        payment_api_key_set=bool(os.environ.get("PAYMENT_API_KEY")),
    )
