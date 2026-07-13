"""Temporal activities — thin async wrappers over SandboxGateway.

The kubernetes client is synchronous, so each call is offloaded with
`asyncio.to_thread` to avoid blocking the activity event loop.
"""

import asyncio

from kubernetes.client.rest import ApiException
from temporalio import activity
from temporalio.exceptions import ApplicationError

from ..core.config import get_settings
from ..core.kubernetes import get_kubernetes_client
from .gateway import SandboxGateway
from .models import LifecycleParams


def _gateway() -> SandboxGateway:
    return SandboxGateway(get_kubernetes_client(), get_settings().claim_namespace)


@activity.defn
async def create_sandbox_claim(params: LifecycleParams) -> None:
    gw = _gateway()
    try:
        await asyncio.to_thread(gw.create, params.name, params.owner, params.size, params.image)
    except ApiException as e:
        status = e.status or 0
        # 4xx = the claim was rejected (policy/RBAC/schema); retrying can't help, so fail
        # cleanly. 429/408 are transient throttle/timeout — let those retry. (409 never reaches here.)
        if 400 <= status < 500 and status not in (408, 429):
            raise ApplicationError(
                f"Sandbox claim rejected ({status} {e.reason}): {e.body}",
                type="ClaimRejected",
                non_retryable=True,
            ) from e
        raise


@activity.defn
async def check_sandbox_ready(name: str) -> bool:
    return await asyncio.to_thread(_gateway().is_ready, name)


@activity.defn
async def delete_sandbox_claim(name: str) -> None:
    await asyncio.to_thread(_gateway().delete, name)
