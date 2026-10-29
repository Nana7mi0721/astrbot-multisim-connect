"""任务编排：提交、轮询、取消与插件侧缓存。

上游 multisim-mcp 已有 durable queue，这里不再实现第二套调度器；
缓存仅用于 `/ms jobs` 与“结束通知”。
"""

from __future__ import annotations

import asyncio
from time import time
from typing import Any, Awaitable, Callable

from ..domain import errors
from ..domain.models import JobRecord, JobState

Invoke = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]

_JOB_ID_KEYS = ("job_id", "jobId", "experiment_id", "experimentId", "id")
_STATE_KEYS = ("state", "status", "job_state", "jobStatus")
_VERIFICATION_KEYS = ("verification", "verification_status", "acceptance", "conclusion")


def _deep_find(value: Any, keys: tuple[str, ...], max_depth: int = 4) -> Any:
    """在嵌套 dict/list 中按广度优先查找第一个匹配键。"""
    queue: list[tuple[Any, int]] = [(value, 0)]
    while queue:
        current, depth = queue.pop(0)
        if depth > max_depth:
            continue
        if isinstance(current, dict):
            for key in keys:
                if key in current and current[key] not in (None, ""):
                    return current[key]
            queue.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            queue.extend((item, depth + 1) for item in current[:20])
    return None


def _extract_job_id(data: Any) -> str | None:
    value = _deep_find(data, _JOB_ID_KEYS)
    if value is None:
        return None
    return str(value)


def _extract_state(data: Any) -> JobState:
    return JobState.parse(_deep_find(data, _STATE_KEYS))


def _extract_verification(data: Any) -> str | None:
    value = _deep_find(data, _VERIFICATION_KEYS)
    if isinstance(value, dict):
        value = value.get("status") or value.get("result") or value.get("conclusion")
    if value is None:
        return None
    return str(value)


class JobService:
    def __init__(
        self,
        invoke: Invoke,
        *,
        poll_s: float = 2.0,
        timeout_s: float = 900.0,
        log: Callable[..., Any] | None = None,
    ) -> None:
        self._invoke = invoke
        self._poll_s = max(0.2, poll_s)
        self._timeout_s = max(5.0, timeout_s)
        self._log = log
        self._records: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    # ---------------------------------------------------------------- 缓存
    async def remember(self, record: JobRecord) -> None:
        async with self._lock:
            self._records[record.job_id] = record

    async def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        async with self._lock:
            records = sorted(
                self._records.values(), key=lambda r: r.submitted_at, reverse=True
            )
            return [record.to_dict() for record in records[: max(1, limit)]]

    async def active_ids(self) -> list[str]:
        async with self._lock:
            return [
                record.job_id
                for record in self._records.values()
                if not record.state.terminal
            ]

    # ---------------------------------------------------------------- 调用
    async def _invoke_job_tool(self, key: str, job_id: str) -> dict[str, Any]:
        payload = await self._invoke(key, {"job_id": job_id})
        # 上游不同版本可能用 experiment_id 命名
        if payload.get("ok") is False and payload.get("code") == "invalid_input":
            alternate = await self._invoke(key, {"experiment_id": job_id})
            if alternate.get("ok"):
                return alternate
        return payload

    async def submit(self, key: str, arguments: dict[str, Any]) -> dict[str, Any]:
        payload = await self._invoke(key, arguments)
        if not payload.get("ok"):
            return payload

        data = payload.get("data")
        job_id = _extract_job_id(data)
        if not job_id:
            raise errors.SimulationFailed(
                "后端未返回 job_id，无法跟踪任务",
                details={"tool": payload.get("tool"), "data": data},
            )
        state = _extract_state(data)
        await self.remember(JobRecord(job_id=job_id, tool=payload.get("tool", key), state=state))
        return {
            "ok": True,
            "job_id": job_id,
            "state": state.value,
            "verification": _extract_verification(data),
            "tool": payload.get("tool"),
            "data": data,
        }

    async def _normalize(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not payload.get("ok"):
            payload.setdefault("job_id", job_id)
            return payload
        data = payload.get("data")
        state = _extract_state(data)
        verification = _extract_verification(data)

        async with self._lock:
            record = self._records.get(job_id)
            if record is None:
                record = JobRecord(job_id=job_id, tool=payload.get("tool", ""))
                self._records[job_id] = record
            record.state = state
            record.verification = verification
            record.updated_at = time()

        return {
            "ok": True,
            "job_id": job_id,
            "state": state.value,
            "verification": verification,
            "tool": payload.get("tool"),
            "data": data,
        }

    async def get(self, job_id: str) -> dict[str, Any]:
        payload = await self._invoke_job_tool("get_job", job_id)
        return await self._normalize(job_id, payload)

    async def cancel(self, job_id: str) -> dict[str, Any]:
        payload = await self._invoke_job_tool("cancel_job", job_id)
        return await self._normalize(job_id, payload)

    async def list_jobs(self, limit: int = 10) -> dict[str, Any]:
        payload = await self._invoke("list_jobs", {"limit": max(1, int(limit))})
        if payload.get("ok") is False and payload.get("code") == "invalid_input":
            payload = await self._invoke("list_jobs", {})
        if payload.get("ok"):
            payload["cached"] = await self.recent(limit)
        return payload

    async def wait(
        self,
        job_id: str,
        *,
        timeout_s: float | None = None,
        poll_s: float | None = None,
    ) -> dict[str, Any]:
        timeout = timeout_s or self._timeout_s
        interval = poll_s or self._poll_s
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        last: dict[str, Any] = {"ok": False, "job_id": job_id, "code": "not_found"}

        while True:
            last = await self.get(job_id)
            if not last.get("ok"):
                return last
            state = JobState.parse(last.get("state"))
            if state.terminal:
                return last
            if loop.time() >= deadline:
                return {
                    "ok": False,
                    "job_id": job_id,
                    "code": "timeout",
                    "message": f"等待任务 {job_id} 超时（{timeout:.0f}s），任务可能仍在运行",
                    "retryable": True,
                    "state": state.value,
                    "last": last,
                }
            await asyncio.sleep(interval)
