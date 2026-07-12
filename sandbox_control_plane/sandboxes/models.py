from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, Field

Size = Literal["small", "medium", "large"]


class SandboxRequest(BaseModel):
    """What the API client sends to create a sandbox."""

    owner: str
    size: Size = "small"
    image: str = "busybox:1.36"
    ttl: timedelta = Field(default=timedelta(hours=1), description="seconds (e.g. 120) or ISO-8601 (PT2M)")


class LifecycleParams(BaseModel):
    """Args handed to the SandboxLifecycle workflow."""

    name: str
    owner: str
    size: Size
    image: str
    ttl: timedelta


class SandboxInfo(BaseModel):
    """What the API returns for a sandbox."""

    id: str  # = claim name = workflow id
    owner: str
    size: str
    image: str
    phase: str  # from the workflow: provisioning | running | deleting | deleted
    namespace: str | None = None
