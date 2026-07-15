from contextlib import asynccontextmanager

from fastapi import FastAPI

from .core.config import get_settings
from .core.kubernetes import get_kubernetes_client
from .core.temporal import get_temporal_client
from .sandboxes.fake import FakeSandboxService
from .sandboxes.gateway import SandboxGateway
from .sandboxes.router import router as sandboxes_router
from .sandboxes.service import SandboxService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.mode == "fake":
        app.state.sandbox_service = FakeSandboxService()
    else:
        client = await get_temporal_client()
        gateway = SandboxGateway(get_kubernetes_client(), settings.claim_namespace)
        app.state.sandbox_service = SandboxService(client, gateway)
    yield


app = FastAPI(title="Sandbox Control Plane", lifespan=lifespan)
app.include_router(sandboxes_router)
