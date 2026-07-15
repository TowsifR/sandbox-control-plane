from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCP_", env_file=".env")

    mode: Literal["real", "fake"] = "real"  # "fake" = in-memory sandboxes, no Temporal/k8s

    temporal_address: str = "localhost:7233"  # port-forward svc/temporal-frontend for local dev
    temporal_namespace: str = "default"
    task_queue: str = "sandbox-lifecycle"

    claim_namespace: str = "default"


@lru_cache
def get_settings() -> Settings:
    return Settings()
