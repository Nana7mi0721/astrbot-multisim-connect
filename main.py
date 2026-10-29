"""AstrBot Multisim 插件入口。

架构：
    AstrBot 插件 (64-bit) --MCP stdio--> multisim-mcp --COM--> Multisim 14.3

本模块只做“装配 + 面向 Agent/用户的薄接口”：
- domain/ 纯模型与错误
- application/ 编排与路径策略
- infrastructure/ MCP 客户端与工具映射

AstrBot 的命令与 LLM 工具装饰器必须定义在 Star 子类所在的模块（main.py），
因此这里同时承载 15 个 LLM 工具与 /ms 命令。
"""

from __future__ import annotations

import asyncio
import json
import shlex
from typing import Any, Awaitable, Callable

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, StarTools

from .application.path_policy import WorkspacePathPolicy
from .application.simulation_service import SimulationService
from .config import PluginSettings
from .domain import errors
from .infrastructure.fake_backend import FakeBackend
from .infrastructure.mcp_backend import McpStdioBackend

PLUGIN_NAME = "astrbot_plugin_multisim"


def _dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str, indent=None)


def _pretty(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str, indent=2)


def _split_args(text: str) -> list[str]:
    try:
        parts = shlex.split(text, posix=False)
    except ValueError:
        parts = text.split()
    return [part.strip('"').strip("'") for part in parts]


def _as_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


class MultisimPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self.settings = PluginSettings.from_dict(self.config)
        self.data_dir = StarTools.get_data_dir(PLUGIN_NAME)
        self.policy = WorkspacePathPolicy(
            self.settings.resolved_workspace_root(self.data_dir)
        )
        self._service: SimulationService | None = None
        self._service_lock = asyncio.Lock()
        self._watchers: set[asyncio.Task] = set()

    # ---------------------------------------------------------------- 生命周期
    async def initialize(self) -> None:
        logger.info(
            "[Multisim] 已加载：后端=%s，解释器=%s，工作区=%s",
            self.settings.backend.mode,
            self.settings.backend.executable,
            self.policy.root,
        )

    async def terminate(self) -> None:
        for task in list(self._watchers):
            if not task.done():
                task.cancel()
        if self._watchers:
            await asyncio.gather(*self._watchers, return_exceptions=True)
        self._watchers.clear()
        if self._service is not None:
            try:
                await self._service.close()
            except Exception as exc:  # 卸载阶段只记录，不抛出
                logger.warning("[Multisim] 关闭后端时出错：%s", exc)
            self._service = None
        logger.info("[Multisim] 插件已卸载")

    # ---------------------------------------------------------------- 内部装配
    async def _get_service(self) -> SimulationService:
        async with self._service_lock:
            if self._service is None:
                if self.settings.backend.mode == "fake":
                    backend = FakeBackend()
                else:
                    backend = McpStdioBackend(
                        self.settings.backend,
                        log=logger,
                        extra_env=self.settings.backend_env(),
                    )
                self._service = SimulationService(
                    backend, self.settings, self.policy, log=logger
                )
            return self._service

    async def _run(
        self, action: Callable[[SimulationService], Awaitable[dict[str, Any]]]
    ) -> str:
        """执行一次服务调用并序列化为统一契约；异常不外抛到 agent loop。"""
        try:
            service = await self._get_service()
            payload = await action(service)
        except errors.MultisimError as exc:
            payload = exc.to_dict()
        except Exception as exc:  # 兜底：未知异常也给出结构化结果
            logger.exception("[Multisim] 工具执行异常")
            payload = {
                "ok": False,
                "code": "internal_error",
                "message": str(exc),
                "retryable": False,
            }
        return _dumps(payload)

    # ================================================================ LLM 工具
    @filter.llm_tool(name="multisim_status")
    async def multisim_status(self, event: AstrMessageEvent) -> str:
        """检查 NI Multisim 自动化后端是否就绪，并列出后端工具映射情况。

        在任何仿真操作之前先调用本工具。返回 ok=false 时不要继续提交实验，
        应先把错误信息转告用户。
        """
        return await self._run(lambda svc: svc.status())

    @filter.llm_tool(name="multisim_submit_experiment")
    async def multisim_submit_experiment(
        self,
        event: AstrMessageEvent,
        request: dict,
        output_dir: str = "",
    ) -> str:
        """提交一个电路仿真实验（异步任务，立即返回 job_id）。

        request 会原样转发给 multisim-mcp 的 submit_circuit_experiment，
        字段以该后端契约为准（netlist / commands / analyses 等）。
        提交后使用 multisim_get_job 轮询，完成后用 multisim_get_summary 取测量值与产物。

        Args:
            request(object): 实验请求对象，原样转发给上游 submit_circuit_experiment
            output_dir(string): 输出目录（工作区内相对路径），留空由后端决定
        """
        return await self._run(
            lambda svc: svc.submit_experiment(request, output_dir=output_dir or None)
        )

    @filter.llm_tool(name="multisim_run_verified")
    async def multisim_run_verified(
        self,
        event: AstrMessageEvent,
        spec: dict,
        output_dir: str = "",
    ) -> str:
        """提交“带验收要求”的实验（ExperimentSpec），返回 job_id。

        spec 会以 {"spec": ...} 转发给 run_verified_circuit_experiment；
        其中 requirements 用于自动测量并给出 pass / fail / unverified 结论。
        unverified 表示未验证通过，绝不能当作成功。

        Args:
            spec(object): ExperimentSpec（含 netlist、requirements 等）
            output_dir(string): 输出目录（工作区内相对路径）
        """
        return await self._run(
            lambda svc: svc.submit_experiment(
                spec, output_dir=output_dir or None, verified=True
            )
        )

    @filter.llm_tool(name="multisim_get_job")
    async def multisim_get_job(self, event: AstrMessageEvent, job_id: str) -> str:
        """查询任务状态：queued / running / succeeded / failed / cancelled / timed_out。

        Args:
            job_id(string): 提交实验时返回的任务 ID
        """
        return await self._run(lambda svc: svc.get_job(job_id))

    @filter.llm_tool(name="multisim_list_jobs")
    async def multisim_list_jobs(self, event: AstrMessageEvent, limit: int = 10) -> str:
        """列出近期实验任务。

        Args:
            limit(int): 返回条数上限，默认 10
        """
        return await self._run(lambda svc: svc.list_jobs(limit))

    @filter.llm_tool(name="multisim_cancel_job")
    async def multisim_cancel_job(self, event: AstrMessageEvent, job_id: str) -> str:
        """取消一个正在运行或排队中的任务。

        Args:
            job_id(string): 任务 ID
        """
        return await self._run(lambda svc: svc.cancel_job(job_id))

    @filter.llm_tool(name="multisim_get_summary")
    async def multisim_get_summary(self, event: AstrMessageEvent, job_id: str) -> str:
        """获取任务的结果摘要：测量值、验收结论与产物列表。

        Args:
            job_id(string): 任务 ID
        """
        return await self._run(lambda svc: svc.get_summary(job_id))

    @filter.llm_tool(name="multisim_run_sweep")
    async def multisim_run_sweep(
        self,
        event: AstrMessageEvent,
        request: dict,
        output_dir: str = "",
    ) -> str:
        """提交参数扫描任务（最多 100 个扫描点），返回 job_id。

        request 会原样转发给 multisim-mcp 的 submit_experiment_sweep。

        Args:
            request(object): 扫描计划对象（参数、范围、步数等，以上游契约为准）
            output_dir(string): 输出目录（工作区内相对路径）
        """
        return await self._run(
            lambda svc: svc.run_sweep(request, output_dir=output_dir or None)
        )

    @filter.llm_tool(name="multisim_export_report")
    async def multisim_export_report(self, event: AstrMessageEvent, request: dict) -> str:
        """导出正式实验报告。

        request 会原样转发给 export_formal_experiment_report
        （通常包含实验目录或任务 ID，以上游契约为准）。

        Args:
            request(object): 报告导出请求对象
        """
        return await self._run(lambda svc: svc.export_report(request))

    @filter.llm_tool(name="multisim_open_circuit")
    async def multisim_open_circuit(self, event: AstrMessageEvent, path: str) -> str:
        """在 Multisim 中打开一个已有电路文件（.ms14）。

        路径必须位于插件工作区内。

        Args:
            path(string): 电路文件路径（相对工作区或工作区内绝对路径）
        """
        return await self._run(lambda svc: svc.open_circuit(path))

    @filter.llm_tool(name="multisim_set_component_value")
    async def multisim_set_component_value(
        self,
        event: AstrMessageEvent,
        refdes: str,
        value: float,
        property_name: str = "value",
    ) -> str:
        """修改当前已打开电路中某个元件的参数（如电阻值）。

        仿真运行中通常不允许结构性修改；如失败请先停止仿真再重试。

        Args:
            refdes(string): 元件位号，例如 R1
            value(number): 新的数值（基本单位，如 1000 表示 1kΩ）
            property_name(string): 属性名，默认 value
        """
        return await self._run(
            lambda svc: svc.set_component_value(refdes, value, property_name)
        )

    @filter.llm_tool(name="multisim_list_components")
    async def multisim_list_components(self, event: AstrMessageEvent) -> str:
        """列出当前已打开电路中的元件及其参数。"""
        return await self._run(lambda svc: svc.list_components())

    @filter.llm_tool(name="multisim_run_spice")
    async def multisim_run_spice(self, event: AstrMessageEvent, request: dict) -> str:
        """执行 SPICE / Nutmeg 请求（原样转发给上游工具）。

        上游默认只允许 op / dc / ac / tran 分析；任意命令文件需要显式开启
        `features.allow_unsafe_commands`。

        Args:
            request(object): SPICE 请求对象（netlist / commands 等，以上游契约为准）
        """
        return await self._run(lambda svc: svc.run_spice(request))

    @filter.llm_tool(name="multisim_save_circuit")
    async def multisim_save_circuit(self, event: AstrMessageEvent, request: dict) -> str:
        """另存当前电路（原样转发给上游保存工具）。

        Args:
            request(object): 保存请求对象（目标路径、是否覆盖等，以上游契约为准）
        """
        return await self._run(lambda svc: svc.save_circuit(request))

    @filter.llm_tool(name="multisim_stop")
    async def multisim_stop(self, event: AstrMessageEvent, restart: bool = False) -> str:
        """停止所有活动任务；可选重启后端连接（用于 COM 卡死时恢复）。

        Args:
            restart(bool): 是否重启 multisim-mcp 连接，默认 false
        """
        return await self._run(lambda svc: svc.stop(restart=restart))

    # ================================================================ 用户命令
    @filter.command("ms", alias={"/ms"})
    async def ms_command(self, event: AstrMessageEvent):
        """Multisim 控制台。

        用法：/ms status | jobs [N] | job <id> | cancel <id> | summary <id> |
              run <spec.json> [--watch|--no-watch] [--out DIR] |
              sweep <spec.json> | tools | doctor | stop [restart]
        """
        argv = _split_args(event.message_str.strip())
        if argv and argv[0].lstrip("/").lower() == "ms":
            argv = argv[1:]
        sub = argv[0].lower() if argv else "status"
        args = argv[1:]
        try:
            text = await self._handle_ms(sub, args, event)
        except errors.MultisimError as exc:
            text = f"{exc.code}: {exc.message}"
        except Exception as exc:
            logger.exception("[Multisim] 命令执行异常")
            text = f"执行失败：{exc}"
        yield event.plain_result(text)

    async def _handle_ms(
        self, sub: str, args: list[str], event: AstrMessageEvent
    ) -> str:
        service = await self._get_service()

        if sub in {"status", "doctor"}:
            payload = await service.status()
            if sub == "doctor":
                try:
                    toolmap = await service.refresh_tools()
                    names = toolmap.available
                    payload["available_tools"] = (
                        names[:60] + ([f"...(+{len(names) - 60})"] if len(names) > 60 else [])
                    )
                except errors.MultisimError as exc:
                    payload.setdefault("backend_error", exc.to_dict())
                return _pretty(payload)
            return self._format_status(payload)

        if sub == "tools":
            toolmap = await service.refresh_tools()
            names = toolmap.available
            shown = names[:80] + ([f"...(+{len(names) - 80})"] if len(names) > 80 else [])
            return f"上游工具 {len(names)} 个：\n" + "\n".join(shown)

        if sub == "jobs":
            payload = await service.list_jobs(_as_int(args[0] if args else None, 10))
            if not payload.get("ok"):
                return self._format_error_payload(payload)
            data = payload.get("data")
            cached = payload.get("cached") or []
            lines = ["近期任务（插件缓存）："]
            if cached:
                lines.extend(
                    f"- {item['job_id']}  {item['state']}" for item in cached
                )
            else:
                lines.append("- 无")
            if data is not None:
                lines.append("\n后端返回：")
                lines.append(_pretty(data))
            return "\n".join(lines)

        if sub == "job":
            if not args:
                return "用法：/ms job <id>"
            return _pretty(await service.get_job(args[0]))

        if sub == "cancel":
            if not args:
                return "用法：/ms cancel <id>"
            return _pretty(await service.cancel_job(args[0]))

        if sub == "summary":
            if not args:
                return "用法：/ms summary <id>"
            return _pretty(await service.get_summary(args[0]))

        if sub in {"run", "sweep"}:
            if not args:
                return f"用法：/ms {sub} <spec.json> [--watch|--no-watch] [--out DIR]"
            return await self._handle_submit(sub, args, event)

        if sub == "stop":
            restart = bool(args and args[0].lower() == "restart")
            return _pretty(await service.stop(restart=restart))

        return (
            "未知子命令。可用：status / jobs / job / cancel / summary / "
            "run / sweep / tools / doctor / stop"
        )

    async def _handle_submit(
        self, sub: str, args: list[str], event: AstrMessageEvent
    ) -> str:
        spec_path = args[0]
        watch = self.settings.auto_watch
        output_dir: str | None = None
        index = 1
        while index < len(args):
            flag = args[index].lower()
            if flag == "--watch":
                watch = True
            elif flag == "--no-watch":
                watch = False
            elif flag == "--out" and index + 1 < len(args):
                output_dir = args[index + 1]
                index += 1
            else:
                return f"未知参数：{args[index]}"
            index += 1

        resolved = self.policy.resolve(spec_path, must_exist=True)
        raw = await asyncio.to_thread(resolved.read_text, encoding="utf-8")
        try:
            request = json.loads(raw)
        except ValueError as exc:
            raise errors.InvalidRequest(f"spec 不是合法 JSON：{exc}") from exc
        if not isinstance(request, dict):
            raise errors.InvalidRequest("spec 必须是 JSON 对象")

        service = await self._get_service()
        if sub == "run":
            payload = await service.submit_experiment(request, output_dir=output_dir)
        else:
            payload = await service.run_sweep(request, output_dir=output_dir)

        if not payload.get("ok"):
            return self._format_error_payload(payload)

        job_id = payload.get("job_id", "")
        text = f"已提交任务 {job_id}（状态：{payload.get('state', 'unknown')}）。\n"
        text += f"查询：/ms job {job_id}　结果：/ms summary {job_id}"
        if watch and job_id:
            self._start_watcher(event.unified_msg_origin, job_id)
            text += "\n已开启结果推送，任务结束后会在此会话通知。"
        return text

    # ---------------------------------------------------------------- 展示辅助
    @staticmethod
    def _format_status(payload: dict[str, Any]) -> str:
        if not payload.get("ok"):
            message = payload.get("message") or "后端不可用"
            code = payload.get("code") or "error"
            return f"Multisim 未就绪：{code} — {message}"

        config = payload.get("config") or {}
        missing = payload.get("missing_tools") or []
        runtime = payload.get("runtime") or {}
        runtime_ok = runtime.get("ok", False)
        runtime_data = runtime.get("data")
        runtime_data = runtime_data if isinstance(runtime_data, dict) else {}
        lines = [
            "Multisim 后端：已连接",
            f"模式：{config.get('mode')}　工具数：{payload.get('tool_count', 0)}",
            f"工作区：{config.get('workspace_root')}",
        ]
        if not runtime_ok:
            lines.append("运行状态：异常")
        elif payload.get("multisim_ready"):
            lines.append(f"自动化：就绪（{payload.get('runtime_mode') or 'native'}）")
        else:
            lines.append(
                f"自动化：未就绪（{payload.get('runtime_mode') or 'unknown'}，仅 MCP 自省）"
            )
            reason = runtime_data.get("runtime_message") or runtime_data.get("worker_error")
            if reason:
                lines.append(f"原因：{str(reason)[:200]}")
            if runtime_data.get("required_python_bits") == 32:
                lines.append(
                    "修复：安装 32 位 Python + pywin32，并在 backend.env 设置 "
                    "MULTISIM_MCP_WORKER_PYTHON"
                )
        if missing:
            lines.append("缺失工具：" + ", ".join(missing))
        lines.append("详细诊断：/ms doctor")
        return "\n".join(lines)

    @staticmethod
    def _format_error_payload(payload: dict[str, Any]) -> str:
        code = payload.get("code", "error")
        message = payload.get("message", "")
        retryable = "可重试" if payload.get("retryable") else "不可重试"
        return f"失败：{code}（{retryable}）\n{message}"

    # ---------------------------------------------------------------- 结束推送
    def _start_watcher(self, umo: str, job_id: str) -> None:
        task = asyncio.create_task(
            self._watch_job(umo, job_id), name=f"multisim-watch-{job_id}"
        )
        self._watchers.add(task)
        task.add_done_callback(self._watchers.discard)

    async def _watch_job(self, umo: str, job_id: str) -> None:
        try:
            service = await self._get_service()
            payload = await service.wait_job(
                job_id,
                timeout_s=self.settings.job_timeout_s,
                poll_s=self.settings.job_poll_s,
            )
            if payload.get("ok"):
                text = f"[Multisim] 任务 {job_id} 已结束：{payload.get('state')}"
                verification = payload.get("verification")
                if verification:
                    text += f"；验证结论：{verification}"
                    if str(verification).strip().lower() == "unverified":
                        text += "（未验证通过，不能视为成功）"
            else:
                text = (
                    f"[Multisim] 任务 {job_id} 未完成："
                    f"{payload.get('code')} — {payload.get('message')}"
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            text = f"[Multisim] 任务 {job_id} 监控失败：{exc}"

        try:
            await self.context.send_message(umo, MessageChain().message(text))
        except Exception as exc:
            logger.warning("[Multisim] 结果推送失败（%s）：%s", umo, exc)
