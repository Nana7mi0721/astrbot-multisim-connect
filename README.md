# astrbot_plugin_multisim

<img src="logo.png" width="120" align="right" alt="logo" />

[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.16%2C%3C5-1a73e8)](https://astrbot.app)
[![version](https://img.shields.io/badge/version-0.1.0-blue)](CHANGELOG.md)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![platform](https://img.shields.io/badge/platform-Windows-lightgrey)](#前置条件)

让 AstrBot 的 AI Agent 直接驱动本机 **NI Multisim 14.3** 做电路仿真：打开工程、改参数、跑 DC/AC/瞬态、参数扫描、读测量值与验收结论、导出报告。

插件自身**不碰 COM**，而是作为 [`multisim-mcp`](https://github.com/yxy050208/multisim-mcp)（MIT）的 MCP 客户端：

```
AstrBot（64 位 Python）
  └── 本插件 ──MCP stdio──> multisim-mcp ──COM──> 32 位 COM Worker ──> Multisim 14.3
```

32/64 位 COM、`.ms14` 编解码、任务队列与 worker 崩溃恢复交给上游；插件只负责**领域工具面、权限开关、路径沙箱与统一结果契约**。

## 功能

- **15 个 LLM 工具**：状态检查、提交实验、验收型实验、任务查询/取消、结果摘要、参数扫描、报告导出、打开电路、读写元件、SPICE、另存、紧急停止。
- **`/ms` 控制台**：不经模型也能提交与查看任务，`/ms doctor` 给出完整诊断。
- **异步任务模型**：提交即返回 `job_id`，不长时间占住工具调用；`/ms run --watch` 结束后自动推送到会话。
- **路径沙箱**：模型给出的每个路径都解析后校验必须落在工作区内。
- **开关式权限**：元件修改、参数扫描、危险命令分别可控。
- **诚实的结论**：上游 `verification=unverified` 原样转达，绝不视为成功。

## 前置条件

| 组件 | 要求 |
|---|---|
| 操作系统 | Windows（Multisim 与 COM 仅限 Windows） |
| AstrBot | `>=4.16,<5`（在 4.29.3 上验证） |
| NI Multisim | 14.3（14.x 一般可用，未逐一验证），需有效授权 |
| Python（插件侧） | AstrBot 自带 64 位解释器即可，需 `pip install multisim-mcp==1.3.0` |
| Python（COM worker） | **32 位** Python + `pywin32`，通过 `MULTISIM_MCP_WORKER_PYTHON` 指定 |
| MCP SDK | AstrBot 已自带，`requirements.txt` 已声明兼容范围 |

> 只有 COM worker 必须是 32 位；multisim-mcp 前端与 AstrBot 用 64 位即可。

## 快速开始

1. **安装插件**：在 AstrBot WebUI「插件市场」搜索 *Multisim 电路仿真* 安装，或用本仓库地址安装。
2. **装后端**：在 AstrBot 使用的 Python 中执行 `pip install multisim-mcp==1.3.0`。
3. **准备 32 位 worker**：安装 32 位 Python + `pywin32`，把解释器路径填到插件配置 `backend.env.MULTISIM_MCP_WORKER_PYTHON`（详见 [安装部署](docs/install.md)）。
4. **重载插件**，发送 `/ms status`，看到 `自动化：就绪（automation）` 即成功。
5. 把实验描述放进工作区，发送 `/ms run demo.json --watch`。

最小实验描述（`workspace/demo.json`）：

```json
{
  "netlist": "R1 in out 1k\nC1 out 0 1u\nV1 in 0 dc 5",
  "commands": "tran 0 5m 0 10u",
  "output_dir": "runs/rc_demo"
}
```

更多示例见 [`examples/`](examples/)。

## 配置

配置在 WebUI 插件配置页完成，写入 `data/config/astrbot_plugin_multisim_config.json`。

| 键 | 默认 | 说明 |
|---|---|---|
| `backend.mode` | `mcp_stdio` | `fake` 仅用于演示，不做真实仿真 |
| `backend.python` | 空 | 启动 `multisim_mcp.server` 的解释器；空 = AstrBot 自带 |
| `backend.args` | `["-m","multisim_mcp.server"]` | 启动参数 |
| `backend.tool_profile` | `full` | 上游工具轮廓；原生电路编辑工具在 `full` 中 |
| `backend.env` | `{}` | `MULTISIM_MCP_WORKER_PYTHON`、`MULTISIM_MCP_TEMPLATE_DIR` 等 |
| `backend.start_timeout_s` | `30` | 后端启动超时 |
| `workspace_root` | 空 | Agent 可访问的路径根；空 = `data/plugin_data/astrbot_plugin_multisim/workspace` |
| `timeouts.call_timeout_s` | `60` | 单次后端调用超时 |
| `timeouts.job_poll_s` | `2` | 任务轮询间隔 |
| `timeouts.job_timeout_s` | `900` | 任务等待上限 |
| `features.allow_component_edit` | `true` | 允许 `multisim_set_component_value` |
| `features.allow_sweep` | `true` | 允许参数扫描 |
| `features.allow_unsafe_commands` | `false` | 允许上游执行任意 Nutmeg 命令文件（危险） |
| `features.auto_watch` | `true` | `/ms run` 后自动跟踪并推送结果 |
| `tool_map` | `{}` | 覆盖「领域键 → 上游工具名」映射（高级） |

逐项说明与示例见 [配置参考](docs/configuration.md)。

## Agent 工具

| 工具 | 作用 |
|---|---|
| `multisim_status` | 后端就绪状态 + 工具映射诊断（任何操作前先调） |
| `multisim_submit_experiment` | 提交仿真实验，返回 `job_id` |
| `multisim_run_verified` | 带 `requirements` 的验收型实验（pass / fail / unverified） |
| `multisim_get_job` | 查询任务状态与进度 |
| `multisim_list_jobs` | 近期任务列表 |
| `multisim_cancel_job` | 取消任务 |
| `multisim_get_summary` | 测量值、验收结论与产物列表 |
| `multisim_run_sweep` | 参数扫描（最多 100 点） |
| `multisim_export_report` | 导出正式实验报告 |
| `multisim_open_circuit` | 打开工作区内的 `.ms14` |
| `multisim_set_component_value` | 修改 R/C/L 等元件参数 |
| `multisim_list_components` | 枚举当前电路元件 |
| `multisim_run_spice` | SPICE / Nutmeg 请求 |
| `multisim_save_circuit` | 另存当前电路 |
| `multisim_stop` | 停止全部任务，可重启后端 |

所有工具返回统一 JSON：

```jsonc
// 成功
{"ok": true, "key": "submit_experiment", "tool": "submit_circuit_experiment", "data": {}}
// 失败
{"ok": false, "code": "invalid_input|not_found|permission_denied|timeout|backend_unavailable|...",
 "message": "...", "retryable": false}
```

参数与返回细节见 [工具参考](docs/tools.md)。

## 用户命令

```
/ms status                       # 简要状态
/ms doctor                       # 完整诊断（配置、工具映射、上游工具名）
/ms tools                        # 上游工具列表
/ms jobs [N]                     # 近期任务
/ms job <id>                     # 任务详情
/ms summary <id>                 # 结果摘要
/ms cancel <id>                  # 取消
/ms run <spec.json> [--watch|--no-watch] [--out DIR]
/ms sweep <spec.json> [--out DIR]
/ms stop [restart]
```

详见 [命令参考](docs/commands.md)。

## 安全边界

- 模型给出的路径全部 `Path.resolve()` 后校验，越界返回 `permission_denied`。
- 任意 shell / 任意 Nutmeg 命令文件默认禁用，需显式打开 `allow_unsafe_commands`。
- Multisim 执行串行（插件侧单队列），并发请求排队。
- COM 不出本机：stdio 只在本机父子进程间通信，不监听端口。
- 卸载/重载插件会取消后台跟踪任务并关闭 MCP 子进程，不留孤儿进程。

## 文档

| 文档 | 内容 |
|---|---|
| [安装部署](docs/install.md) | 从零安装：后端、32 位 worker、验证、卸载 |
| [配置参考](docs/configuration.md) | 全部配置项与环境变量 |
| [工具参考](docs/tools.md) | 15 个 LLM 工具的参数、返回与错误码 |
| [命令参考](docs/commands.md) | `/ms` 子命令与实验描述格式 |
| [架构说明](docs/architecture.md) | 分层结构、MCP 客户端实现、扩展点 |
| [故障排查](docs/troubleshooting.md) | 常见症状与处理 |
| [调研报告](docs/research/) | 立项时的两份可行性调研 |

## 开发

```bash
# 单元测试（不需要 Multisim / mcp）
python -m unittest discover -s tests -t .

# 传输层冒烟：真实拉起 MCP stdio 子进程（需要 mcp SDK）
python -m tests.smoke_mcp

# 进程内插件冒烟：Star 生命周期、工具注册与命令（需要 AstrBot 运行环境）
python -m tests.inprocess_smoke
```

目录结构：

```
main.py          Star 入口（LLM 工具与 /ms 命令必须在此模块）
config.py        配置解析
domain/          纯模型与错误（不依赖 AstrBot / MCP）
application/     编排、路径沙箱、任务服务、后端 Protocol
infrastructure/  MCP stdio 客户端、工具映射、假后端
tests/           单元测试与冒烟脚本
examples/        示例实验描述
docs/            文档
```

贡献前请读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 已知限制

- 仅 Windows；需要本机安装并授权 Multisim。
- 未在 Multisim 14.3 上跑通「真实 DC/AC/TRAN 结果与手工基线对比」的公开回归（见 [故障排查](docs/troubleshooting.md#尚未验证的部分)）。
- `full` 轮廓中的原生电路编辑工具名在启动时自动发现，可用 `tool_map` 覆盖。
- 上游 `multisim-mcp` 的模板包若缺少部分扩展数字器件，`full_workflow_ready` 会是 `false`，不影响模拟电路仿真。

## 许可证

[MIT](LICENSE)。上游依赖 [`multisim-mcp`](https://github.com/yxy050208/multisim-mcp) 亦为 MIT；NI Multisim 为 National Instruments 商业软件，本插件不包含其任何组件，使用需自备授权。

---

English summary: an AstrBot plugin that exposes a local NI Multisim 14.3 installation to LLM agents through [multisim-mcp](https://github.com/yxy050208/multisim-mcp) over MCP stdio. It ships 15 LLM tools plus a `/ms` console command, with a path sandbox and per-feature switches. Windows only. See [README_EN.md](README_EN.md) for details.
