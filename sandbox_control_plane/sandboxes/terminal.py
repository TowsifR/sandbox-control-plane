"""Terminal bridge: pump bytes between a WebSocket and a duplex byte stream.

Fake mode stands a local pty-backed shell in for the pod; the bridge shape is the
same one we later point at Kubernetes `pods/exec` — only the backing stream changes.
"""

import asyncio
import fcntl
import json
import os
import pty
import signal
import struct
import termios
import threading
from collections.abc import Awaitable, Callable
from contextlib import suppress

from fastapi import WebSocket
from kubernetes.stream import stream
from kubernetes.stream.ws_client import (
    ERROR_CHANNEL,
    RESIZE_CHANNEL,
    STDERR_CHANNEL,
    STDOUT_CHANNEL,
)
from websocket import WebSocketConnectionClosedException

from ..core.kubernetes import KubernetesClient

_READ_SIZE = 65536
_POLL = 0.2  # how long the reader thread blocks before rechecking `stop`
_JOIN_TIMEOUT = 2.0

# Exec injects no env, so TERM must be set here or bash assumes "dumb" — no colours, no `clear`.
# One exec, no probe round-trip: busybox has ash but no bash, the -slim images have both.
_SHELL = [
    "/bin/sh",
    "-c",
    "export TERM=xterm-256color; command -v bash >/dev/null 2>&1 && exec bash || exec sh",
]

OnInput = Callable[[bytes], Awaitable[bool]]  # False = the stream is gone, stop
OnControl = Callable[[bytes], Awaitable[None]]


def _terminal_size(control: bytes) -> tuple[int, int] | None:
    """Parse a control frame into (cols, rows); None if it isn't one."""
    try:
        msg = json.loads(control)
        return int(msg["cols"]), int(msg["rows"])
    except (ValueError, TypeError, KeyError):
        return None


def _exec_error(status: bytes) -> bytes | None:
    """Turn channel 3's metav1.Status into a line for the terminal, or None if it's unremarkable.

    Hand-parsed because WSClient.returncode int()s a field that only exists on NonZeroExitCode.
    """
    try:
        parsed = json.loads(status)
    except ValueError:
        return None
    # A shell exiting 1 is normal life, not something to editorialise about.
    if parsed.get("status") == "Success" or parsed.get("reason") == "NonZeroExitCode":
        return None
    return f"\r\n\x1b[31m{parsed.get('message', 'exec error')}\x1b[0m\r\n".encode()


def _exec_failure(e: BaseException) -> str:
    """What the apiserver actually said, dug out of the client's own broken error path.

    websocket_call raises ApiException(reason=..., body=None) and api_client's handler then
    calls body.decode() on that None — so what arrives is an AttributeError with the real
    exception one __context__ down. Its reason is "Handshake status N -+-+- headers -+-+- body".
    """
    reason = next(
        (str(r) for exc in (e, e.__context__) if (r := getattr(exc, "reason", None))), str(e)
    )
    parts = reason.split("-+-+-")
    # The body arrives as a bytes *repr*, so slice out the JSON rather than trusting the edges.
    with suppress(Exception):
        body = parts[-1]
        return json.loads(body[body.index("{") : body.rindex("}") + 1])["message"]
    return parts[0].strip() or str(e)


async def _fail(ws: WebSocket, message: str) -> None:
    """Report in-band: browsers don't surface WebSocket close reasons, so a close code alone
    leaves the user staring at a blank terminal."""
    with suppress(Exception):
        await ws.send_bytes(f"\r\n\x1b[31m{message}\x1b[0m\r\n".encode())
        await ws.close(code=1011)


async def _bridge(
    ws: WebSocket, outbound: asyncio.Queue[bytes], on_input: OnInput, on_control: OnControl
) -> None:
    """Pump `outbound` to the ws and ws frames to the stream until either ends — b"" is EOF.
    Text frames are keystrokes; binary frames are control JSON ({"cols": N, "rows": N}), which
    xterm.js never sends. Returns once one direction ends; the caller closes its own stream."""

    async def to_ws() -> None:
        while chunk := await outbound.get():
            await ws.send_bytes(chunk)

    async def from_ws() -> None:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                return
            if (control := msg.get("bytes")) is not None:
                await on_control(control)
            elif (text := msg.get("text")) and not await on_input(text.encode()):
                return

    tasks = [asyncio.create_task(to_ws()), asyncio.create_task(from_ws())]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    for task in done:
        task.exception()  # the bridge is over either way; reading it just silences asyncio's warning


def _set_winsize(fd: int, cols: int, rows: int) -> None:
    # struct winsize is (rows, cols, xpixel, ypixel) — the order flips, it isn't a typo.
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


async def _wait_writable(loop: asyncio.AbstractEventLoop, fd: int) -> None:
    """Suspend until the pty accepts input again (its buffer drained)."""
    future = loop.create_future()

    def on_writable() -> None:
        if not future.done():
            future.set_result(None)

    loop.add_writer(fd, on_writable)
    try:
        await future
    finally:
        loop.remove_writer(fd)


async def _write_all(loop: asyncio.AbstractEventLoop, fd: int, data: bytes) -> None:
    """Write every byte to the non-blocking fd — os.write can write short, or raise
    BlockingIOError once the pty's input buffer fills (a big paste outruns the shell)."""
    view = memoryview(data)
    while view:
        try:
            written = os.write(fd, view)
        except BlockingIOError:
            await _wait_writable(loop, fd)
            continue
        view = view[written:]


