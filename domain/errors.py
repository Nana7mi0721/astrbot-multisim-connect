"""统一错误类型与上游错误码映射。

对外契约（工具返回值）始终是：
    {"ok": false, "code": ..., "message": ..., "retryable": ...}
上游原始 code 尽量原样保留，不吞诊断信息。
"""

from __future__ import annotations

from typing import Any


class MultisimError(Exception):
    code: str = "runtime_error"
    retryable: bool = False
    default_message: str = "Multisim 后端调用失败"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        retryable: bool | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        self.details = details or None
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.details:
            payload["details"] = self.details
        return payload


class BackendUnavailable(MultisimError):
    code = "backend_unavailable"
    retryable = True
    default_message = "无法连接 Multisim 后端（multisim-mcp）"


class MultisimNotReady(MultisimError):
    code = "multisim_not_ready"
    retryable = True
    default_message = "Multisim 尚未就绪（未安装 / 未授权 / COM 不可用）"


class InvalidRequest(MultisimError):
    code = "invalid_input"
    default_message = "请求参数无效"


class PermissionDenied(MultisimError):
    code = "permission_denied"
    default_message = "操作被插件策略拒绝"


class NotFound(MultisimError):
    code = "not_found"
    default_message = "目标不存在"


class SimulationFailed(MultisimError):
    code = "simulation_failed"
    default_message = "仿真执行失败"


class JobTimedOut(MultisimError):
    code = "timeout"
    retryable = True
    default_message = "操作超时"


class JobCancelled(MultisimError):
    code = "cancelled"
    default_message = "任务已取消"


class ArtifactUnavailable(MultisimError):
    code = "artifact_unavailable"
    default_message = "产物不可用"


class ToolUnavailable(MultisimError):
    code = "tool_unavailable"
    default_message = "所请求的后端工具不可用"


_BY_CODE: dict[str, type[MultisimError]] = {
    cls.code: cls
    for cls in (
        BackendUnavailable,
        MultisimNotReady,
        InvalidRequest,
        PermissionDenied,
        NotFound,
        SimulationFailed,
        JobTimedOut,
        JobCancelled,
        ArtifactUnavailable,
        ToolUnavailable,
    )
}


def from_backend_code(
    code: str | None,
    message: str | None = None,
    *,
    retryable: bool | None = None,
) -> MultisimError:
    """把上游错误码映射为领域错误；未知码保留原样。"""
    key = (code or "").strip().lower()
    cls = _BY_CODE.get(key)
    if cls is None:
        err = MultisimError(message, code=key or "runtime_error", retryable=retryable)
        if retryable is None:
            err.retryable = key in {"timeout", "backend_unavailable"}
        return err
    return cls(message, retryable=retryable)
