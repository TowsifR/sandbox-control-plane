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
_RETRIES = 4  # a fresh port-forward tunnel occasionally drops/hangs before the first response; retry fresh
# opencode serve runs sessions on a paid model the free Zen key rejects, so we pin every session to this
# free one. (All personas use it; a per-persona model would add a flaky /config port-forward round-trip.)
_CHAT_MODEL = "opencode/deepseek-v4-flash-free"


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
    timeout: float = 15.0,
) -> tuple[int, bytes]:
    """One request/response round-trip to opencode serve. Calls are quick (a prompt returns at once, its
    reply arriving over the event stream), so the timeout is short and a hung tunnel is retried, not awaited."""

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

    last: Exception | None = None
    for _ in range(_RETRIES):
        try:
            return await asyncio.to_thread(call)
        except (OSError, http.client.HTTPException) as e:  # tunnel dropped mid-request — retry on a fresh one
            last = e
            await asyncio.sleep(0.3)
    raise last  # type: ignore[misc]


async def create_session(k8s: KubernetesClient, namespace: str, pod: str) -> tuple[int, bytes]:
    """Create a chat session and pin its model (`_CHAT_MODEL`) before the first prompt. Retried as a unit:
    a dropped tunnel can return a truncated body that won't parse, so a bad session id means try again."""
    provider, _, model_id = _CHAT_MODEL.partition("/")  # "opencode/deepseek-v4-flash-free"
    status, data = 502, b'{"detail":"agent unreachable"}'
    for _ in range(_RETRIES):
        status, data = await request(k8s, namespace, pod, "POST", "/api/session", body={})
        if 400 <= status < 500:
            return status, data  # a real rejection — retrying won't help
        try:
            session_id = json.loads(data)["data"]["id"]
        except (ValueError, KeyError, TypeError):
            continue  # truncated/garbled body — retry the whole create
        await request(
            k8s, namespace, pod, "POST", f"/api/session/{session_id}/model",
            body={"model": {"id": model_id, "providerID": provider}},
        )
        return status, data
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
