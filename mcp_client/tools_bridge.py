"""
CoderX — MCP Tools Bridge

Cầu nối giữa MCPClientManager và Agent Loop.
Cho phép agent gọi bất kỳ MCP tool nào như thể là native action.

Tích hợp flow:
  1. Khi agent_loop khởi động, MCPToolsBridge kết nối tới tất cả MCP server.
  2. Danh sách tools được đưa vào system prompt (agent biết có tool gì).
  3. Khi agent quyết định CALL_MCP_TOOL → bridge.execute() được gọi.
  4. Kết quả được trả về agent như một Observation bình thường.
"""
from __future__ import annotations

import json
import os
from typing import Any

from mcp_client.client import MCPClientManager
from mcp_client.registry import MCPRegistry
from orchestrator.logger import log


class MCPToolsBridge:
    """
    Singleton wrapper để dễ dùng trong agent_loop.

    Usage:
        bridge = MCPToolsBridge()
        await bridge.startup()            # kết nối tất cả servers

        summary = bridge.tools_summary()  # đưa vào system prompt
        result  = await bridge.execute("filesystem/read_file", {"path": "/foo.py"})

        await bridge.shutdown()           # đóng tất cả connections
    """

    def __init__(self):
        self._registry = MCPRegistry()
        self._manager: MCPClientManager | None = None
        self._ready = False
        self.workspace_root: str | None = None

    async def startup(self, force_restart: bool = False) -> None:
        """Kết nối tới tất cả MCP server được cấu hình."""
        if self._ready and not force_restart:
            return

        if force_restart:
            log("[MCP Bridge] Force restart requested — shutting down servers...", style="yellow")
            await self.shutdown()

        if self._registry.is_empty():
            log(
                "[MCP Bridge] No servers configured. "
                "Create [cyan]mcp.json[/cyan] in the project root to add MCP servers. "
                "See [dim]mcp_client/README.md[/dim] for examples.",
                style="yellow",
            )
            return

        log(
            f"[MCP Bridge] Connecting to {len(self._registry)} server(s): "
            f"{[s.name for s in self._registry.all()]}",
            category="MCP",
            style="cyan",
        )

        self._manager = MCPClientManager(self._registry)
        await self._manager.connect_all()
        self._ready = True

        if self._manager.is_connected():
            log(
                f"[MCP Bridge] ✅ Ready — {len(self._manager.list_all_tools())} tools available "
                f"from: {self._manager.connected_servers}",
                category="MCP",
                style="bold green",
            )
        else:
            log("[MCP Bridge] ⚠️  No servers connected.", category="MCP", style="yellow")

    async def shutdown(self) -> None:
        """Đóng tất cả connections."""
        if self._manager:
            await self._manager.disconnect_all()
            self._manager = None
        self._ready = False
        log("[MCP Bridge] Shutdown complete.", category="MCP", style="dim")

    def is_ready(self) -> bool:
        return self._ready and self._manager is not None and self._manager.is_connected()

    def tools_summary(self) -> str:
        """
        Trả về mô tả tất cả MCP tools để đưa vào system prompt.
        Empty string nếu không có tools.
        """
        if not self._manager:
            return ""
        return self._manager.get_tools_summary()

    def list_tools(self) -> list[dict[str, Any]]:
        """Danh sách tool dưới dạng dicts."""
        if not self._manager:
            return []
        return self._manager.list_all_tools()

    def _is_safe_path(self, path: str) -> bool:
        """Kiểm tra đường dẫn có nằm trong workspace_root không."""
        if not self.workspace_root:
            return True
            
        import os
        root = os.path.abspath(self.workspace_root)
        try:
            if not os.path.isabs(path):
                target = os.path.abspath(os.path.join(root, path))
            else:
                target = os.path.abspath(path)
                
            # Sử dụng commonpath để đảm bảo logic thư mục chính xác
            return os.path.commonpath([root]) == os.path.commonpath([root, target])
        except Exception:
            return False

    async def execute(self, tool_name: str, arguments: dict[str, Any] | str) -> str:
        """
        Thực thi một MCP tool.

        Args:
            tool_name: "server_name/tool_name" — vd: "filesystem/read_file"
            arguments: dict tham số, hoặc JSON string (agent thường trả về JSON string)

        Returns:
            Kết quả dạng string sẵn sàng đưa vào observation
        """
        if not self._manager:
            return "Error: MCP bridge not started. Call startup() first."

        # Parse arguments nếu là JSON string
        if isinstance(arguments, str):
            arguments = arguments.strip()
            if arguments:
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError as e:
                    return f"Error: Invalid JSON arguments for MCP tool: {e}\nGot: {arguments}"
            else:
                arguments = {}

        log(f"[MCP Bridge] Execute: {tool_name} | args: {arguments}", category="MCP", style="cyan")
        
        # Security Check: Nếu là tool filesystem, kiểm tra đường dẫn
        if tool_name.startswith("filesystem/") and "path" in arguments:
            path = arguments["path"]
            if not self._is_safe_path(path):
                msg = f"Security Error: Access denied. Path '{path}' is outside workspace root."
                log(f"[MCP Bridge] ❌ {msg}", category="MCP", style="bold red")
                return msg

        result = await self._manager.call_tool(tool_name, arguments)
        return result

    # ── Context manager ───────────────────────────────────────────────────────

    async def __aenter__(self) -> "MCPToolsBridge":
        await self.startup()
        return self

    async def __aexit__(self, *args) -> None:
        await self.shutdown()


# Global singleton — dùng trong agent_loop.py
_bridge: MCPToolsBridge | None = None


def get_mcp_bridge() -> MCPToolsBridge:
    """Lấy hoặc tạo global MCP bridge instance."""
    global _bridge
    if _bridge is None:
        _bridge = MCPToolsBridge()
    return _bridge
