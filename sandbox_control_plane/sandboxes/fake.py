"""In-memory sandbox service for local dev without a cluster (SCP_MODE=fake).

Same surface as SandboxService, backed by a dict — no Temporal, no Kubernetes.
A sandbox flips provisioning → running after a short delay to mimic the real flow.
"""

import secrets
import time

from .models import SandboxInfo, SandboxRequest

_READY_AFTER_SECONDS = 2.0


class FakeSandboxService:
    def __init__(self) -> None:
        self._store: dict[str, tuple[SandboxInfo, float]] = {}  # id -> (info, ready-at monotonic)

    async def create(self, req: SandboxRequest) -> SandboxInfo:
        sid = f"sb-{secrets.token_hex(4)}"
        info = SandboxInfo(
            id=sid,
            owner=req.owner,
            size=req.size,
            image=req.image,
            phase="provisioning",
            namespace=f"sandbox-{sid}",
        )
        ready_at = time.monotonic() + _READY_AFTER_SECONDS
        self._store[sid] = (info, ready_at)
        return self._view(info, ready_at)

    async def get(self, sandbox_id: str) -> SandboxInfo | None:
        entry = self._store.get(sandbox_id)
        return self._view(*entry) if entry else None

    async def list(self) -> list[SandboxInfo]:
        return [self._view(info, ready_at) for info, ready_at in self._store.values()]

    async def delete(self, sandbox_id: str) -> None:
        self._store.pop(sandbox_id, None)

    @staticmethod
    def _view(info: SandboxInfo, ready_at: float) -> SandboxInfo:
        phase = "running" if time.monotonic() >= ready_at else "provisioning"
        return info.model_copy(update={"phase": phase})
