from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket

from ..core.config import get_settings
from ..core.kubernetes import get_kubernetes_client
from .gateway import CONTAINER
from .models import SandboxInfo, SandboxRequest
from .service import SandboxService
from .terminal import run_local_pty, run_pod_exec

router = APIRouter(prefix="/sandboxes", tags=["sandboxes"])


def get_service(request: Request) -> SandboxService:
    return request.app.state.sandbox_service  # built in the app lifespan


@router.post("", response_model=SandboxInfo, status_code=201)
async def create_sandbox(
    req: SandboxRequest, service: SandboxService = Depends(get_service)
) -> SandboxInfo:
    return await service.create(req)


@router.get("", response_model=list[SandboxInfo])
async def list_sandboxes(service: SandboxService = Depends(get_service)) -> list[SandboxInfo]:
    return await service.list()


@router.get("/{sandbox_id}", response_model=SandboxInfo)
async def get_sandbox(
    sandbox_id: str, service: SandboxService = Depends(get_service)
) -> SandboxInfo:
    info = await service.get(sandbox_id)
    if info is None:
        raise HTTPException(status_code=404, detail="sandbox not found")
    return info


@router.delete("/{sandbox_id}", status_code=204)
async def delete_sandbox(sandbox_id: str, service: SandboxService = Depends(get_service)) -> None:
    await service.delete(sandbox_id)


@router.websocket("/{sandbox_id}/terminal")
async def sandbox_terminal(websocket: WebSocket, sandbox_id: str) -> None:
    service = websocket.app.state.sandbox_service
    info = await service.get(sandbox_id)
    await websocket.accept()
    if info is None:
        await websocket.close(code=1008, reason="sandbox not found")
        return
    if info.phase != "running":
        await websocket.close(code=1008, reason="sandbox not running")
        return
    if get_settings().mode == "fake":
        await run_local_pty(websocket)  # local shell stands in for pods/exec
        return
    if info.namespace is None:  # the composition hasn't published it yet
        await websocket.close(code=1008, reason="sandbox has no namespace yet")
        return
    pod = await service.pod_name(sandbox_id, info.namespace)
    if pod is None:
        await websocket.close(code=1008, reason="sandbox pod not found")
        return
    await run_pod_exec(websocket, get_kubernetes_client(), info.namespace, pod, CONTAINER)
