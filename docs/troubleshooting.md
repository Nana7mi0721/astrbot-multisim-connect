# 故障排查

## 先看这三个地方

1. `/ms status` —— 后端连没连上、处于什么运行模式。
2. `/ms doctor` —— 完整 JSON：解释器、工具映射、`runtime_status` 原文、缺失工具。
3. AstrBot 日志 —— 搜索 `[Multisim]`，上游 stderr 也会转发到日志。

## 仅 MCP 自省（introspection-only）

`/ms status` 显示：

```
自动化：未就绪（introspection-only，仅 MCP 自省）
原因：Multisim automation requires a 32-bit Python interpreter
修复：安装 32 位 Python + pywin32，并在 backend.env 设置 MULTISIM_MCP_WORKER_PYTHON
```

含义：后端进程起来了、工具也能列出来，但 COM worker 不可用，**不能真正跑仿真**。

处理：

1. 确认 32 位解释器存在且位数正确：
   `C:\Python312-32\python.exe -c "import struct; print(struct.calcsize('P')*8)"` → `32`
2. 该解释器里装好 `pywin32`（必要时再跑 `python -m pywin32_postinstall -install`）。
3. 把路径写进配置 `backend.env.MULTISIM_MCP_WORKER_PYTHON`（注意 JSON 里要双反斜杠）。
4. 重载插件，再 `/ms status`。

## `backend_unavailable`

后端进程连不上或已崩溃。按顺序检查：

| 检查 | 方法 |
|---|---|
| 解释器能跑后端 | `backend.python -m multisim_mcp.server --help` |
| 参数没被改坏 | `backend.args` 应为 `["-m","multisim_mcp.server"]` |
| 版本匹配 | `python -m pip show multisim-mcp`，建议 1.3.0 |
| 端口/环境冲突 | 插件用 stdio，不占端口；检查是否有代理软件改写子进程环境 |

修复后 `/ms stop restart` 或重载插件。

## `multisim_not_ready`

Multisim 未安装 / 未激活 / COM 未注册 / 被弹窗阻塞。

- 手动启动一次 Multisim，完成激活与首次引导，再重试。
- 关闭可能阻塞的模态对话框（授权提示、更新提示、恢复文件提示）。
- 仍失败时运行上游诊断：`python -m multisim_mcp.server --help` 查看它提供的 doctor 子命令，或直接看 `/ms doctor` 里 `runtime` 字段的原文。

## `tool_unavailable`

当前上游版本没有对应工具：

1. `/ms tools` 看实际工具名；
2. 在配置 `tool_map` 里把领域键指向真实名字，例如：

```json
"tool_map": { "run_spice": "run_spice_netlist" }
```

3. 若确实不存在该能力，升级 `multisim-mcp`，或改用 `backend.tool_profile = full`。

## 任务一直 `running` 或 `timeout`

- `/ms job <id>` 看进度与最后一次快照；
- 长仿真把 `timeouts.job_timeout_s` 调大（默认 900 秒）；
- Multisim 卡死时执行 `/ms stop restart`；
- 若任务在上游已完成但插件显示超时，用 `/ms summary <id>` 直接取结果。

## 修改元件报错

Multisim 在仿真运行中通常不允许结构性修改。先 `/ms stop` 停止任务，再调用 `multisim_set_component_value`。

## pywin32 生成缓存损坏

现象（32 位 worker 侧）：

```
module 'win32com.gen_py.xxxxxxxx-...' has no attribute 'CLSIDToPackageMap'
```

原因：`gen_py` 缓存与当前 pywin32 / Multisim 版本不匹配。处理：

1. 关闭 Multisim 与 AstrBot；
2. 删除 `%TEMP%\gen_py\<Python 版本>`（例如 `%TEMP%\gen_py\3.10`）；
3. 重启 AstrBot，让 COM 重新生成缓存。

## 上游模板包与 `full_workflow_ready`

`multisim-mcp` 的 bootstrap 脚本会从本机 NI 样例生成元件模板包。若本机样例缺少某些扩展数字器件（如 CD4017、DFF8、SWB、TIMER8），诊断里 `full_workflow_ready` 会是 `false`，但模拟电路实验不受影响。

需要注意：bootstrap 必须用 **32 位** 解释器运行（它要走 COM 打开样例）。

## 开发相关

| 现象 | 处理 |
|---|---|
| `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` | 装的是 mcp 2.x，`FastMCP` 已改名 `MCPServer`。插件的 `tests/fake_mcp_server.py` 已兼容两者；自己的脚本按 2.x API 改写 |
| `RuntimeError: Attempted to exit cancel scope in a different task` | 不要在别的任务里关闭 MCP 会话；插件的 `McpStdioBackend` 已把连接固定在同一任务 |
| `python -m unittest discover` 找不到包 | 在**仓库根目录**执行，并使用 `-t .`：`python -m unittest discover -s tests -t .` |
| AstrBot 加载插件报 `data.plugins.astrbot_multisim.main` 导入失败 | 插件目录名必须是 `astrbot_plugin_multisim`（仓库根目录即插件根目录） |

## 尚未验证的部分

以下内容没有在公开环境做过端到端回归，遇到问题欢迎提 Issue：

- Multisim 14.3 上 DC / AC / 瞬态结果与手工基线的逐项对比；
- 不同 Multisim 14.x 小版本、不同授权的兼容性；
- `full` 轮廓里原生电路编辑工具在其它上游版本中的命名差异（插件靠启动时发现 + `tool_map` 兜底）。
