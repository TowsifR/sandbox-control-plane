from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..core.config import get_settings
from ..core.kubernetes import get_kubernetes_client
from . import chat
from .gateway import CONTAINER
from .models import SandboxInfo, SandboxRequest
from .service import SandboxService
from .terminal import run_local_pty, run_pod_exec

router = APIRouter(prefix="/sandboxes", tags=["sandboxes"])


def get_service(request: Request) -> SandboxService:
    return request.app.state.sandbox_service  # built in the app lifespan


class ChatPrompt(BaseModel):
    text: str


async def _chat_pod(service: SandboxService, sandbox_id: str) -> tuple[str, str]:
    """Resolve the running pod to proxy chat to, or raise. Chat needs a real, running opencode pod."""
    info = await service.get(sandbox_id)
    if info is None:
        raise HTTPException(status_code=404, detail="sandbox not found")
    if info.phase != "running" or info.namespace is None:
        raise HTTPException(status_code=409, detail="sandbox not running")
    pod = await service.pod_name(sandbox_id, info.namespace)
    if pod is None:
        raise HTTPException(status_code=404, detail="sandbox pod not found")
    return info.namespace, pod


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


# Chat proxies to the pod's `opencode serve` (see chat.py). JSON round-trips forward opencode's own
# response bytes/status verbatim; events is its SSE stream piped straight through.
def _json(pair: tuple[int, bytes]) -> Response:
    return Response(content=pair[1], status_code=pair[0], media_type="application/json")


@router.post("/{sandbox_id}/chat/sessions")
async def chat_create_session(
    sandbox_id: str, service: SandboxService = Depends(get_service)
) -> Response:
    ns, pod = await _chat_pod(service, sandbox_id)
    return _json(await chat.create_session(get_kubernetes_client(), ns, pod))


@router.get("/{sandbox_id}/chat/sessions/{session_id}/messages")
async def chat_messages(
    sandbox_id: str, session_id: str, service: SandboxService = Depends(get_service)
) -> Response:
    ns, pod = await _chat_pod(service, sandbox_id)
    path = f"/api/session/{session_id}/message"
    return _json(await chat.request(get_kubernetes_client(), ns, pod, "GET", path))


@router.post("/{sandbox_id}/chat/sessions/{session_id}/prompt")
async def chat_prompt(
    sandbox_id: str,
    session_id: str,
    prompt: ChatPrompt,
    service: SandboxService = Depends(get_service),
) -> Response:
    ns, pod = await _chat_pod(service, sandbox_id)
    path = f"/api/session/{session_id}/prompt"
    body = {"prompt": {"text": prompt.text}}
    # the model can take a while; the reply also streams over the events channel
    return _json(await chat.request(get_kubernetes_client(), ns, pod, "POST", path, body, timeout=300.0))


@router.get("/{sandbox_id}/chat/sessions/{session_id}/events")
async def chat_events(
    sandbox_id: str, session_id: str, service: SandboxService = Depends(get_service)
) -> StreamingResponse:
    ns, pod = await _chat_pod(service, sandbox_id)
    stream = chat.stream_events(get_kubernetes_client(), ns, pod, session_id)
    return StreamingResponse(stream, media_type="text/event-stream")
