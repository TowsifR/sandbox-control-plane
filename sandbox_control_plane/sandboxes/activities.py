"""Temporal activities — thin async wrappers over SandboxGateway.

The kubernetes client is synchronous, so each call is offloaded with
`asyncio.to_thread` to avoid blocking the activity event loop.
"""

import asyncio

from temporalio import activity

from ..core.config import get_settings
from ..core.kubernetes import get_kubernetes_client
from .gateway import SandboxGateway
from .models import LifecycleParams


def _gateway() -> SandboxGateway:
    return SandboxGateway(get_kubernetes_client(), get_settings().claim_namespace)


@activity.defn
async def create_sandbox_claim(params: LifecycleParams) -> None:
    gw = _gateway()
    await asyncio.to_thread(gw.create, params.name, params.owner, params.size, params.image)


@activity.defn
async def check_sandbox_ready(name: str) -> bool:
    return await asyncio.to_thread(_gateway().is_ready, name)


@activity.defn
async def delete_sandbox_claim(name: str) -> None:
    await asyncio.to_thread(_gateway().delete, name)
