# 贡献指南

欢迎 Issue 与 PR。这个插件的目标是「薄而稳」：把 COM 与仿真细节留给上游 `multisim-mcp`，插件只维护领域工具面、权限、路径沙箱与结果契约。

## 开发环境

| 依赖 | 用途 |
|---|---|
| Python 3.10+（64 位） | 运行插件与单测 |
| AstrBot ≥ 4.16 | 进程内冒烟（`tests/inprocess_smoke.py`） |
| `mcp` SDK 1.x 或 2.x | 传输层冒烟（`tests/smoke_mcp.py`） |
| Multisim 14.3 + 32 位 worker | 只有真实联调才需要 |

仓库根目录就是插件根目录；本地调试时可克隆到 AstrBot 的 `data/plugins/astrbot_plugin_multisim`（目录名必须是这个）。

## 测试

```bash
# 单元测试：不需要 AstrBot / mcp / Multisim
python -m unittest discover -s tests -t .

# 传输层：真实拉起一个 MCP stdio 子进程（fake server，不需要 Multisim）
python -m tests.smoke_mcp

# 进程内：Star 生命周期、LLM 工具注册、/ms 命令（需要 AstrBot 运行环境）
python -m tests.inprocess_smoke
```

改动涉及真实后端时，另附 `/ms doctor` 输出与复现步骤。

## 代码约定

- 分层：`main.py`（展示）→ `application/`（编排）→ `domain/`（纯模型）。`domain/` 不 import `astrbot`、`mcp`、`win32`。
- 对外返回值统一走 `domain/errors.py` 的契约：`{"ok": false, "code", "message", "retryable"}`。
- 不吞上游诊断：错误码尽量原样保留，附加信息放 `backend` 字段。
- LLM 工具的参数必须写进 docstring 的 `Args:` 段（AstrBot 靠它生成 schema）。
- 路径一律经过 `WorkspacePathPolicy`，不要自己拼路径。
- 日志用 `from astrbot.api import logger`，带 `[Multisim]` 前缀；不要记录电路内容与授权信息。

## 提交 PR

1. 说明动机与影响面（涉及哪些工具、配置项、错误码）。
2. 附测试方式（跑了哪些命令、结果如何）。
3. 涉及行为变更时同步更新 `docs/` 与 `CHANGELOG.md`。
4. 一个 PR 只做一件事。

## 提交信息

建议 Conventional Commits 风格：`feat: ...`、`fix: ...`、`docs: ...`、`test: ...`、`chore: ...`。
