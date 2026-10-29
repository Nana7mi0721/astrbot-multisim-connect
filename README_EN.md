# astrbot_plugin_multisim

[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.16%2C%3C5-1a73e8)](https://astrbot.app)
[![version](https://img.shields.io/badge/version-0.1.0-blue)](CHANGELOG.md)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Give AstrBot agents hands-on control of a local **NI Multisim 14.3** installation: open designs, edit component values, run DC/AC/transient analyses and parameter sweeps, read measurements and acceptance results, and export reports.

The plugin never touches COM itself. It is an MCP client for [`multisim-mcp`](https://github.com/yxy050208/multisim-mcp) (MIT):

```
AstrBot (64-bit Python)
  └── this plugin ──MCP stdio──> multisim-mcp ──COM──> 32-bit COM worker ──> Multisim 14.3
```

32/64-bit COM interop, `.ms14` codecs, job queues and worker recovery stay upstream; the plugin owns the domain tool surface, permission switches, path sandbox and result contract.

## Features

- **15 LLM tools** — status, submit experiment, verified run, job query/list/cancel, summary, sweep, report export, open circuit, read/write components, SPICE, save, emergency stop.
- **`/ms` console** — drive everything without the model; `/ms doctor` prints a full diagnostic.
- **Async jobs** — submit returns a `job_id`; `--watch` reports the outcome back to the chat.
- **Path sandbox** — every model-supplied path is resolved and must stay inside the workspace.
- **Honest results** — upstream `verification=unverified` is never reported as success.

## Requirements

| Component | Requirement |
|---|---|
| OS | Windows (Multisim and COM are Windows-only) |
| AstrBot | `>=4.16,<5` (verified on 4.29.3) |
| NI Multisim | 14.3, licensed |
| Plugin-side Python | AstrBot's bundled 64-bit interpreter, with `pip install multisim-mcp==1.3.0` |
| COM worker | **32-bit** Python + `pywin32`, pointed to by `MULTISIM_MCP_WORKER_PYTHON` |

## Quick start

1. Install the plugin (plugin market or this repository URL).
2. `pip install multisim-mcp==1.3.0` into the interpreter that runs AstrBot.
3. Install a 32-bit Python with `pywin32` and set `backend.env.MULTISIM_MCP_WORKER_PYTHON`.
4. Reload the plugin and send `/ms status` — expect `自动化：就绪（automation）`.
5. Drop a spec into the workspace and send `/ms run demo.json --watch`.

```json
{
  "netlist": "R1 in out 1k\nC1 out 0 1u\nV1 in 0 dc 5",
  "commands": "tran 0 5m 0 10u",
  "output_dir": "runs/rc_demo"
}
```

## Configuration

Everything lives in the AstrBot plugin config page. Highlights: `backend.python`, `backend.env`, `backend.tool_profile`, `workspace_root`, `timeouts.*`, `features.*`, `tool_map`. See [docs/configuration.md](docs/configuration.md).

## Documentation

| Doc | Contents |
|---|---|
| [安装部署](docs/install.md) | Step-by-step setup (Chinese) |
| [配置参考](docs/configuration.md) | All options and environment variables (Chinese) |
| [工具参考](docs/tools.md) | The 15 LLM tools, contract and error codes (Chinese) |
| [命令参考](docs/commands.md) | `/ms` subcommands and spec format (Chinese) |
| [架构说明](docs/architecture.md) | Layers, MCP client design, extension points (Chinese) |
| [故障排查](docs/troubleshooting.md) | Troubleshooting (Chinese) |

## Development

```bash
python -m unittest discover -s tests -t .   # unit tests, no Multisim needed
python -m tests.smoke_mcp                   # real MCP stdio transport smoke
python -m tests.inprocess_smoke             # Star lifecycle / tools / commands
```

## Known limitations

- Windows only; requires a licensed Multisim installation.
- End-to-end DC/AC/transient results have not been publicly regression-tested against manual baselines.
- Native circuit-editing tool names are discovered at startup and can be overridden with `tool_map`.

## License

[MIT](LICENSE). NI Multisim is commercial software by National Instruments; this plugin ships none of its components.
