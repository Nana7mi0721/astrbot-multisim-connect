# 示例

这些文件放进插件工作区（`/ms status` 显示的那一行），然后用 `/ms run <文件>` 或 `/ms sweep <文件>` 提交。

| 文件 | 用途 |
|---|---|
| [`divider_spec.json`](divider_spec.json) | 电阻分压 + DC 扫描 + 验收条件（配合 `multisim_run_verified` 使用） |
| [`rc_transient.json`](rc_transient.json) | RC 一阶电路的瞬态分析 |
| [`sweep_rc.json`](sweep_rc.json) | 参数扫描骨架（改动电阻值观察频率响应） |

## 说明

- `netlist` / `commands` 采用 SPICE 写法；具体字段最终由上游 `multisim-mcp` 解释。
- `requirements` 只有验收型实验使用，字段示例：

```json
{
  "id": "vout-mid",
  "metric": "dc_value",
  "signal": "V(out)",
  "operator": "approximately",
  "target": 2.5,
  "tolerance_percent": 2
}
```

- `sweep` 的字段是**示意**：上游不同版本对扫描计划的字段名可能不同，请以 `/ms tools` 与上游文档为准。
- 输出目录会创建在工作区内；也可以命令行用 `--out` 覆盖。

提交后：

```
/ms job <job_id>
/ms summary <job_id>
```

长任务用 `/ms run <文件> --watch`，结束后结论会推送到当前会话。
