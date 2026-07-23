import asyncio
import secrets

from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode

from ..core.config import get_settings
from .gateway import SandboxGateway
from .models import LifecycleParams, SandboxInfo, SandboxRequest
from .workflows import SandboxLifecycle


class SandboxService:
    """Coordinates the sandbox lifecycle: starts/queries/cancels workflows and
    reads claims. Routes call this; it holds no HTTP concerns."""

    def __init__(self, client: Client, gateway: SandboxGateway) -> None:
        self._client = client
        self._gateway = gateway
        self._task_queue = get_settings().task_queue

    async def create(self, req: SandboxRequest) -> SandboxInfo:
        name = f"sb-{secrets.token_hex(4)}"
        params = LifecycleParams(
            name=name, owner=req.owner, size=req.size, image=req.image, persona=req.persona, ttl=req.ttl
        )
        await self._client.start_workflow(
            SandboxLifecycle.run, params, id=name, task_queue=self._task_queue
        )
        # Claim isn't created until the workflow's first activity runs — report from the request.
        return SandboxInfo(
            id=name, owner=req.owner, size=req.size, image=req.image, persona=req.persona, phase="provisioning"
        )

    async def get(self, sandbox_id: str) -> SandboxInfo | None:
        claim = await asyncio.to_thread(self._gateway.get, sandbox_id)
        if claim is None:
            return None
        return self._info(claim, await self._phase(sandbox_id))

    async def list(self) -> list[SandboxInfo]:
        claims = await asyncio.to_thread(self._gateway.list)
        return [self._info(c, await self._phase(c["metadata"]["name"])) for c in claims]

    async def delete(self, sandbox_id: str) -> None:
        # Signal the workflow to expire early; its cleanup deletes the claim.
        handle = self._client.get_workflow_handle(sandbox_id)
        try:
            await handle.signal(SandboxLifecycle.request_delete)
        except RPCError as e:
            # Workflow already finished (e.g. TTL expired first), so its cleanup already ran and the
            # sandbox is gone — deleting an already-gone sandbox is a no-op, not a 500.
            if e.status is not RPCStatusCode.NOT_FOUND:
                raise

    async def pod_name(self, sandbox_id: str, namespace: str) -> str | None:
        return await asyncio.to_thread(self._gateway.pod_name, namespace, sandbox_id)

    async def _phase(self, sandbox_id: str) -> str:
        try:
            handle = self._client.get_workflow_handle(sandbox_id)
            return await handle.query(SandboxLifecycle.phase)
        except Exception:  # workflow closed or gone
            return "unknown"

    @staticmethod
    def _info(claim: dict, phase: str) -> SandboxInfo:
        spec = claim.get("spec", {})
        return SandboxInfo(
            id=claim["metadata"]["name"],
            owner=spec.get("owner", ""),
            size=spec.get("size", ""),
            image=spec.get("image", ""),
            persona=spec.get("persona"),
            phase=phase,
            namespace=(claim.get("status") or {}).get("namespace"),
        )
