"""领域模型。

本模块刻意不 import astrbot / mcp / pywin32：
领域层只描述“一次仿真任务及其结果”，便于单测与未来替换后端。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import time
from typing import Any


class JobState(str, Enum):
    """与 multisim-mcp 一致的任务状态机。"""

    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    UNKNOWN = "unknown"

    @property
    def terminal(self) -> bool:
        return self in {
            JobState.SUCCEEDED,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.TIMED_OUT,
        }

    @classmethod
    def parse(cls, value: Any) -> "JobState":
        if isinstance(value, JobState):
            return value
        text = str(value or "").strip().lower()
        aliases = {
            "success": cls.SUCCEEDED,
            "completed": cls.SUCCEEDED,
            "complete": cls.SUCCEEDED,
            "done": cls.SUCCEEDED,
            "error": cls.FAILED,
            "failure": cls.FAILED,
            "timeout": cls.TIMED_OUT,
            "timed-out": cls.TIMED_OUT,
            "canceled": cls.CANCELLED,
            "pending": cls.QUEUED,
        }
        if text in aliases:
            return aliases[text]
        try:
            return cls(text)
        except ValueError:
            return cls.UNKNOWN


class VerificationStatus(str, Enum):
    """验收结论。unverified 绝不能当作成功。"""

    PASS = "pass"
    FAIL = "fail"
    UNVERIFIED = "unverified"

    @classmethod
    def parse(cls, value: Any) -> "VerificationStatus | None":
        if value is None:
            return None
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return None


@dataclass(slots=True)
class BackendReply:
    """一次上游工具调用的原始结果（已做 JSON 解析）。"""

    tool: str
    ok: bool
    data: Any = None
    text: str = ""
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False


@dataclass(slots=True)
class JobRecord:
    """插件侧记录的任务快照（上游 durable queue 才是权威）。"""

    job_id: str
    tool: str
    submitted_at: float = field(default_factory=time)
    state: JobState = JobState.QUEUED
    verification: str | None = None
    origin: str | None = None
    updated_at: float = field(default_factory=time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "tool": self.tool,
            "state": self.state.value,
            "verification": self.verification,
            "submitted_at": self.submitted_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class ToolBinding:
    """领域工具键 -> 上游 MCP 工具名的绑定结果。"""

    key: str
    backend_tool: str | None
    source: str  # "default" | "config" | "discovered" | "missing"

    @property
    def available(self) -> bool:
        return bool(self.backend_tool)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "backend_tool": self.backend_tool,
            "source": self.source,
            "available": self.available,
        }
