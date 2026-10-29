"""MCP stdio 后端客户端。

设计要点：
- 整个连接（子进程 + 会话）由一个长期任务持有，进出都在同一任务内完成，
  避免 anyio cancel scope 跨任务问题；
- 所有调用经单一队列串行执行（Multisim COM 本身只能串行）；
- 子进程退出 / 启动失败时给出结构化 backend_unavailable，下一次调用自动重启。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Callable

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..config import BackendSettings
from ..domain import errors
from ..domain.models import BackendReply


@dataclass(slots=True)
class _Request:
    future: asyncio.Future
    method: str  # "call" | "list_tools"
    tool: str | None
    arguments: dict[str, Any] | None
    timeout: float | None


def _describe_exc(exc: BaseException) -> str:
    """展开 anyio TaskGroup 的 ExceptionGroup，拿到最内层原因。"""
    children = getattr(exc, "exceptions", None)
    if children:
        return _describe_exc(children[0])
    return f"{type(exc).__name__}: {exc}"


def _reply_from_result(tool: str, result: Any) -> BackendReply:
    texts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            texts.append(text)
    text = "\n".join(texts).strip()

    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)

    parsed: Any = None
    if text:
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None

    data = structured if structured is not None else (parsed if parsed is not None else text)

    is_error = bool(getattr(result, "isError", False) or getattr(result, "is_error", False))
    if not is_error:
        return BackendReply(tool=tool, ok=True, data=data, text=text)

    code = "runtime_error"
    message = text or "上游工具返回错误"
    retryable = False
    if isinstance(parsed, dict):
        code = str(parsed.get("code") or parsed.get("error") or code)
        message = str(parsed.get("message") or message)
        retryable = bool(parsed.get("retryable", retryable))
    return BackendReply(
        tool=tool,
        ok=False,
        data=parsed,
        text=text,
        error_code=code,
        error_message=message,
        retryable=retryable,
    )


class McpStdioBackend:
    def __init__(
        self,
        settings: BackendSettings,
        log: Callable[..., Any] | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self._settings = settings
        self._log = log
        self._extra_env = dict(extra_env or {})
        self._task: asyncio.Task | None = None
        self._queue: asyncio.Queue[_Request | None] = asyncio.Queue()
        self._ready = asyncio.Event()
        self._start_lock = asyncio.Lock()
        self._fatal: str | None = None
        self._tools: list[str] = []

    # ---------------------------------------------------------------- 生命周期
    async def _run(self) -> None:
        try:
            async with AsyncExitStack() as stack:
                transport = await stack.enter_async_context(
                    stdio_client(self._server_params())
                )
                read_stream, write_stream = transport
                session = await stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                await session.initialize()
                listed = await session.list_tools()
                self._tools = [tool.name for tool in listed.tools]
                self._ready.set()
                if self._log:
                    self._log.info(
                        "[Multisim] multisim-mcp 已连接，可用工具 %d 个",
                        len(self._tools),
                    )
                while True:
                    item = await self._queue.get()
                    if item is None:
                        break
                    if item.future.cancelled():
                        continue
                    try:
                        if item.method == "list_tools":
                            result = await session.list_tools()
                            names = [tool.name for tool in result.tools]
                            self._tools = names
                            item.future.set_result(names)
                        else:
                            coro = session.call_tool(item.tool or "", item.arguments or {})
                            if item.timeout:
                                result = await asyncio.wait_for(coro, timeout=item.timeout)
                            else:
                                result = await coro
                            item.future.set_result(_reply_from_result(item.tool or "", result))
                    except asyncio.TimeoutError:
                        if not item.future.done():
                            item.future.set_exception(
                                errors.JobTimedOut(
                                    f"后端调用超时：{item.tool}（{item.timeout:.0f}s）"
                                )
                            )
                    except Exception as exc:
                        # 工具级错误会以 isError 结果返回；这里的异常通常意味着
                        # 连接/协议已损坏，标记致命并退出循环，下一次调用自动重启。
                        self._fatal = _describe_exc(exc)
                        if not item.future.done():
                            item.future.set_exception(
                                errors.BackendUnavailable(f"后端调用失败：{exc}")
                            )
                        break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._fatal = _describe_exc(exc)
            if self._log:
                self._log.warning("[Multisim] multisim-mcp 会话异常退出：%s", self._fatal)
        finally:
            self._ready.clear()
            while True:
                try:
                    item = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if item is None or item.future.done():
                    continue
                item.future.set_exception(
                    errors.BackendUnavailable(self._fatal or "后端连接已关闭")
                )

    def _server_params(self) -> StdioServerParameters:
        env = dict(os.environ)
        env.update(self._extra_env)
        return StdioServerParameters(
            command=self._settings.executable,
            args=self._settings.resolved_args(),
            env=env,
        )

    async def _ensure_started(self) -> None:
        async with self._start_lock:
            if self._task and not self._task.done() and self._ready.is_set():
                return
            await self._stop_task()
            self._fatal = None
            self._ready.clear()
            self._task = asyncio.create_task(self._run(), name="multisim-mcp-stdio")

            loop = asyncio.get_running_loop()
            deadline = loop.time() + max(1.0, self._settings.start_timeout_s)
            while loop.time() < deadline:
                if self._ready.is_set():
                    return
                if self._task.done():
                    break
                await asyncio.sleep(0.05)
            if self._ready.is_set():
                return

            reason = self._fatal or (
                "multisim-mcp 进程已退出" if self._task.done() else "multisim-mcp 启动超时"
            )
            await self._stop_task()
            raise errors.BackendUnavailable(
                f"{reason}。请确认已安装 multisim-mcp 且 backend.python / args 配置正确。",
                details={
                    "executable": self._settings.executable,
                    "args": self._settings.resolved_args(),
                },
            )

    async def _stop_task(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        if task.done():
            with contextlib.suppress(asyncio.CancelledError, Exception):
                task.result()
            return
        with contextlib.suppress(Exception):
            await self._queue.put(None)
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=10)
        except asyncio.TimeoutError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        except asyncio.CancelledError:
            task.cancel()
            raise
        except Exception:
            pass

    # ---------------------------------------------------------------- 对外接口
    async def list_tools(self) -> list[str]:
        await self._ensure_started()
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        await self._queue.put(_Request(future, "list_tools", None, None, 15.0))
        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            future.cancel()
            raise errors.JobTimedOut("获取工具列表超时")

    async def call(
        self,
        tool: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> BackendReply:
        await self._ensure_started()
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        await self._queue.put(_Request(future, "call", tool, arguments, timeout))
        wait_s = (timeout or 1800.0) + 30.0
        try:
            return await asyncio.wait_for(future, timeout=wait_s)
        except asyncio.TimeoutError:
            future.cancel()
            raise errors.JobTimedOut(f"等待后端响应超时：{tool}")

    async def restart(self) -> None:
        await self._stop_task()

    async def close(self) -> None:
        await self._stop_task()
