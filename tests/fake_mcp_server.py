"""最小 MCP stdio 服务器，用于验证插件的传输层（不需要 Multisim）。

配套脚本：``python -m tests.smoke_mcp``。
兼容 mcp SDK 1.x（FastMCP）与 2.x（MCPServer，FastMCP 在 2.0 改名为 MCPServer）。
"""

from __future__ import annotations

try:  # mcp < 2
    from mcp.server.fastmcp import FastMCP as _Server
except ModuleNotFoundError:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server

server = _Server("fake-multisim")


@server.tool()
def runtime_status() -> dict:
    return {"ok": True, "api_name": "fake-multisim", "api_version": 1, "ready": True}


@server.tool()
def submit_circuit_experiment(netlist: str = "") -> dict:
    return {"job_id": "smoke-job-1", "state": "queued", "netlist": netlist}


@server.tool()
def get_experiment_job(job_id: str) -> dict:
    return {"job_id": job_id, "state": "succeeded", "verification": "pass"}


@server.tool()
def get_experiment_summary(job_id: str) -> dict:
    return {"job_id": job_id, "verification": "unverified", "artifacts": []}


@server.tool()
def open_circuit_file(path: str) -> dict:
    return {"opened": path}


if __name__ == "__main__":
    server.run(transport="stdio")
