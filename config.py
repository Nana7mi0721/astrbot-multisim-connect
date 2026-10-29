"""配置解析。

AstrBot 传入的 config 是 AstrBotConfig（dict 子类），缺 key 时返回 None，
因此这里全部走容错读取，不依赖 key 一定存在。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

DEFAULT_ARGS = ["-m", "multisim_mcp.server"]


def _section(raw: Mapping[str, Any] | None, key: str) -> Mapping[str, Any]:
    value = (raw or {}).get(key)
    return value if isinstance(value, Mapping) else {}


def _str(section: Mapping[str, Any], key: str, default: str) -> str:
    value = section.get(key, default)
    return value.strip() if isinstance(value, str) else default


def _float(section: Mapping[str, Any], key: str, default: float) -> float:
    try:
        return float(section.get(key, default))
    except (TypeError, ValueError):
        return default


def _bool(section: Mapping[str, Any], key: str, default: bool) -> bool:
    value = section.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _str_list(section: Mapping[str, Any], key: str, default: list[str]) -> list[str]:
    value = section.get(key, default)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    return list(default)


def _str_dict(section: Mapping[str, Any], key: str) -> dict[str, str]:
    value = section.get(key, {})
    if isinstance(value, Mapping):
        return {str(k): str(v) for k, v in value.items() if str(v).strip()}
    return {}


@dataclass(slots=True)
class BackendSettings:
    mode: str = "mcp_stdio"
    python: str = ""
    args: list[str] = field(default_factory=lambda: list(DEFAULT_ARGS))
    tool_profile: str = "full"
    env: dict[str, str] = field(default_factory=dict)
    start_timeout_s: float = 30.0

    @property
    def executable(self) -> str:
        return self.python or sys.executable

    def resolved_args(self) -> list[str]:
        args = list(self.args)
        if self.tool_profile and "--tool-profile" not in args:
            args.extend(["--tool-profile", self.tool_profile])
        return args


@dataclass(slots=True)
class PluginSettings:
    backend: BackendSettings = field(default_factory=BackendSettings)
    workspace_root: str = ""
    call_timeout_s: float = 60.0
    job_poll_s: float = 2.0
    job_timeout_s: float = 900.0
    allow_component_edit: bool = True
    allow_sweep: bool = True
    allow_unsafe_commands: bool = False
    auto_watch: bool = True
    tool_map_overrides: dict[str, str] = field(default_factory=dict)

    def backend_env(self) -> dict[str, str]:
        env = dict(self.backend.env)
        if self.allow_unsafe_commands:
            env.setdefault("MULTISIM_MCP_ENABLE_UNSAFE_COMMANDS", "1")
        return env

    def resolved_workspace_root(self, data_dir: Path) -> Path:
        if self.workspace_root:
            return Path(self.workspace_root).expanduser()
        return data_dir / "workspace"

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> "PluginSettings":
        backend_raw = _section(raw, "backend")
        timeouts = _section(raw, "timeouts")
        features = _section(raw, "features")
        mode = _str(backend_raw, "mode", "mcp_stdio")
        if mode not in {"mcp_stdio", "fake"}:
            mode = "mcp_stdio"
        profile = _str(backend_raw, "tool_profile", "full")
        if profile not in {"full", "experiment", "optimization", "core"}:
            profile = "full"
        return cls(
            backend=BackendSettings(
                mode=mode,
                python=_str(backend_raw, "python", ""),
                args=_str_list(backend_raw, "args", DEFAULT_ARGS),
                tool_profile=profile,
                env=_str_dict(backend_raw, "env"),
                start_timeout_s=_float(backend_raw, "start_timeout_s", 30.0),
            ),
            workspace_root=_str(raw, "workspace_root", ""),
            call_timeout_s=_float(timeouts, "call_timeout_s", 60.0),
            job_poll_s=max(0.2, _float(timeouts, "job_poll_s", 2.0)),
            job_timeout_s=_float(timeouts, "job_timeout_s", 900.0),
            allow_component_edit=_bool(features, "allow_component_edit", True),
            allow_sweep=_bool(features, "allow_sweep", True),
            allow_unsafe_commands=_bool(features, "allow_unsafe_commands", False),
            auto_watch=_bool(features, "auto_watch", True),
            tool_map_overrides=_str_dict(raw, "tool_map"),
        )
