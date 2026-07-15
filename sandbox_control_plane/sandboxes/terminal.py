"""Terminal bridge: pump bytes between a WebSocket and a duplex byte stream.

Fake mode stands a local pty-backed shell in for the pod; the bridge shape is the
same one we later point at Kubernetes `pods/exec` — only the backing stream changes.
"""

import asyncio
import os
import pty
import signal

from fastapi import WebSocket

_READ_SIZE = 65536


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

    async def pty_to_ws() -> None:
        while chunk := await outbound.get():
            await ws.send_bytes(chunk)

    async def ws_to_pty() -> None:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                return
            data = msg.get("bytes")
            if data is None and msg.get("text") is not None:
                data = msg["text"].encode()
            if data:
                try:
                    await _write_all(loop, fd, data)
                except OSError:  # pty closed (child exited) -> EIO
                    return

    tasks = [asyncio.create_task(pty_to_ws()), asyncio.create_task(ws_to_pty())]
    try:
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
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
