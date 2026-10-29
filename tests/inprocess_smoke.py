"""进程内插件冒烟：用 fake 后端直接实例化插件并调用 LLM 工具。

需要 AstrBot 运行环境（只为验证 Star 生命周期与装饰器接线，不连接真实 Multisim）：
    python -m tests.inprocess_smoke
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):  # 支持 python tests/inprocess_smoke.py 直接运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import ensure_package_importable

ensure_package_importable()

# 独立运行时定位 AstrBot 源码（插件被 AstrBot 加载时不需要）
_CANDIDATES = (
    os.environ.get("ASTRBOT_APP", ""),
    r"D:\Program\AstrBot\backend\app",
    "/opt/AstrBot/backend/app",
)
for _path in _CANDIDATES:
    if _path and os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from astrbot.core.star.star_tools import StarTools


def _patch_data_dir() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="multisim-plugin-smoke-"))
    StarTools.get_data_dir = classmethod(lambda cls, plugin_name=None: tmp)  # type: ignore[assignment]
    return tmp


class _FakeEvent:
    def __init__(self, message: str) -> None:
        self.message_str = message
        self.unified_msg_origin = "webchat:FriendMessage:smoke"

    def plain_result(self, text: str) -> str:
        return text


async def main() -> int:
    _patch_data_dir()
    from astrbot_plugin_multisim.main import MultisimPlugin

    plugin = MultisimPlugin(context=None, config={"backend": {"mode": "fake"}})
    await plugin.initialize()
    try:
        status = json.loads(await plugin.multisim_status(None))
        print("status:", status["ok"], status["tool_count"])
        assert status["ok"]

        submitted = json.loads(
            await plugin.multisim_submit_experiment(
                None, {"netlist": "R1 in out 1k", "commands": "dc VIN 0 10 1"}, "runs/smoke"
            )
        )
        print("submitted:", submitted)
        assert submitted["ok"], submitted
        job_id = submitted["job_id"]

        job = json.loads(await plugin.multisim_get_job(None, job_id))
        print("job:", job["state"], job["verification"])
        assert job["ok"] and job["state"] == "succeeded"

        summary = json.loads(await plugin.multisim_get_summary(None, job_id))
        assert summary["ok"], summary

        component = json.loads(
            await plugin.multisim_set_component_value(None, "R1", 2200.0)
        )
        print("set_component_value:", component["ok"])
        assert component["ok"]

        # 命令通道
        results = []
        async for chunk in plugin.ms_command(_FakeEvent("/ms status")):
            results.append(chunk)
        print("command status:", results[0].splitlines()[0])
        assert "Multisim 后端" in results[0]

        results = []
        async for chunk in plugin.ms_command(_FakeEvent("/ms jobs 5")):
            results.append(chunk)
        assert "近期任务" in results[0]

        print("in-process smoke OK")
        return 0
    finally:
        await plugin.terminate()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
