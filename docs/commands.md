# 命令参考（`/ms`）

`/ms` 是插件提供的控制台命令，不需要经过模型：适合运维检查、手动提交与排查。

```
/ms status                       # 简要状态
/ms doctor                       # 完整诊断（JSON）
/ms tools                        # 上游工具列表
/ms jobs [N]                     # 近期任务（默认 10）
/ms job <id>                     # 任务详情
/ms summary <id>                 # 结果摘要
/ms cancel <id>                  # 取消任务
/ms run <spec.json> [--watch|--no-watch] [--out DIR]
/ms sweep <spec.json> [--out DIR]
/ms stop [restart]
```

不带子命令时等同于 `/ms status`。

## `/ms status`

```
Multisim 后端：已连接
模式：mcp_stdio　工具数：123
工作区：D:\AstrBotData\multisim_workspace
自动化：就绪（automation）
详细诊断：/ms doctor
```

出现「未就绪（…，仅 MCP 自省）」时，会同时打印原因与修复提示，见 [故障排查](troubleshooting.md)。

## `/ms doctor`

输出完整 JSON 诊断，字段说明：

| 字段 | 说明 |
|---|---|
| `ok` | 后端整体是否可用 |
| `config` | 生效配置（解释器、参数、工具轮廓、工作区） |
| `tool_count` / `available_tools` | 上游工具数量与前 60 个名字 |
| `tool_map` | 领域键 → 上游工具名 |
| `missing_tools` | 缺失的上游工具 |
| `runtime` | 上游 `runtime_status` 原始返回 |
| `runtime_mode` / `multisim_ready` | 是否处于 `automation` 模式 |

## `/ms tools`

列出上游实际暴露的工具名（最多显示 80 个）。用于填写 `tool_map` 或确认上游版本。

## `/ms jobs [N]`

先列插件缓存的近期任务，再附上游返回的任务列表（如果上游支持）。

```
近期任务（插件缓存）：
- 9f3c1a2b  succeeded
- 1d0e77aa  running
```

## `/ms job <id>` / `/ms summary <id>`

分别返回任务状态与结果摘要（测量值 + 产物路径 + 验收结论）。摘要优先用 `job_id` 调用，上游若要求 `experiment_id` 会自动回退。

## `/ms cancel <id>`

取消排队或运行中的任务。已结束的任务返回 `not_found` 或上游错误。

## `/ms run` / `/ms sweep`

把工作区内的实验描述提交给后端。

| 参数 | 说明 |
|---|---|
| `<spec.json>` | 工作区内相对路径（也接受工作区内绝对路径），必须是 JSON 对象 |
| `--watch` / `--no-watch` | 是否在任务结束后推送到当前会话；默认取配置 `features.auto_watch` |
| `--out DIR` | 覆盖输出目录（工作区内相对路径），会覆盖 spec 里的 `output_dir` |

提交成功返回：

```
已提交任务 9f3c1a2b（状态：queued）。
查询：/ms job 9f3c1a2b　结果：/ms summary 9f3c1a2b
已开启结果推送，任务结束后会在此会话通知。
```

### 实验描述（spec）格式

以 [`examples/divider_spec.json`](../examples/divider_spec.json) 为例：

```json
{
  "schema_version": 1,
  "netlist": "V1 in 0 5\nR1 in out 1k\nR2 out 0 1k",
  "commands": "dc V1 0 5 1",
  "requirements": [
    {
      "id": "vout-mid",
      "metric": "dc_value",
      "signal": "V(out)",
      "operator": "approximately",
      "target": 2.5,
      "tolerance_percent": 2
    }
  ],
  "output_dir": "runs/divider"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `netlist` | 视上游 | SPICE 网表文本 |
| `commands` | 否 | 分析命令，如 `tran 0 5m 0 10u`、`ac dec 10 1 1meg` |
| `requirements` | 否 | 验收条件，只有 `multisim_run_verified` / `run_verified` 使用 |
| `output_dir` | 否 | 输出目录（相对工作区）；`--out` 优先级更高 |

其余字段原样转发给上游 `multisim-mcp`，完整契约以[上游文档](https://github.com/yxy050208/multisim-mcp)为准。

### `/ms run` 与 `/ms sweep` 的区别

- `run` → `submit_circuit_experiment`（或 `run_verified_circuit_experiment`，走 LLM 工具 `multisim_run_verified`）
- `sweep` → `submit_experiment_sweep`，spec 描述扫描计划（参数、范围、步数），上游限制最多 100 个点

## `/ms stop [restart]`

停止插件缓存中的所有活动任务；加 `restart` 会额外重启后端连接（用于 COM 卡死、Multisim 弹窗阻塞等场景）。

```json
{"ok": true, "cancelled": ["9f3c1a2b"], "failed": [], "restarted": true}
```
