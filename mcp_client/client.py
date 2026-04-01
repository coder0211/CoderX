"""
CoderX — MCP Client Manager

Quản lý kết nối tới nhiều MCP server cùng lúc.
Hỗ trợ:
  - stdio transport  : spawn child process, communicate qua stdin/stdout
  - http/SSE transport: kết nối tới remote MCP server qua HTTP

Dùng thư viện `mcp` (pip install "mcp[cli]").
"""
from __future__ import annotations

import asyncio
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.types import Tool

from mcp_client.registry import MCPServerConfig, MCPRegistry
from orchestrator.logger import log


class ConnectedServer:
    """Đại diện một MCP server đang kết nối."""

    def __init__(self, config: MCPServerConfig, session: ClientSession):
        self.config = config
        self.session = session
        self.tools: list[Tool] = []

    @property
    def name(self) -> str:
        return self.config.name

    async def refresh_tools(self) -> None:
        """Lấy danh sách tools từ server."""
        result = await self.session.list_tools()
        self.tools = result.tools
        log(
            f"[MCP Client] '{self.name}' has {len(self.tools)} tool(s): "
            f"{[t.name for t in self.tools]}",
            style="dim",
        )

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """
        Gọi một tool trên server này.
        Trả về string kết quả (đã xử lý để phù hợp với context LLM).
        """
        log(f"[MCP Client] Calling '{self.name}/{tool_name}' with {arguments}", style="cyan")
        result = await self.session.call_tool(tool_name, arguments=arguments)

        # Gộp tất cả content block thành string
        parts: list[str] = []
        for block in result.content:
            if hasattr(block, "text"):
                parts.append(block.text)
            else:
                parts.append(str(block))

        output = "\n".join(parts)
        log(f"[MCP Client] '{tool_name}' returned {len(output)} chars", style="dim")
        return output


