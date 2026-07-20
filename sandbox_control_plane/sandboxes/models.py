from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, Field

Size = Literal["small", "medium", "large"]
# A governed flavor (see the platform's persona catalog). When set it drives the image and a
# locked-down agent config; when None, the raw image is used.
Persona = Literal["builder", "architect"]


class SandboxRequest(BaseModel):
    """What the API client sends to create a sandbox."""

    owner: str
    size: Size = "small"
    image: str = "busybox:1.36"
    persona: Persona | None = None
    ttl: timedelta = Field(default=timedelta(hours=1), description="seconds (e.g. 120) or ISO-8601 (PT2M)")


class LifecycleParams(BaseModel):
    """Args handed to the SandboxLifecycle workflow."""

    name: str
    owner: str
    size: Size
    image: str
    persona: Persona | None
    ttl: timedelta


class SandboxInfo(BaseModel):
    """What the API returns for a sandbox."""

    id: str  # = claim name = workflow id
    owner: str
    size: str
    image: str
    persona: str | None = None
    phase: str  # from the workflow: provisioning | running | deleting | deleted
    namespace: str | None = None
