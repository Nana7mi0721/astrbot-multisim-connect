"""后端窄接口。

infrastructure 实现它；application 只依赖这个 Protocol。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..domain.models import BackendReply


@runtime_checkable
class MultisimBackend(Protocol):
    async def list_tools(self) -> list[str]:
        """返回上游 MCP 工具名列表。"""

    async def call(
        self,
        tool: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> BackendReply:
        """调用一个上游工具。工具级错误通过 BackendReply.ok=False 表达。"""

    async def close(self) -> None:
        """释放连接/子进程。"""

    async def restart(self) -> None:
        """重启后端（下一次调用时惰性重建）。"""
