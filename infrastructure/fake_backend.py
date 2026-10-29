"""确定性假后端。

用途：
- 单测（不依赖 mcp SDK / Multisim）；
- `backend.mode: fake` 时用于演示插件界面与命令流。
"""

from __future__ import annotations

import time
from typing import Any

from ..domain.models import BackendReply

_FAKE_TOOLS = [
    "runtime_status",
    "submit_circuit_experiment",
    "run_verified_circuit_experiment",
    "get_experiment_job",
    "list_experiment_jobs",
    "cancel_experiment_job",
    "get_experiment_summary",
    "submit_experiment_sweep",
    "export_formal_experiment_report",
    "open_circuit_file",
    "set_component_value",
    "list_components",
    "run_spice_netlist",
    "save_circuit_as",
]


class FakeBackend:
    def __init__(self, *, job_terminal_after: int = 1) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False
        self._job_counter = 0
        self._jobs: dict[str, dict[str, Any]] = {}
        self._polls = 0
        self._job_terminal_after = job_terminal_after

    async def list_tools(self) -> list[str]:
        return list(_FAKE_TOOLS)

    async def call(
        self,
        tool: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> BackendReply:
        args = dict(arguments or {})
        self.calls.append((tool, args))
        handler = getattr(self, f"_tool_{tool}", None)
        if handler is None:
            return BackendReply(tool=tool, ok=True, data={"echo": args})
        return handler(args)

    async def close(self) -> None:
        self.closed = True

    async def restart(self) -> None:
        pass

    # ---------------------------------------------------------------- 工具实现
    def _tool_runtime_status(self, args: dict[str, Any]) -> BackendReply:
        return BackendReply(
            tool="runtime_status",
            ok=True,
            data={
                "schema_version": 1,
                "api_name": "multisim-mcp-agent-api",
                "api_version": 1,
                "mode": "fake",
                "ready": True,
            },
        )

    def _tool_submit_circuit_experiment(self, args: dict[str, Any]) -> BackendReply:
        self._job_counter += 1
        job_id = f"fake-job-{self._job_counter}"
        self._jobs[job_id] = {"polls": 0, "request": args}
        return BackendReply(
            tool="submit_circuit_experiment",
            ok=True,
            data={"job_id": job_id, "state": "queued"},
        )

    _tool_run_verified_circuit_experiment = _tool_submit_circuit_experiment
    _tool_submit_experiment_sweep = _tool_submit_circuit_experiment

    def _tool_get_experiment_job(self, args: dict[str, Any]) -> BackendReply:
        job_id = str(args.get("job_id") or args.get("experiment_id") or "")
        job = self._jobs.get(job_id)
        if job is None:
            return BackendReply(
                tool="get_experiment_job",
                ok=False,
                error_code="not_found",
                error_message=f"任务不存在：{job_id}",
            )
        job["polls"] += 1
        state = "succeeded" if job["polls"] >= self._job_terminal_after else "running"
        data: dict[str, Any] = {"job_id": job_id, "state": state}
        if state == "succeeded":
            data["verification"] = "pass"
            data["measurements"] = {"V(out)": 5.0}
            data["artifacts"] = [{"path": "runs/fake/vout.csv", "kind": "csv"}]
        return BackendReply(tool="get_experiment_job", ok=True, data=data)

    def _tool_list_experiment_jobs(self, args: dict[str, Any]) -> BackendReply:
        jobs = [{"job_id": key, "state": "succeeded"} for key in self._jobs]
        return BackendReply(tool="list_experiment_jobs", ok=True, data={"jobs": jobs})

    def _tool_cancel_experiment_job(self, args: dict[str, Any]) -> BackendReply:
        job_id = str(args.get("job_id") or args.get("experiment_id") or "")
        if job_id in self._jobs:
            self._jobs[job_id]["state"] = "cancelled"
            return BackendReply(
                tool="cancel_experiment_job",
                ok=True,
                data={"job_id": job_id, "state": "cancelled"},
            )
        return BackendReply(
            tool="cancel_experiment_job",
            ok=False,
            error_code="not_found",
            error_message=f"任务不存在：{job_id}",
        )

    def _tool_get_experiment_summary(self, args: dict[str, Any]) -> BackendReply:
        job_id = str(args.get("job_id") or args.get("experiment_id") or "")
        return BackendReply(
            tool="get_experiment_summary",
            ok=True,
            data={
                "job_id": job_id,
                "verification": "unverified",
                "artifacts": [],
                "checked_at": time.time(),
            },
        )

    def _tool_export_formal_experiment_report(self, args: dict[str, Any]) -> BackendReply:
        return BackendReply(
            tool="export_formal_experiment_report",
            ok=True,
            data={"report": "runs/fake/report.md"},
        )

    def _tool_open_circuit_file(self, args: dict[str, Any]) -> BackendReply:
        return BackendReply(
            tool="open_circuit_file",
            ok=True,
            data={"opened": args.get("path"), "mode": "fake"},
        )

    def _tool_set_component_value(self, args: dict[str, Any]) -> BackendReply:
        return BackendReply(
            tool="set_component_value",
            ok=True,
            data={"applied": args, "mode": "fake"},
        )

    def _tool_list_components(self, args: dict[str, Any]) -> BackendReply:
        return BackendReply(
            tool="list_components",
            ok=True,
            data={"components": [{"refdes": "R1", "value": 1000.0, "unit": "ohm"}]},
        )

    def _tool_run_spice_netlist(self, args: dict[str, Any]) -> BackendReply:
        return BackendReply(
            tool="run_spice_netlist",
            ok=True,
            data={"analysis": args.get("commands"), "mode": "fake"},
        )

    def _tool_save_circuit_as(self, args: dict[str, Any]) -> BackendReply:
        return BackendReply(
            tool="save_circuit_as",
            ok=True,
            data={"saved": args.get("path"), "mode": "fake"},
        )
