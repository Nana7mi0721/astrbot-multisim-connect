"""工作区路径策略：模型给出的任何路径都必须落在 workspace_root 内。"""

from __future__ import annotations

from pathlib import Path

from ..domain.errors import InvalidRequest, PermissionDenied


class WorkspacePathPolicy:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def resolve(self, raw: str | Path, *, must_exist: bool = False) -> Path:
        """把相对路径解析到工作区；拒绝穿越与工作区外路径。"""
        text = str(raw).strip()
        if not text:
            raise InvalidRequest("路径不能为空")
        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise PermissionDenied(
                f"路径不在工作区内：{resolved}",
                details={"workspace_root": str(self.root)},
            )
        if must_exist and not resolved.exists():
            raise InvalidRequest(f"文件不存在：{resolved}")
        return resolved

    def ensure_output_dir(self, raw: str | Path | None, job_hint: str = "") -> Path:
        """解析并创建输出目录；为空时在工作区下创建按任务区分的目录。"""
        if raw:
            target = self.resolve(raw)
        else:
            target = self.root / "runs" / job_hint if job_hint else self.root / "runs"
        target.mkdir(parents=True, exist_ok=True)
        return target
