from fastapi import APIRouter, Depends, HTTPException, Request

from .models import SandboxInfo, SandboxRequest
from .service import SandboxService

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
