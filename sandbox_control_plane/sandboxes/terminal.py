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
from collections.abc import Awaitable, Callable

from fastapi import WebSocket

_READ_SIZE = 65536

OnInput = Callable[[bytes], Awaitable[bool]]  # False = the stream is gone, stop
OnControl = Callable[[bytes], Awaitable[None]]


def _terminal_size(control: bytes) -> tuple[int, int] | None:
    """Parse a control frame into (cols, rows); None if it isn't one."""
    try:
        msg = json.loads(control)
        return int(msg["cols"]), int(msg["rows"])
    except (ValueError, TypeError, KeyError):
        return None


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
