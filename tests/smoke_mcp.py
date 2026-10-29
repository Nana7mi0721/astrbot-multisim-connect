"""传输层冒烟测试：真实拉起一个 MCP stdio 子进程并调用工具。

前置：使用装有 `mcp` 的 Python（AstrBot 自带解释器即可）。
运行（仓库根目录）：
    python -m tests.smoke_mcp
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if __package__ in (None, ""):  # 支持 python tests/smoke_mcp.py 直接运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import ensure_package_importable

ensure_package_importable()

from astrbot_plugin_multisim.config import BackendSettings  # noqa: E402
from astrbot_plugin_multisim.infrastructure.mcp_backend import (  # noqa: E402
    McpStdioBackend,
)

FAKE_SERVER = str(Path(__file__).with_name("fake_mcp_server.py"))


async def main() -> int:
    settings = BackendSettings(python=sys.executable, args=[FAKE_SERVER], tool_profile="")
    backend = McpStdioBackend(settings)
    try:
        tools = await backend.list_tools()
        print("tools:", tools)
        assert "runtime_status" in tools, tools

        reply = await backend.call("runtime_status", {})
        print("runtime_status:", reply)
        assert reply.ok and reply.data.get("ready") is True, reply

        submitted = await backend.call("submit_circuit_experiment", {"netlist": "R1 1 0 1k"})
        assert submitted.ok and submitted.data["job_id"] == "smoke-job-1", submitted

        job = await backend.call("get_experiment_job", {"job_id": "smoke-job-1"})
        assert job.ok and job.data["state"] == "succeeded", job
        print("smoke OK")
        return 0
    finally:
        await backend.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
