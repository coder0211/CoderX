"""
CoderX — MCP (Model Context Protocol) Client Package

Cho phép CoderX gọi tools từ các MCP server bên ngoài.
Hỗ trợ cả stdio transport (Claude Desktop, Cursor) và http/SSE transport (remote).
"""
from mcp_client.registry import MCPRegistry
from mcp_client.client import MCPClientManager
from mcp_client.tools_bridge import MCPToolsBridge

__all__ = ["MCPRegistry", "MCPClientManager", "MCPToolsBridge"]