class MCPClientManager:
    """
    Quản lý vòng đời của tất cả MCP server connections.

    Usage:
        manager = MCPClientManager(registry)
        async with manager:
            tools = manager.list_all_tools()
            result = await manager.call_tool("filesystem/read_file", {"path": "/foo/bar.py"})
    """

    def __init__(self, registry: MCPRegistry):
        self._registry = registry
        self._servers: dict[str, ConnectedServer] = {}
        self._exit_stack_tasks: list[asyncio.Task] = []
        self._context_managers: list[Any] = []

    async def connect_all(self) -> None:
        """Kết nối tới tất cả server trong registry."""
        if self._registry.is_empty():
            log("[MCP Client] No MCP servers configured — skipping", style="yellow")
            return

        for cfg in self._registry.all():
            try:
                await self._connect(cfg)
            except Exception as e:
                log(f"[MCP Client] Failed to connect to '{cfg.name}': {e}", style="bold red")

    async def _connect(self, cfg: MCPServerConfig) -> None:
        """Kết nối tới một MCP server."""
        log(f"[MCP Client] Connecting to '{cfg.name}' ({cfg.transport})...", style="cyan")

        if cfg.transport == "stdio":
            await self._connect_stdio(cfg)
        elif cfg.transport in ("http", "sse"):
            await self._connect_sse(cfg)

    async def _connect_stdio(self, cfg: MCPServerConfig) -> None:
        """Spawn process và tạo stdio MCP session."""
        import os

        server_params = StdioServerParameters(
            command=cfg.command,
            args=cfg.args,
            env={**os.environ, **cfg.env} if cfg.env else None,
            cwd=cfg.cwd,
        )

        # stdio_client là async context manager: tạo streams rồi trả về (read, write)
        # Ta lưu cm để __aexit__ có thể cleanup đúng cách
        cm = stdio_client(server_params)
        read, write = await cm.__aenter__()
        self._context_managers.append((cm, read, write))

        session = ClientSession(read, write)
        await session.__aenter__()
        await session.initialize()

        server = ConnectedServer(cfg, session)
        await server.refresh_tools()
        self._servers[cfg.name] = server
        log(f"[MCP Client] ✅ Connected (stdio): '{cfg.name}'", style="green")

    async def _connect_sse(self, cfg: MCPServerConfig) -> None:
        """Kết nối HTTP/SSE MCP session."""
        cm = sse_client(cfg.url)
        read, write = await cm.__aenter__()
        self._context_managers.append((cm, read, write))

        session = ClientSession(read, write)
        await session.__aenter__()
        await session.initialize()

        server = ConnectedServer(cfg, session)
        await server.refresh_tools()
        self._servers[cfg.name] = server
        log(f"[MCP Client] ✅ Connected (SSE): '{cfg.name}' @ {cfg.url}", style="green")

    async def disconnect_all(self) -> None:
        """Đóng tất cả kết nối."""
        for name, server in self._servers.items():
            try:
                await server.session.__aexit__(None, None, None)
                log(f"[MCP Client] Disconnected: '{name}'", style="dim")
            except Exception:
                pass

        for cm, *_ in self._context_managers:
            try:
                await cm.__aexit__(None, None, None)
            except Exception:
                pass

        self._servers.clear()
        self._context_managers.clear()

    # ── Context manager support ───────────────────────────────────────────────

    async def __aenter__(self) -> "MCPClientManager":
        await self.connect_all()
        return self

    async def __aexit__(self, *args) -> None:
        await self.disconnect_all()

    # ── Tool discovery ────────────────────────────────────────────────────────

    def list_all_tools(self) -> list[dict[str, Any]]:
        """
        Trả về danh sách tất cả tool từ mọi server đang kết nối.
        Format: {"name": "server/tool", "description": ..., "schema": ...}
        """
        result: list[dict[str, Any]] = []
        for server_name, server in self._servers.items():
            for tool in server.tools:
                result.append({
                    "name": f"{server_name}/{tool.name}",
                    "description": tool.description or "",
                    "schema": tool.inputSchema,
                    "_server": server_name,
                    "_tool": tool.name,
                })
        return result

    def get_tools_summary(self) -> str:
        """Trả về string mô tả tất cả tools để đưa vào system prompt."""
        tools = self.list_all_tools()
        if not tools:
            return "No MCP tools available."

        lines = ["## Available MCP Tools\n"]
        current_server = None
        for t in tools:
            server = t["_server"]
            if server != current_server:
                lines.append(f"\n### [{server}]")
                current_server = server
            schema = t["schema"] or {}
            props = schema.get("properties", {})
            param_str = ", ".join(props.keys()) if props else "no params"
            lines.append(f"- **{t['name']}**({param_str}): {t['description']}")

        return "\n".join(lines)

    # ── Tool execution ────────────────────────────────────────────────────────

    async def call_tool(self, qualified_name: str, arguments: dict[str, Any]) -> str:
        """
        Gọi một tool theo tên đầy đủ "server_name/tool_name".

        Args:
            qualified_name: vd "filesystem/read_file" hoặc "github/create_issue"
            arguments: dict các tham số

        Returns:
            Kết quả dạng string
        """
        if "/" not in qualified_name:
            return f"Error: Tool name must be 'server/tool', got: {qualified_name}"

        server_name, tool_name = qualified_name.split("/", 1)

        server = self._servers.get(server_name)
        if server is None:
            available = list(self._servers.keys())
            return (
                f"Error: Server '{server_name}' not connected. "
                f"Available: {available}"
            )

        tool_names = [t.name for t in server.tools]
        if tool_name not in tool_names:
            return (
                f"Error: Tool '{tool_name}' not found in server '{server_name}'. "
                f"Available tools: {tool_names}"
            )

        try:
            return await server.call_tool(tool_name, arguments)
        except Exception as e:
            return f"Error calling '{qualified_name}': {e}"

    def is_connected(self) -> bool:
        return len(self._servers) > 0

    @property
    def connected_servers(self) -> list[str]:
        return list(self._servers.keys())
