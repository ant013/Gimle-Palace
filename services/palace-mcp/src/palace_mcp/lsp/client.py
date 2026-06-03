"""Minimal async LSP JSON-RPC client over stdio subprocess.

Implements Content-Length framing per LSP specification.
Handles server→client requests by echoing null results (e.g. client/registerCapability).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_HEADER_SEP = b"\r\n\r\n"
_CONTENT_LENGTH_PREFIX = b"Content-Length: "


class LspError(Exception):
    """Raised when the LSP server returns an error response."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class LspClient:
    """Async LSP client wrapping a sourcekit-lsp subprocess.

    Usage::

        async with LspClient(binary, workspace_root) as client:
            results = await client.prepare_call_hierarchy(file_uri, line, char)
    """

    def __init__(
        self,
        binary: str,
        workspace_root: str,
        scratch_path: str | None = None,
        index_store_path: str | None = None,
        index_db_path: str | None = None,
        log_level: str = "error",
    ) -> None:
        self._binary = binary
        self._workspace_root = workspace_root
        self._scratch_path = scratch_path
        self._index_store_path = index_store_path
        self._index_db_path = index_db_path
        self._log_level = log_level
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "LspClient":
        await self.start()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.stop()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        args = [self._binary, "--log-level", self._log_level]
        if self._scratch_path:
            args += ["--scratch-path", self._scratch_path]
        if self._index_store_path:
            args += ["-index-store-path", self._index_store_path]
        if self._index_db_path:
            args += ["-index-db-path", self._index_db_path]
        self._proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env={**os.environ},
        )
        self._reader_task = asyncio.ensure_future(self._reader_loop())
        await self._initialize()

    async def stop(self) -> None:
        try:
            await self._request("shutdown", {})
        except Exception:
            pass
        try:
            await self._notify("exit", {})
        except Exception:
            pass
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._proc is not None and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=3.0)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Initialize
    # ------------------------------------------------------------------

    async def _initialize(self) -> None:
        workspace_uri = _path_to_uri(self._workspace_root)
        result = await self._request(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": workspace_uri,
                "capabilities": {
                    "textDocument": {
                        "callHierarchy": {"dynamicRegistration": False},
                        "synchronization": {"dynamicRegistration": False},
                    },
                    "window": {"workDoneProgress": False},
                },
                "workspaceFolders": [
                    {"uri": workspace_uri, "name": "workspace"}
                ],
            },
        )
        logger.debug("LSP initialize result: %s", result.get("serverInfo"))
        await self._notify("initialized", {})

    # ------------------------------------------------------------------
    # High-level operations
    # ------------------------------------------------------------------

    async def did_open(self, file_uri: str, content: str) -> None:
        """Notify server of an open file (required before call hierarchy)."""
        await self._notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": file_uri,
                    "languageId": "swift",
                    "version": 1,
                    "text": content,
                }
            },
        )

    async def prepare_call_hierarchy(
        self, file_uri: str, line: int, character: int
    ) -> list[dict[str, Any]]:
        """Issue textDocument/prepareCallHierarchy; returns item list (may be empty)."""
        result = await self._request(
            "textDocument/prepareCallHierarchy",
            {
                "textDocument": {"uri": file_uri},
                "position": {"line": line, "character": character},
            },
        )
        if result is None:
            return []
        return result if isinstance(result, list) else [result]

    async def incoming_calls(
        self, item: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Issue callHierarchy/incomingCalls for a prepared item."""
        result = await self._request(
            "callHierarchy/incomingCalls",
            {"item": item},
        )
        if result is None:
            return []
        return result if isinstance(result, list) else [result]

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    async def _request(
        self, method: str, params: dict[str, Any], timeout: float = 60.0
    ) -> Any:
        async with self._lock:
            req_id = self._next_id
            self._next_id += 1
            fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
            self._pending[req_id] = fut

        await self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise LspError(f"LSP request '{method}' timed out after {timeout}s")

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _send(self, message: dict[str, Any]) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        body = json.dumps(message).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._proc.stdin.write(header + body)
        await self._proc.stdin.drain()

    async def _reader_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        reader = self._proc.stdout
        while True:
            try:
                # Read headers until \r\n\r\n
                header_bytes = await reader.readuntil(_HEADER_SEP)
                # Extract Content-Length
                content_length = _parse_content_length(header_bytes)
                if content_length is None:
                    logger.warning("LSP: no Content-Length in header, skipping")
                    continue
                body = await reader.readexactly(content_length)
                msg = json.loads(body.decode("utf-8"))
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
                break
            except Exception as exc:
                logger.debug("LSP reader error: %s", exc)
                break

            msg_id = msg.get("id")
            method = msg.get("method")

            if method is not None and msg_id is not None:
                # Server→client request: respond with null result to unblock it
                await self._send(
                    {"jsonrpc": "2.0", "id": msg_id, "result": None}
                )
            elif msg_id is not None and "result" in msg:
                fut = self._pending.pop(msg_id, None)
                if fut is not None and not fut.done():
                    fut.set_result(msg["result"])
            elif msg_id is not None and "error" in msg:
                fut = self._pending.pop(msg_id, None)
                if fut is not None and not fut.done():
                    err = msg["error"]
                    fut.set_exception(
                        LspError(err.get("message", "unknown"), err.get("code"))
                    )
            # Notifications (no id, has method) are silently dropped

        # Cancel all pending futures on disconnect
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()


def _path_to_uri(path: str) -> str:
    """Convert an absolute filesystem path to a file:// URI."""
    return "file://" + path.rstrip("/")


def _parse_content_length(header: bytes) -> int | None:
    for line in header.split(b"\r\n"):
        if line.startswith(_CONTENT_LENGTH_PREFIX):
            try:
                return int(line[len(_CONTENT_LENGTH_PREFIX):].strip())
            except ValueError:
                return None
    return None
