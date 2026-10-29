# 架构说明

## 为什么不是「插件直连 COM」

Multisim 的自动化接口是 **32 位 COM**，而 AstrBot 运行在 64 位 Python 上；同时 COM 调用有线程套间（apartment）、GUI 生命周期、崩溃隔离等约束。把 COM 放进 AstrBot 主进程会在稳定性与可维护性上都很糟。

因此插件复用上游 [`multisim-mcp`](https://github.com/yxy050208/multisim-mcp)，自己只做 MCP 客户端：

```
┌────────────── AstrBot（64 位） ──────────────┐
│  Star: main.py（15 个 LLM 工具 + /ms 命令）   │
│        │                                      │
│  application/  SimulationService / JobService │
│        │                                      │
│  infrastructure/mcp_backend.py                │
└────────┼──────────────────────────────────────┘
         │ MCP stdio（本机子进程，无端口）
┌────────▼──────────────────────────────────────┐
│ multisim-mcp 1.3.0（64 位 Python 亦可）        │
│  · 工具轮廓 full/experiment/…（123 个工具）    │
│  · .ms14 编解码、任务队列、报告导出            │
└────────┬──────────────────────────────────────┘
         │ 子进程 + COM
┌────────▼──────────────────────────────────────┐
│ 32 位 COM Worker（pywin32）→ Multisim 14.3     │
└───────────────────────────────────────────────┘
```

## 分层

| 层 | 目录 | 职责 | 依赖 |
|---|---|---|---|
| 展示 | `main.py` | Star 子类、LLM 工具、`/ms` 命令、结果推送 | AstrBot |
| 应用 | `application/` | 编排、路径沙箱、任务服务、后端 Protocol | domain |
| 领域 | `domain/` | 数据模型与错误层级，纯逻辑 | 无 |
| 基础设施 | `infrastructure/` | MCP stdio 客户端、工具映射、假后端 | domain, config |

依赖方向单向：`main → application → domain`，`infrastructure` 实现 `application.backend.MultisimBackend` 协议。`domain/` 不 import `astrbot`、`mcp`、`win32`，因此可以在任何环境跑单测。

## MCP 客户端（`infrastructure/mcp_backend.py`）

几个关键决策：

1. **连接由单独任务持有。** 子进程与会话在 `_run()` 这个长期任务里用 `AsyncExitStack` 建立和关闭。MCP SDK 的 `stdio_client` 使用 anyio 的 cancel scope，跨任务退出会抛 `RuntimeError: Attempted to exit cancel scope in a different task`，所以所有进出都留在同一任务。
2. **单一请求队列串行化。** 工具调用与 `list_tools` 都投递到 `asyncio.Queue`，由 `_run()` 顺序执行。Multisim COM 本身只能串行，排队反而让行为可预测。
3. **自动重启。** 子进程退出或传输异常时设置 `_fatal`，本次调用返回 `backend_unavailable`（可重试）；下一次调用会重新拉起子进程。
4. **结果解析。** 优先读 `structuredContent`，否则尝试把文本内容按 JSON 解析，再退化为纯文本；`isError` 为真时从 JSON 里提取 `code` / `message` / `retryable`。

启动参数由 `BackendSettings` 生成：解释器（默认 `sys.executable`）、`args`、附加 `--tool-profile`；环境变量 = 当前进程环境 + `backend.env`。

## 工具映射（`infrastructure/tool_map.py`）

- 9 个核心工具键有固定默认（如 `submit_experiment → submit_circuit_experiment`）。
- 5 个原生工具键（打开电路、改元件、枚举元件、SPICE、保存）在启动时按关键词从 `tools/list` 的结果里**发现**，避免硬编码上游改名。
- 发现顺序有优先级（例如 `set_component_value` 优先匹配 `set_rlc_value` 而不是 `get_rlc_value`）。
- `tool_map` 配置可以覆盖任何键；缺失的键会出现在 `/ms status` 的 `missing_tools` 中，调用对应工具返回 `tool_unavailable`。

## 任务模型（`application/job_service.py`）

- `submit()` 调上游提交工具，BFS 深度查找返回体里的 `job_id` / `state` / `verification`，兼容不同字段名。
- 上游若要求 `experiment_id` 而不是 `job_id`，遇到 `invalid_input` 会自动换参数名重试一次。
- 插件维护一个有界的任务缓存（`recent()` / `active_ids()`），`/ms stop` 依赖它。
- `wait()` 按 `job_poll_s` 轮询，超过 `job_timeout_s` 返回 `{ok:false, code:"timeout", retryable:true, last:...}`，不会吞掉最后一次快照。

## 路径沙箱（`application/path_policy.py`）

所有模型输入的路径都经过 `WorkspacePathPolicy.resolve()`：

- `Path.resolve()` 展开 `..`、符号链接与大小写；
- 结果必须是工作区根目录的子路径，否则抛 `PermissionDenied`；
- `ensure_output_dir()` 负责在根目录内创建实验输出目录。

## 生命周期

- `initialize()`：只记录配置，不启动子进程（避免 AstrBot 启动变慢）。
- 首次工具调用时惰性装配 `SimulationService` 与后端。
- `terminate()`：取消后台跟踪任务 → 关闭后端（终止 MCP 子进程）→ 置空服务，热重载不留孤儿进程。

## 扩展点

| 想做的事 | 改动位置 |
|---|---|
| 增加一个新工具 | `main.py` 加 `@filter.llm_tool`，`simulation_service.py` 加薄方法，必要时在 `tool_map.py` 加键 |
| 换后端实现 | 实现 `application/backend.py` 的 `MultisimBackend` 协议 |
| 适配上游改名 | 用配置 `tool_map`，或改 `DISCOVERY_HINTS` |
| 换演示数据 | `infrastructure/fake_backend.py` |
