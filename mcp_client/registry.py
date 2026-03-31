"""
CoderX — MCP Server Registry

Đọc cấu hình MCP server từ file `mcp.json` (style giống Claude Desktop / VS Code).
Fallback về env vars nếu không tìm thấy file.

─── Format của mcp.json ─────────────────────────────────────────────────────────
{
  "mcpServers": {

    // stdio server — chạy local process (npx, python, uvx, ...)
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"],
      "env": {}                  // optional — extra env vars cho process
    },

    // stdio server với env vars
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx"
      }
    },

    // http/SSE server — kết nối remote
    "my-remote-server": {
      "url": "http://localhost:9000/sse"
    }

  }
}
─────────────────────────────────────────────────────────────────────────────────

File `mcp.json` được tìm theo thứ tự:
  1. Đường dẫn trong env var MCP_CONFIG_FILE (nếu có)
  2. <project_root>/mcp.json  (cùng thư mục với main.py)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from orchestrator.logger import log


TransportType = Literal["stdio", "http", "sse"]

# Đường dẫn mặc định của file config — cùng thư mục với registry.py/../ (project root)
_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "mcp.json"


@dataclass
class MCPServerConfig:
    """Cấu hình cho một MCP server."""
    name: str
    transport: TransportType

    # ── stdio fields ──────────────────────────────────────────────────────────
    command: str = ""           # Lệnh chạy server (vd: "npx", "python", "uvx")
    args: list[str] = field(default_factory=list)      # Tham số CLI
    env: dict[str, str] = field(default_factory=dict)  # ENV vars bổ sung

    # ── http / sse fields ─────────────────────────────────────────────────────
    url: str = ""               # URL của server (vd: "http://localhost:8765/sse")

    def __str__(self) -> str:
        if self.transport == "stdio":
            return f"[stdio] {self.name}: {self.command} {' '.join(self.args)}"
        return f"[{self.transport}] {self.name}: {self.url}"


class MCPRegistry:
    """
    Registry của các MCP server.

    Đọc từ file mcp.json theo thứ tự ưu tiên:
      1. $MCP_CONFIG_FILE  (env var override)
      2. ./mcp.json        (project root)

    Nếu không tìm thấy file, fallback đọc env vars MCP_SERVER_* (legacy).
    """

    def __init__(self, config_path: str | Path | None = None):
        self._servers: dict[str, MCPServerConfig] = {}
        self._config_path: Path | None = None
        self._load(config_path)

    # ── Loading ───────────────────────────────────────────────────────────────

    def _load(self, config_path: str | Path | None) -> None:
        """Tìm và load config từ file JSON, fallback về env vars."""
        path = self._resolve_path(config_path)

        if path and path.exists():
            self._config_path = path
            log(f"[MCP Registry] Loading config: [cyan]{path}[/cyan]", style="bold")
            self._load_from_json(path)
        else:
            # Không tìm thấy file → thử env vars (backward compat)
            if path:
                log(
                    f"[MCP Registry] Config file not found: [yellow]{path}[/yellow] "
                    f"— falling back to env vars. "
                    f"Copy [dim]mcp.example.json[/dim] → [cyan]mcp.json[/cyan] to get started.",
                    style="yellow",
                )
            self._load_from_env()

    def _resolve_path(self, override: str | Path | None) -> Path | None:
        """Xác định đường dẫn file config."""
        if override:
            return Path(override)
        # Env var override
        env_path = os.getenv("MCP_CONFIG_FILE", "").strip()
        if env_path:
            return Path(env_path)
        # Default: mcp.json ở project root
        return _DEFAULT_CONFIG_PATH

    def _load_from_json(self, path: Path) -> None:
        """Parse mcp.json và build registry."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            log(f"[MCP Registry] ❌ JSON parse error in {path}: {e}", style="bold red")
            return

        servers_raw: dict = data.get("mcpServers", {})
        if not servers_raw:
            log(f"[MCP Registry] No 'mcpServers' key found in {path.name}", style="yellow")
            return

        for name, cfg_raw in servers_raw.items():
            if not isinstance(cfg_raw, dict):
                log(f"[MCP Registry] Skip '{name}': value must be an object", style="yellow")
                continue

            server = self._parse_server(name, cfg_raw)
            if server:
                self._servers[name] = server
                log(f"[MCP Registry] ✅ Registered: {server}", style="dim")

        log(
            f"[MCP Registry] Loaded {len(self._servers)} server(s) from "
            f"[cyan]{path.name}[/cyan]",
            style="bold green",
        )

    def _parse_server(self, name: str, raw: dict) -> MCPServerConfig | None:
        """Parse một server entry từ JSON → MCPServerConfig."""

        # Nếu có "url" → http/sse transport
        if "url" in raw:
            url = raw["url"].strip()
            if not url:
                log(f"[MCP Registry] Skip '{name}': 'url' is empty", style="yellow")
                return None
            # Xác định sse hay http dựa vào URL path
            transport: TransportType = "sse" if url.endswith("/sse") else "http"
            return MCPServerConfig(name=name, transport=transport, url=url)

        # stdio transport
        command = raw.get("command", "").strip()
        if not command:
            log(
                f"[MCP Registry] Skip '{name}': missing 'command' (and no 'url'). "
                f"Entry: {raw}",
                style="yellow",
            )
            return None

        args: list[str] = raw.get("args", [])
        if not isinstance(args, list):
            args = str(args).split()

        env: dict[str, str] = raw.get("env", {}) or {}
        # Lọc chỉ giữ str values
        env = {str(k): str(v) for k, v in env.items()}

        # Disabled flag (cho phép tắt server mà không cần xóa)
        if raw.get("disabled", False):
            log(f"[MCP Registry] Skip '{name}': disabled=true", style="dim")
            return None

        return MCPServerConfig(
            name=name,
            transport="stdio",
            command=command,
            args=args,
            env=env,
        )

    # ── Legacy env var loader (backward compat) ───────────────────────────────

    _ENV_PREFIX = "MCP_SERVER_"

    def _load_from_env(self) -> None:
        """Đọc MCP_SERVER_* từ env (dùng khi không có mcp.json)."""
        names: set[str] = set()
        for key in os.environ:
            if key.startswith(self._ENV_PREFIX):
                rest = key[len(self._ENV_PREFIX):]
                parts = rest.split("_")
                if len(parts) >= 2:
                    names.add("_".join(parts[:-1]).lower())

        if not names:
            return

        log(
            f"[MCP Registry] Reading {len(names)} server(s) from env vars "
            f"(MCP_SERVER_*). Tip: migrate to mcp.json for easier config.",
            style="dim",
        )

        for name in names:
            prefix = f"{self._ENV_PREFIX}{name.upper()}_"
            transport_raw = os.getenv(f"{prefix}TRANSPORT", "stdio").lower()
            transport: TransportType = (
                transport_raw if transport_raw in ("stdio", "http", "sse") else "stdio"  # type: ignore[assignment]
            )

            if transport == "stdio":
                command = os.getenv(f"{prefix}COMMAND", "")
                args_raw = os.getenv(f"{prefix}ARGS", "")
                args = args_raw.split() if args_raw else []

                env_raw = os.getenv(f"{prefix}ENV", "")
                env: dict[str, str] = {}
                if env_raw:
                    for pair in env_raw.split(","):
                        if "=" in pair:
                            k, v = pair.split("=", 1)
                            env[k.strip()] = v.strip()

                if not command:
                    log(f"[MCP Registry] Skip env '{name}': COMMAND is empty", style="yellow")
                    continue

                cfg = MCPServerConfig(name=name, transport="stdio", command=command, args=args, env=env)

            elif transport in ("http", "sse"):
                url = os.getenv(f"{prefix}URL", "")
                if not url:
                    log(f"[MCP Registry] Skip env '{name}': URL is empty", style="yellow")
                    continue
                cfg = MCPServerConfig(name=name, transport=transport, url=url)  # type: ignore[arg-name]
            else:
                continue

            self._servers[name] = cfg
            log(f"[MCP Registry] Registered (env): {cfg}", style="dim")

    # ── Reload support ────────────────────────────────────────────────────────

    def reload(self) -> None:
        """Tải lại config từ file (dùng khi file thay đổi mà không restart)."""
        self._servers.clear()
        self._load(self._config_path)

    # ── Public API ────────────────────────────────────────────────────────────

    def all(self) -> list[MCPServerConfig]:
        return list(self._servers.values())

    def get(self, name: str) -> MCPServerConfig | None:
        return self._servers.get(name)

    def is_empty(self) -> bool:
        return len(self._servers) == 0

    @property
    def config_file(self) -> Path | None:
        return self._config_path

    def __len__(self) -> int:
        return len(self._servers)

    def __repr__(self) -> str:
        return f"MCPRegistry({list(self._servers.keys())})"
