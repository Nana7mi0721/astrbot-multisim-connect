# 工具参考（LLM 工具）

插件向 Agent 暴露 15 个工具。它们的返回值都是**JSON 字符串**，遵循同一契约；Agent 只需要判断 `ok` 与 `code`。

## 统一契约

```jsonc
// 成功
{
  "ok": true,
  "key": "submit_experiment",          // 插件内部领域键
  "tool": "submit_circuit_experiment", // 真正调用的上游工具名
  "data": { }                          // 上游原始返回
}

// 失败
{
  "ok": false,
  "code": "invalid_input",
  "message": "人可读的说明",
  "retryable": false,
  "key": "submit_experiment",
  "tool": "submit_circuit_experiment",
  "backend": { }                       // 可选：上游原始错误体
}
```

### 状态与结论字段

任务类工具的 `data` 通常包含：

| 字段 | 取值 |
|---|---|
| `job_id` | 任务 ID |
| `state` | `queued` / `running` / `cancelling` / `succeeded` / `failed` / `cancelled` / `timed_out` |
| `verification` | `pass` / `fail` / `unverified` |
| `measurements` | 测量值列表（摘要接口） |
| `artifacts` | 产物路径列表（摘要接口） |

> **`verification = unverified` 不等于成功。** 插件原样转达上游结论，Agent 在汇报时应说明「未验证」。

### 错误码

| `code` | 含义 | 可重试 |
|---|---|---|
| `invalid_input` | 参数不合法 | 否 |
| `not_found` | 任务 / 文件 / 工具不存在 | 否 |
| `permission_denied` | 被路径沙箱或功能开关拒绝 | 否 |
| `tool_unavailable` | 上游没有对应工具（用 `/ms tools` 查） | 否 |
| `multisim_not_ready` | Multisim 未安装 / 未激活 / COM 不可用 | 是 |
| `backend_unavailable` | 后端进程连不上或已崩溃 | 是 |
| `timeout` | 调用或任务超时 | 是 |
| `cancelled` | 任务被取消 | 否 |
| `simulation_failed` | 仿真执行失败 | 否 |
| `artifact_unavailable` | 产物缺失 | 否 |
| `io_error` / `runtime_error` / `internal_error` | 上游或插件的其他错误 | 视情况 |

## 工具清单

### `multisim_status`

检查后端是否就绪，并给出工具映射诊断。**任何仿真操作前先调用。**

- 参数：无
- 返回 `data` 关键字段：

| 字段 | 说明 |
|---|---|
| `plugin_version` | 插件版本 |
| `config` | 生效配置摘要（含工作区绝对路径） |
| `tool_count` | 上游工具数量 |
| `tool_map` | 领域键 → 上游工具名 |
| `missing_tools` | 未发现的上游工具 |
| `runtime_mode` | `automation` / `introspection-only` |
| `multisim_ready` | 是否可真正执行仿真 |

### `multisim_submit_experiment`

提交一个仿真实验（异步），立即返回 `job_id`。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `request` | object | 是 | 实验请求，原样转发给上游 `submit_circuit_experiment`（`netlist` / `commands` / `analyses` 等） |
| `output_dir` | string | 否 | 工作区内相对路径；留空由后端决定 |

### `multisim_run_verified`

提交带验收要求的实验，上游会自动测量并给出 `pass` / `fail` / `unverified`。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `spec` | object | 是 | `ExperimentSpec`，以 `{"spec": ...}` 转发给 `run_verified_circuit_experiment` |
| `output_dir` | string | 否 | 工作区内相对路径 |

### `multisim_get_job`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `job_id` | string | 是 | 任务 ID |

### `multisim_list_jobs`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `limit` | int | 否 | 返回条数，默认 10 |

### `multisim_cancel_job`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `job_id` | string | 是 | 任务 ID |

### `multisim_get_summary`

返回测量值、验收结论与产物列表。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `job_id` | string | 是 | 任务 ID |

### `multisim_run_sweep`

参数扫描（上游限制最多 100 个扫描点），受 `features.allow_sweep` 控制。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `request` | object | 是 | 扫描计划，转发给 `submit_experiment_sweep` |
| `output_dir` | string | 否 | 工作区内相对路径 |

### `multisim_export_report`

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `request` | object | 是 | 报告导出请求，转发给 `export_formal_experiment_report` |

### `multisim_open_circuit`

在 Multisim 中打开工作区内的 `.ms14`。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `path` | string | 是 | 相对工作区或工作区内绝对路径；文件必须存在 |

### `multisim_set_component_value`

修改当前电路中元件的参数，受 `features.allow_component_edit` 控制。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `refdes` | string | 是 | 位号，如 `R1` |
| `value` | number | 是 | 基本单位数值，`1000` 表示 1 kΩ |
| `property_name` | string | 否 | 属性名，默认 `value` |

仿真运行中通常不允许结构性修改，失败时先停止仿真再重试。

### `multisim_list_components`

列出当前电路的元件与参数。参数：无。

### `multisim_run_spice`

执行 SPICE / Nutmeg 请求，原样转发给上游。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `request` | object | 是 | 请求对象（`netlist` / `commands` 等） |

上游默认只允许 `op` / `dc` / `ac` / `tran`；任意命令文件需要 `features.allow_unsafe_commands`。

### `multisim_save_circuit`

另存当前电路。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `request` | object | 是 | 保存请求（目标路径等） |

### `multisim_stop`

停止所有活动任务；可选重启后端（COM 卡死时恢复）。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `restart` | bool | 否 | 是否重启 MCP 连接，默认 `false` |

返回 `{"ok": true, "cancelled": [...], "failed": [...], "restarted": bool}`。

## 典型调用顺序

```
multisim_status
  → multisim_open_circuit("/workspace/rc.ms14")     # 可选：基于已有工程
  → multisim_set_component_value("R1", 2200)         # 可选：改参数
  → multisim_submit_experiment({"netlist": ..., "commands": ...})
  → multisim_get_job(job_id)                         # 轮询到 succeeded
  → multisim_get_summary(job_id)                     # 测量值 + 产物
  → multisim_export_report({"experiment_id": job_id}) # 可选
```