async def run_local_pty(ws: WebSocket, command: list[str] | None = None) -> None:
    """Spawn `command` (argv; defaults to a shell) in a pty and bridge it to an accepted WebSocket."""
    candidates = [command] if command else [["/bin/bash"], ["/bin/sh"]]
    pid, fd = pty.fork()
    if pid == 0:  # child: become the command (execvp replaces the forked image)
        os.environ["TERM"] = "xterm-256color"
        for argv in candidates:
            try:
                os.execvp(argv[0], argv)
            except FileNotFoundError:
                continue
        os._exit(1)  # nothing executable found

    os.set_blocking(fd, False)
    loop = asyncio.get_running_loop()
    outbound: asyncio.Queue[bytes] = asyncio.Queue()  # pty -> ws, order-preserving

    def on_readable() -> None:
        try:
            data = os.read(fd, _READ_SIZE)
        except BlockingIOError:
            return
        except OSError:  # pty closed (child exited) -> EIO
            data = b""
        outbound.put_nowait(data)  # b"" is the EOF sentinel

    loop.add_reader(fd, on_readable)

    async def on_input(data: bytes) -> bool:
        try:
            await _write_all(loop, fd, data)
        except OSError:  # pty closed (child exited) -> EIO
            return False
        return True

    async def on_control(control: bytes) -> None:
        if size := _terminal_size(control):
            _set_winsize(fd, *size)

    try:
        await _bridge(ws, outbound, on_input, on_control)
    finally:
        loop.remove_reader(fd)
        os.close(fd)
        try:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        except (ProcessLookupError, ChildProcessError):
            pass
        try:
            await ws.close()
        except RuntimeError:  # already closed
            pass


async def run_pod_exec(
    ws: WebSocket,
    k8s: KubernetesClient,
    namespace: str,
    pod: str,
    container: str,
    command: list[str] | None = None,
) -> None:
    """Exec a shell in `pod` and bridge it to an accepted WebSocket.

    Same shape as run_local_pty — only the producer differs: the official client's WSClient
    is a blocking poll, so a thread feeds the queue where the pty uses loop.add_reader.
    """
    loop = asyncio.get_running_loop()
    api = k8s.core_v1_exec()
    try:
        wsc = await asyncio.to_thread(
            stream,
            api.connect_get_namespaced_pod_exec,
            pod,
            namespace,
            container=container,
            command=command or _SHELL,
            stdin=True,
            stdout=True,
            stderr=False,  # the apiserver rejects stderr together with tty
            tty=True,
            binary=True,  # keep bytes end to end; otherwise it utf-8 decodes each frame
            _preload_content=False,  # hand back the WSClient rather than a buffered response
        )
    except Exception as e:
        # RBAC denial, unknown container and "pod not running" all fail the handshake. Catch
        # broadly: the client mangles its own ApiException into an AttributeError (see
        # _exec_failure), and either way the user wants a message, not a stack trace.
        await _fail(ws, f"exec failed: {_exec_failure(e)}")
        api.api_client.close()
        return

    outbound: asyncio.Queue[bytes] = asyncio.Queue()  # exec -> ws, order-preserving
    stop = threading.Event()

    def reader() -> None:
        try:
            while not stop.is_set() and wsc.is_open():
                wsc.update(timeout=_POLL)  # bounded: an unbounded poll would never see `stop`
                for channel in (STDOUT_CHANNEL, STDERR_CHANNEL):
                    if data := wsc.read_channel(channel):
                        loop.call_soon_threadsafe(outbound.put_nowait, data)
                if (status := wsc.read_channel(ERROR_CHANNEL)) and (msg := _exec_error(status)):
                    loop.call_soon_threadsafe(outbound.put_nowait, msg)
        except Exception:  # socket died under us; the sentinel below ends the bridge
            pass
        finally:
            with suppress(RuntimeError):  # loop already closed
                loop.call_soon_threadsafe(outbound.put_nowait, b"")  # b"" is the EOF sentinel

    thread = threading.Thread(target=reader, name=f"exec-{pod}", daemon=True)
    thread.start()

    async def on_input(data: bytes) -> bool:
        try:
            await asyncio.to_thread(wsc.write_stdin, data)
        except WebSocketConnectionClosedException:
            return False
        return True

    async def on_control(control: bytes) -> None:
        if size := _terminal_size(control):
            cols, rows = size
            # Go's remotecommand.TerminalSize — capitalised, or it unmarshals to zero silently.
            payload = json.dumps({"Width": cols, "Height": rows}).encode()
            with suppress(WebSocketConnectionClosedException):
                await asyncio.to_thread(wsc.write_channel, RESIZE_CHANNEL, payload)

    try:
        await _bridge(ws, outbound, on_input, on_control)
    finally:
        stop.set()
        # Join before closing: the reader is polling this socket's fd, and close-vs-poll races.
        await asyncio.to_thread(thread.join, _JOIN_TIMEOUT)
        await asyncio.to_thread(wsc.close)  # the apiserver reaps the shell; the pod is untouched
        api.api_client.close()
        with suppress(RuntimeError):  # already closed
            await ws.close()
