"""领域工具 -> 上游 MCP 工具名 的映射与启动时校验。

核心工具名来自 multisim-mcp 的 Agent API（已核实）；原生电路编辑工具
在不同版本/工具轮廓下名称可能不同，因此用启发式发现 + 配置覆盖。
"""

from __future__ import annotations

from typing import Iterable

from ..domain.errors import ToolUnavailable
from ..domain.models import ToolBinding

# 已在 multisim-mcp 1.3 Agent API 文档中核实过的工具名
CORE_DEFAULTS: dict[str, str] = {
    "runtime_status": "runtime_status",
    "submit_experiment": "submit_circuit_experiment",
    "run_verified": "run_verified_circuit_experiment",
    "get_job": "get_experiment_job",
    "list_jobs": "list_experiment_jobs",
    "cancel_job": "cancel_experiment_job",
    "get_summary": "get_experiment_summary",
    "run_sweep": "submit_experiment_sweep",
    "export_report": "export_formal_experiment_report",
}

# 原生电路编辑工具：候选项按“名字同时包含所有 token”匹配
DISCOVERY_HINTS: dict[str, tuple[tuple[str, ...], ...]] = {
    "open_circuit": (
        ("open", "circuit"),
        ("open", "design"),
        ("open", "file"),
    ),
    "set_component_value": (
        ("set", "rlc"),
        ("set", "component"),
        ("replace", "component"),
        ("component", "value"),
    ),
    "list_components": (
        ("enum", "component"),
        ("list", "components"),
        ("component", "list"),
    ),
    "run_spice": (
        ("run", "spice"),
        ("spice", "netlist"),
        ("simulate", "spice"),
        ("nutmeg",),
        ("command", "line"),
    ),
    "save_circuit": (
        ("save", "circuit"),
        ("save", "as"),
        ("save", "design"),
        ("save", "project"),
    ),
}


def _match(tool: str, tokens: Iterable[str]) -> bool:
    lowered = tool.lower()
    return all(token in lowered for token in tokens)


class ToolMap:
    """把领域键解析成上游工具名。

    available 为空表示“未知”（未连接后端），此时只有默认映射可用。
    """

    def __init__(
        self,
        available_tools: list[str] | None = None,
        overrides: dict[str, str] | None = None,
    ) -> None:
        self.available = list(available_tools or [])
        self.overrides = dict(overrides or {})
        self._bindings: dict[str, ToolBinding] = {}
        self._resolve_all()

    def _resolve_all(self) -> None:
        keys = set(CORE_DEFAULTS) | set(DISCOVERY_HINTS) | set(self.overrides)
        for key in sorted(keys):
            self._bindings[key] = self._bind(key)

    def _bind(self, key: str) -> ToolBinding:
        override = self.overrides.get(key)
        if override:
            return ToolBinding(key, override, "config")
        default = CORE_DEFAULTS.get(key)
        if default and (not self.available or default in self.available):
            return ToolBinding(key, default, "default")
        if self.available:
            discovered = self._discover(key)
            if discovered:
                return ToolBinding(key, discovered, "discovered")
        if default:
            # 已连接但上游没有该工具：视为缺失，而不是硬失败
            return ToolBinding(key, None, "missing")
        return ToolBinding(key, None, "missing")

    def _discover(self, key: str) -> str | None:
        """按提示组的先后顺序匹配；同组内优先最短、且含 multisim 的名字。"""
        hints = DISCOVERY_HINTS.get(key)
        if not hints:
            return None
        for tokens in hints:
            candidates = [tool for tool in self.available if _match(tool, tokens)]
            if candidates:
                return min(
                    candidates,
                    key=lambda name: (
                        0 if "multisim" in name.lower() else 1,
                        len(name),
                        name,
                    ),
                )
        return None

    def binding(self, key: str) -> ToolBinding:
        return self._bindings.get(key) or ToolBinding(key, None, "missing")

    def require(self, key: str) -> str:
        binding = self.binding(key)
        if not binding.backend_tool:
            raise ToolUnavailable(
                f"上游没有可用的工具：{key}",
                details={
                    "key": key,
                    "available_tools": self.available[:80],
                    "hint": "可在插件配置 tool_map 中显式指定上游工具名",
                },
            )
        return binding.backend_tool

    def report(self) -> dict[str, dict]:
        return {key: binding.to_dict() for key, binding in self._bindings.items()}

    def missing(self) -> list[str]:
        return [key for key, binding in self._bindings.items() if not binding.available]
