"""Chat proxy: speak HTTP to the pod's `opencode serve` over a Kubernetes port-forward.

The sandbox NetworkPolicy denies ingress, so we never reach the agent over the pod network — port-forward
tunnels to its localhost:4096 through the apiserver (like exec), and we drive plain HTTP over that socket.
"""

import asyncio
import http.client
import json
import threading
from collections.abc import AsyncIterator
from contextlib import suppress

from kubernetes.stream import portforward

from ..core.kubernetes import KubernetesClient

_PORT = 4096
_READ_SIZE = 8192
# opencode serve otherwise runs sessions on its own default (a *paid* model the free Zen key rejects), so
# we pin each new session to the persona's configured model — falling back to a free one when none is set.
_FALLBACK_MODEL = "opencode/deepseek-v4-flash-free"


class _SocketConn(http.client.HTTPConnection):
    """HTTPConnection that talks over an already-open socket (the port-forward tunnel) instead of dialing."""

    def __init__(self, sock: object, timeout: float | None) -> None:
        super().__init__("localhost", timeout=timeout)
        self._sock = sock

    def connect(self) -> None:
        if self.timeout is not None:
            self._sock.settimeout(self.timeout)
        self.sock = self._sock


def _open(
    k8s: KubernetesClient, namespace: str, pod: str, timeout: float | None
) -> tuple[object, object, _SocketConn]:
    api = k8s.core_v1_portforward()
    pf = portforward(api.connect_get_namespaced_pod_portforward, pod, namespace, ports=str(_PORT))
    return api, pf, _SocketConn(pf.socket(_PORT), timeout)


def _close(api: object, pf: object, conn: _SocketConn) -> None:
    for shut in (conn.close, pf.close, api.api_client.close):
        with suppress(Exception):
            shut()


async def request(
    k8s: KubernetesClient,
    namespace: str,
    pod: str,
    method: str,
    path: str,
    body: dict | None = None,
    timeout: float = 120.0,
) -> tuple[int, bytes]:
    """One request/response round-trip to opencode serve (create/prompt/history)."""

    def call() -> tuple[int, bytes]:
        api, pf, conn = _open(k8s, namespace, pod, timeout)
        try:
            payload = json.dumps(body).encode() if body is not None else None
            headers = {"Content-Type": "application/json"} if payload is not None else {}
            conn.request(method, path, body=payload, headers=headers)
            resp = conn.getresponse()
            return resp.status, resp.read()
        finally:
            _close(api, pf, conn)

    return await asyncio.to_thread(call)


async def create_session(k8s: KubernetesClient, namespace: str, pod: str) -> tuple[int, bytes]:
    """Create a chat session and pin its model from `/config` (else `_FALLBACK_MODEL`) before the first
    prompt — see `_FALLBACK_MODEL` for why serve needs the pin."""
    status, data = await request(k8s, namespace, pod, "POST", "/api/session", body={})
    if not 200 <= status < 300:
        return status, data
    session_id = json.loads(data)["data"]["id"]
    _, cfg = await request(k8s, namespace, pod, "GET", "/config")
    model = (json.loads(cfg).get("model") if cfg else None) or _FALLBACK_MODEL
    provider, _, model_id = model.partition("/")  # "opencode/deepseek-v4-flash-free"
    if provider and model_id:
        await request(
            k8s, namespace, pod, "POST", f"/api/session/{session_id}/model",
            body={"model": {"id": model_id, "providerID": provider}},
        )
    return status, data


async def stream_events(
    k8s: KubernetesClient, namespace: str, pod: str, session_id: str
) -> AsyncIterator[bytes]:
    """Proxy opencode serve's per-session SSE stream. A reader thread pumps the blocking socket into a
    queue the caller drains — the same thread-bridge shape as the terminal's exec reader. `read1` forwards
    each burst as it arrives rather than buffering a full chunk (SSE must reach the browser live)."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    stop = threading.Event()

    def reader() -> None:
        api, pf, conn = _open(k8s, namespace, pod, None)
        try:
            conn.request(
                "GET", f"/api/session/{session_id}/event", headers={"Accept": "text/event-stream"}
            )
            resp = conn.getresponse()
            while not stop.is_set() and (chunk := resp.read1(_READ_SIZE)):
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception:  # socket died / stream ended
            pass
        finally:
            with suppress(RuntimeError):  # loop already closed
                loop.call_soon_threadsafe(queue.put_nowait, None)  # EOF sentinel
            _close(api, pf, conn)

    threading.Thread(target=reader, name=f"chat-{session_id}", daemon=True).start()
    try:
        while (chunk := await queue.get()) is not None:
            yield chunk
    finally:
        stop.set()
