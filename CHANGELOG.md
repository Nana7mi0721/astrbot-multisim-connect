# 更新日志

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-10-29

首个公开版本。

### 新增

- 基于 `multisim-mcp`（MCP stdio）驱动本机 NI Multisim 14.3，插件进程不直接使用 COM。
- 15 个 LLM 工具：状态、提交实验、验收型实验、任务查询/列表/取消、结果摘要、参数扫描、报告导出、打开电路、读写元件、SPICE、另存、紧急停止。
- `/ms` 控制台命令：`status` / `doctor` / `tools` / `jobs` / `job` / `summary` / `cancel` / `run` / `sweep` / `stop`。
- 异步任务模型：提交返回 `job_id`，`--watch` 在任务结束后推送结论到会话。
- 路径沙箱：所有模型输入路径解析后必须位于工作区内。
- 功能开关：元件修改、参数扫描、危险命令分别可控。
- 统一 JSON 契约与上游错误码映射；`verification=unverified` 不会被当作成功。
- 上游工具名启动时自动发现，可用 `tool_map` 覆盖。
- `backend.mode=fake` 演示后端；43 个单元测试与两个冒烟脚本。

### 已知限制

- 仅 Windows；需要本机安装并授权 Multisim。
- 尚未完成 Multisim 14.3 上 DC/AC/瞬态结果与手工基线的公开回归。
