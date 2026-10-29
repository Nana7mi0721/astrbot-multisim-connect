"""面向插件的仿真服务门面。

职责：
- 惰性发现上游工具并建立 ToolMap；
- 把每次调用归一化成统一 JSON 契约；
- 路径沙箱、特性开关、任务缓存。
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from ..config import PluginSettings
from ..domain import errors
from ..domain.models import BackendReply
from ..infrastructure.tool_map import ToolMap
from .backend import MultisimBackend
from .job_service import JobService
from .path_policy import WorkspacePathPolicy

PLUGIN_VERSION = "0.1.0"


class SimulationService:
    def __init__(
        self,
        backend: MultisimBackend,
        settings: PluginSettings,
        policy: WorkspacePathPolicy,
        log: Callable[..., Any] | None = None,
    ) -> None:
        self._backend = backend
        self._settings = settings
        self._policy = policy
        self._log = log
        self._toolmap: ToolMap | None = None
        self._toolmap_lock = asyncio.Lock()
        self._jobs = JobService(
            self._invoke,
            poll_s=settings.job_poll_s,
            timeout_s=settings.job_timeout_s,
            log=log,
        )

    # ---------------------------------------------------------------- 基础设施
    async def ensure_ready(self) -> ToolMap:
        async with self._toolmap_lock:
            if self._toolmap is None:
                available = await self._backend.list_tools()
                self._toolmap = ToolMap(available, self._settings.tool_map_overrides)
            return self._toolmap

    async def refresh_tools(self) -> ToolMap:
        available = await self._backend.list_tools()
        self._toolmap = ToolMap(available, self._settings.tool_map_overrides)
        return self._toolmap

    def _config_summary(self) -> dict[str, Any]:
        backend = self._settings.backend
        return {
            "mode": backend.mode,
            "executable": backend.executable,
            "args": backend.resolved_args(),
            "tool_profile": backend.tool_profile,
            "workspace_root": str(self._policy.root),
        }

    async def _invoke(
        self,
        key: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        toolmap = await self.ensure_ready()
        try:
            tool = toolmap.require(key)
        except errors.ToolUnavailable as exc:
            return exc.to_dict()

        reply: BackendReply = await self._backend.call(
            tool, arguments or {}, timeout=timeout or self._settings.call_timeout_s
        )
        return self._payload(key, tool, reply)

    @staticmethod
    def _payload(key: str, tool: str, reply: BackendReply) -> dict[str, Any]:
        if reply.ok:
            return {
                "ok": True,
                "key": key,
                "tool": tool,
                "data": reply.data if reply.data is not None else reply.text,
            }
        err = errors.from_backend_code(
            reply.error_code, reply.error_message, retryable=reply.retryable
        )
        payload = err.to_dict()
        payload.update({"key": key, "tool": tool})
        if reply.data is not None:
            payload["backend"] = reply.data
        return payload

    # ---------------------------------------------------------------- 状态
    async def status(self) -> dict[str, Any]:
        config = self._config_summary()
        try:
            toolmap = await self.refresh_tools()
        except errors.MultisimError as exc:
            payload = exc.to_dict()
            payload["config"] = config
            return payload
        except Exception as exc:  # 兜底，避免 /ms status 崩溃
            payload = errors.BackendUnavailable(f"后端不可用：{exc}").to_dict()
            payload["config"] = config
            return payload

        payload: dict[str, Any] = {
            "ok": True,
            "plugin_version": PLUGIN_VERSION,
            "config": config,
            "tool_count": len(toolmap.available),
            "tool_map": toolmap.report(),
            "missing_tools": toolmap.missing(),
        }
        runtime = await self._invoke("runtime_status", {}, timeout=min(30.0, self._settings.call_timeout_s))
        payload["runtime"] = runtime
        if runtime.get("ok") is False:
            payload["ok"] = False
            return payload

        runtime_data = runtime.get("data")
        runtime_data = runtime_data if isinstance(runtime_data, dict) else {}
        mode = runtime_data.get("runtime_mode")
        compatible = runtime_data.get("runtime_compatible")
        payload["runtime_mode"] = mode
        payload["multisim_ready"] = (
            mode != "introspection-only" and compatible is not False
        )
        return payload

    # ---------------------------------------------------------------- 实验
    def _prepare_request(
        self,
        request: dict[str, Any],
        output_dir: str | None,
    ) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise errors.InvalidRequest("request 必须是 JSON 对象")
        prepared = dict(request)
        target = output_dir
        if not target and isinstance(prepared.get("output_dir"), str):
            target = prepared["output_dir"]
        if target:
            prepared["output_dir"] = str(self._policy.ensure_output_dir(target))
        return prepared

    async def submit_experiment(
        self,
        request: dict[str, Any],
        *,
        output_dir: str | None = None,
        verified: bool = False,
    ) -> dict[str, Any]:
        prepared = self._prepare_request(request, output_dir)
        if verified:
            return await self._jobs.submit("run_verified", {"spec": prepared})
        return await self._jobs.submit("submit_experiment", prepared)

    async def run_sweep(
        self,
        request: dict[str, Any],
        *,
        output_dir: str | None = None,
    ) -> dict[str, Any]:
        if not self._settings.allow_sweep:
            raise errors.PermissionDenied("参数扫描已在插件配置中禁用")
        prepared = self._prepare_request(request, output_dir)
        return await self._jobs.submit("run_sweep", prepared)

    async def get_job(self, job_id: str) -> dict[str, Any]:
        return await self._jobs.get(job_id)

    async def list_jobs(self, limit: int = 10) -> dict[str, Any]:
        return await self._jobs.list_jobs(limit)

    async def cancel_job(self, job_id: str) -> dict[str, Any]:
        return await self._jobs.cancel(job_id)

    async def wait_job(
        self,
        job_id: str,
        *,
        timeout_s: float | None = None,
        poll_s: float | None = None,
    ) -> dict[str, Any]:
        return await self._jobs.wait(job_id, timeout_s=timeout_s, poll_s=poll_s)

    async def get_summary(self, job_id: str) -> dict[str, Any]:
        payload = await self._invoke("get_summary", {"job_id": job_id})
        if payload.get("ok") is False and payload.get("code") == "invalid_input":
            payload = await self._invoke("get_summary", {"experiment_id": job_id})
        return payload

    async def export_report(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise errors.InvalidRequest("request 必须是 JSON 对象")
        return await self._invoke("export_report", dict(request))

    # ---------------------------------------------------------------- 原生电路操作
    async def open_circuit(self, path: str) -> dict[str, Any]:
        resolved = self._policy.resolve(path, must_exist=True)
        return await self._invoke("open_circuit", {"path": str(resolved)})

    async def set_component_value(
        self, refdes: str, value: float, property_name: str = "value"
    ) -> dict[str, Any]:
        if not self._settings.allow_component_edit:
            raise errors.PermissionDenied("元件参数修改已在插件配置中禁用")
        if not refdes.strip():
            raise errors.InvalidRequest("refdes 不能为空")
        return await self._invoke(
            "set_component_value",
            {"refdes": refdes.strip(), "value": float(value), "property": property_name},
        )

    async def list_components(self) -> dict[str, Any]:
        return await self._invoke("list_components", {})

    async def run_spice(self, request: dict[str, Any]) -> dict[str, Any]:
        """把 SPICE/Nutmeg 请求原样转发给上游（上游默认仅允许 op/dc/ac/tran）。"""
        if not isinstance(request, dict):
            raise errors.InvalidRequest("request 必须是 JSON 对象")
        return await self._invoke("run_spice", dict(request))

    async def save_circuit(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise errors.InvalidRequest("request 必须是 JSON 对象")
        return await self._invoke("save_circuit", dict(request))

    # ---------------------------------------------------------------- 停止/关闭
    async def stop(self, *, restart: bool = False) -> dict[str, Any]:
        cancelled: list[str] = []
        failed: list[dict[str, Any]] = []
        for job_id in await self._jobs.active_ids():
            try:
                payload = await self._jobs.cancel(job_id)
                if payload.get("ok"):
                    cancelled.append(job_id)
                else:
                    failed.append({"job_id": job_id, "code": payload.get("code")})
            except errors.MultisimError as exc:
                failed.append({"job_id": job_id, "code": exc.code, "message": exc.message})
        if restart:
            await self._backend.restart()
        return {"ok": True, "cancelled": cancelled, "failed": failed, "restarted": restart}

    async def close(self) -> None:
        await self._backend.close()
