# 安装部署

本文从零开始，把插件跑通到 `/ms status` 显示「自动化：就绪」。全程约 15–30 分钟，取决于是否需要新装 32 位 Python。

> 只需要 **COM worker** 是 32 位；AstrBot 与 multisim-mcp 前端都用 64 位。

## 0. 前置检查

| 检查项 | 命令 / 方法 | 期望 |
|---|---|---|
| Windows | — | Multisim 与 COM 只支持 Windows |
| Multisim 14.3 | 开始菜单能正常启动 | 已激活、首次启动引导已完成 |
| AstrBot | WebUI「关于」 | `>= 4.16`（本插件 `astrbot_version: >=4.16,<5`） |
| AstrBot 解释器 | 见下 | 64 位 Python 3.10+ |

桌面版 AstrBot 的解释器通常在 `安装目录/backend/python/python.exe`。用下面的命令确认位数与依赖：

```bash
python -c "import struct,sys; print(sys.executable, struct.calcsize('P')*8, 'bit')"
python -m pip show multisim-mcp
```

## 1. 安装插件

任选其一：

- **插件市场**：WebUI → 插件 → 插件市场 → 搜索「Multisim 电路仿真」→ 安装。
- **仓库地址**：WebUI → 插件 → 从仓库安装 → 填 `https://github.com/Nana7mi0721/astrbot-multisim-connect`。
- **手动**：把仓库内容放到 `data/plugins/astrbot_plugin_multisim/`（目录名必须是 `astrbot_plugin_multisim`，仓库根目录就是插件根目录）。

安装后**先不要急着用**，插件依赖的后端还没装。

## 2. 安装 multisim-mcp（插件侧）

装到「启动 `multisim_mcp.server` 的那个解释器」里。默认就是 AstrBot 自带的解释器：

```bash
D:\Program\AstrBot\backend\python\python.exe -m pip install "multisim-mcp==1.3.0"
```

如果想把后端放到独立环境，可在插件配置 `backend.python` 填该环境的 `python.exe`，再往那个环境里装 `multisim-mcp`。

验证：

```bash
D:\Program\AstrBot\backend\python\python.exe -m multisim_mcp.server --help
```

## 3. 准备 32 位 COM worker

`multisim-mcp` 通过一个 **32 位** Python 子进程调用 Multisim 的 COM 接口。两种做法：

### 3.1 官方安装器（推荐）

1. 从 python.org 下载 **Windows installer (32-bit)**，例如 Python 3.12.x；
2. 安装时勾选 *Add python.exe to PATH*（或记住安装路径）；
3. 安装依赖：

```bash
C:\Python312-32\python.exe -m pip install --upgrade pip pywin32 multisim-mcp
```

4. （可选，pywin32 提示时）执行 `python.exe -m pywin32_postinstall -install`。

### 3.2 uv 管理的 32 位环境

uv 的默认解释器是 64 位；需要显式指定 `windows-x86` 构建。先看有哪些可用：

```bash
uv python list --all-versions | findstr x86-none
```

再用完整名字建环境（版本号以 `uv python list` 实际输出为准，32 位构建目前最高到 3.10）：

```bash
uv venv --python cpython-3.10.20-windows-x86-none D:\AstrBotData\multisim_worker_py32
D:\AstrBotData\multisim_worker_py32\Scripts\python.exe -m pip install pywin32 multisim-mcp
```

### 3.3 验证位数

```bash
<32位解释器> -c "import struct; print(struct.calcsize('P')*8, 'bit')"
```

必须输出 `32 bit`，否则 COM 调用会报 `Multisim automation requires a 32-bit Python interpreter`。

## 4. 配置插件

WebUI → 插件 → Multisim 电路仿真 → 配置，或在 `data/config/astrbot_plugin_multisim_config.json` 中写入：

```json
{
  "backend": {
    "mode": "mcp_stdio",
    "tool_profile": "full",
    "env": {
      "MULTISIM_MCP_WORKER_PYTHON": "C:\\Python312-32\\python.exe"
    }
  }
}
```

常用附加项：

| 环境变量 | 用途 |
|---|---|
| `MULTISIM_MCP_TEMPLATE_DIR` | 元件模板包目录（上游 bootstrap 脚本生成） |
| `MULTISIM_MCP_EWD` / `MULTISIM_MCP_EWE` | `.ms14` 解码/编码 CLI（`electronics-workbench-decoder`） |

可选：`.ms14` 编解码需要 Node CLI；没有它模拟电路仿真仍可用，但涉及工程文件读写的功能会降级：

```bash
npm install -g electronics-workbench-decoder
```

然后把生成的 `ewd.cmd` / `ewe.cmd` 绝对路径填进 `MULTISIM_MCP_EWD` / `MULTISIM_MCP_EWE`。

## 5. 重载并验证

1. 在插件页点击**重载**（配置改动后必须重载）。
2. 在任意会话发送 `/ms status`，期望：

```
Multisim 后端：已连接
模式：mcp_stdio　工具数：123
工作区：...\data\plugin_data\astrbot_plugin_multisim\workspace
自动化：就绪（automation）
详细诊断：/ms doctor
```

3. 需要更细的信息时发送 `/ms doctor`，重点看：

| 字段 | 含义 |
|---|---|
| `runtime_mode` | `automation` = 可以真正跑仿真；`introspection-only` = 只能列工具 |
| `runtime_compatible` | `false` 表示解释器位数等不满足要求 |
| `missing_tools` | 未发现的上游工具（对应功能会返回 `tool_unavailable`） |
| `available_tools` | 上游实际暴露的工具名，可用于 `tool_map` 覆盖 |

## 6. 跑第一个实验

1. 确认工作区路径（`/ms status` 里显示的那一行）。
2. 把 [`examples/rc_transient.json`](../examples/rc_transient.json) 复制进去，改名为 `demo.json`。
3. 发送 `/ms run demo.json --watch`。
4. 任务结束会推送结论；随后 `/ms summary <job_id>` 查看测量值与产物。

## 7. 更新与卸载

- **更新**：插件市场点更新，或从仓库重新安装；配置文件与工作区不会被删除。
- **卸载**：WebUI 卸载插件即可。插件在 `terminate()` 中会取消后台任务、关闭 MCP 子进程。
- 手动清理时可删除：
  - `data/config/astrbot_plugin_multisim_config.json`
  - `data/plugin_data/astrbot_plugin_multisim/`（含工作区与运行产物）

## 8. 安装阶段常见问题

| 症状 | 处理 |
|---|---|
| `/ms status` 显示「仅 MCP 自省」 | 缺 32 位 worker 或 `pywin32`，见 [故障排查](troubleshooting.md#仅-mcp-自省introspection-only) |
| `backend_unavailable` | `backend.python` 里没装 `multisim-mcp`，或 `backend.args` 被改坏 |
| AstrBot 启动时提示依赖冲突 | 确认 `requirements.txt` 里的 `mcp>=1.0,<3` 未被手动改成 `mcp<2`（AstrBot 4.29 自带 mcp 2.x） |
| Multisim 弹窗要求激活 | 先手动启动一次 Multisim 完成激活，再重载插件 |
