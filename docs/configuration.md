# 配置参考

配置在 AstrBot WebUI → 插件 → Multisim 电路仿真 → 配置 中修改，保存到：

```
data/config/astrbot_plugin_multisim_config.json
```

改动后需要**重载插件**才会生效。配置由 `_conf_schema.json` 描述，缺省值在 `config.py` 中兜底，因此手写 JSON 时只写关心的字段即可。

## backend —— 后端进程

| 键 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `backend.mode` | 枚举 | `mcp_stdio` | `mcp_stdio`：启动真实后端；`fake`：内置假数据，仅用于演示界面与流程 |
| `backend.python` | 字符串 | 空 | 启动 `multisim_mcp.server` 的解释器路径；空 = AstrBot 自带解释器（`sys.executable`） |
| `backend.args` | 列表 | `["-m","multisim_mcp.server"]` | 启动参数；插件会在末尾追加 `--tool-profile` |
| `backend.tool_profile` | 枚举 | `full` | `full` / `experiment` / `optimization` / `core`；原生电路编辑工具只在 `full` 中 |
| `backend.env` | 字典 | `{}` | 传给后端子进程的附加环境变量（见下） |
| `backend.start_timeout_s` | 浮点 | `30` | 等待后端 `initialize` + `tools/list` 完成的超时 |

### 环境变量

`backend.env` 会与当前进程环境合并后传给 `multisim_mcp.server`：

| 变量 | 说明 |
|---|---|
| `MULTISIM_MCP_WORKER_PYTHON` | **32 位** Python 路径，供 COM worker 使用；不设则上游自行探测（常常失败） |
| `MULTISIM_MCP_TEMPLATE_DIR` | 元件模板包目录 |
| `MULTISIM_MCP_EWD` / `MULTISIM_MCP_EWE` | `.ms14` 解码 / 编码 CLI |
| `MULTISIM_MCP_ENABLE_UNSAFE_COMMANDS` | `1` 时放开任意 Nutmeg 命令文件；由 `features.allow_unsafe_commands` 自动注入 |

Windows 路径在 JSON 中要写成双反斜杠：

```json
"env": {
  "MULTISIM_MCP_WORKER_PYTHON": "C:\\Python312-32\\python.exe"
}
```

## workspace_root —— 路径沙箱

| 键 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `workspace_root` | 字符串 | 空 | Agent 与 `/ms` 允许访问的根目录；空 = `data/plugin_data/astrbot_plugin_multisim/workspace` |

规则：

- 模型传入的相对路径按此根目录解析；绝对路径必须已经位于根目录内。
- 解析使用 `Path.resolve()`，会展开 `..` 与符号链接，越界一律返回 `permission_denied`。
- 实验输出目录（`output_dir`）会被创建在根目录内。
- 建议把 `.ms14` 工程与实验描述都放进这个目录，模型才能访问。

## timeouts —— 超时

| 键 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `timeouts.call_timeout_s` | 浮点 | `60` | 单次 MCP 工具调用超时（秒） |
| `timeouts.job_poll_s` | 浮点 | `2` | 等待任务时的轮询间隔（最小 0.2） |
| `timeouts.job_timeout_s` | 浮点 | `900` | 单个任务最长等待时间；超时返回 `code=timeout`（可重试） |

长仿真建议把 `job_timeout_s` 调到 1800–3600；短任务可下调轮询间隔以更快拿到结果。

## features —— 功能开关

| 键 | 默认 | 说明 |
|---|---|---|
| `features.allow_component_edit` | `true` | 允许 `multisim_set_component_value`；关闭后调用返回 `permission_denied` |
| `features.allow_sweep` | `true` | 允许参数扫描（`multisim_run_sweep` / `/ms sweep`） |
| `features.allow_unsafe_commands` | `false` | 把 `MULTISIM_MCP_ENABLE_UNSAFE_COMMANDS=1` 传给上游，放开任意命令文件 |
| `features.auto_watch` | `true` | `/ms run`、`/ms sweep` 默认在任务结束后把结果推回会话 |

> `allow_unsafe_commands` 只应在完全信任输入时开启。它放开的不只是仿真命令，还包括上游认为危险的命令通道。

## tool_map —— 上游工具名覆盖（高级）

插件在启动后用 `tools/list` 自动发现上游工具。若上游改名或你想换用别名的工具，可显式指定：

```json
"tool_map": {
  "open_circuit": "open_circuit",
  "set_component_value": "set_rlc_value",
  "list_components": "enum_components",
  "run_spice": "run_spice_netlist",
  "save_circuit": "save_circuit"
}
```

键是插件的领域键，值是上游工具名。核心 9 个键（`runtime_status`、`submit_experiment`、`run_verified`、`get_job`、`list_jobs`、`cancel_job`、`get_summary`、`run_sweep`、`export_report`）都有默认值，通常无需配置。

查看上游实际工具名：`/ms tools`。

## 完整示例（桌面版典型配置）

```json
{
  "backend": {
    "mode": "mcp_stdio",
    "python": "",
    "args": ["-m", "multisim_mcp.server"],
    "tool_profile": "full",
    "env": {
      "MULTISIM_MCP_WORKER_PYTHON": "D:\\AstrBotData\\multisim_worker_py32\\Scripts\\python.exe",
      "MULTISIM_MCP_TEMPLATE_DIR": "D:\\AstrBotData\\multisim_component_pack",
      "MULTISIM_MCP_EWD": "C:\\Users\\me\\AppData\\Roaming\\npm\\ewd.cmd",
      "MULTISIM_MCP_EWE": "C:\\Users\\me\\AppData\\Roaming\\npm\\ewe.cmd"
    },
    "start_timeout_s": 30
  },
  "workspace_root": "D:\\AstrBotData\\multisim_workspace",
  "timeouts": {
    "call_timeout_s": 60,
    "job_poll_s": 2,
    "job_timeout_s": 1800
  },
  "features": {
    "allow_component_edit": true,
    "allow_sweep": true,
    "allow_unsafe_commands": false,
    "auto_watch": true
  },
  "tool_map": {}
}
```

## 演示模式

把 `backend.mode` 设为 `fake` 可以在没有 Multisim 的机器上体验工具面与 `/ms` 命令：状态、提交、查询、摘要都走内置假数据。它**不会**做任何真实仿真，发布环境请保持 `mcp_stdio`。
