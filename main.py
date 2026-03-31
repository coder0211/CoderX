"""
CoderX — Entry Point
"""
import asyncio
import sys
from rich.console import Console
from rich.panel import Panel

from config import config
from bot.telegram_bot import create_bot, setup_commands
from llm.client import get_openai_client
from orchestrator.logger import console, log

console = Console()


async def test_openai_connection():
    """Test API key immediately on startup."""
    client = get_openai_client()
    try:
        # Simple test call
        await client.models.list()
        return True, ""
    except Exception as e:
        return False, str(e)


async def main():
    def mask_key(k):
        if not k: return "MISSING"
        return f"{k[:10]}...{k[-4:]} (len: {len(k)})"

    def _mcp_status_line():
        if not config.MCP_ENABLED:
            return "[yellow]⚠[/yellow] MCP Servers: [red]Disabled[/red]"
        try:
            import json
            from pathlib import Path
            mcp_cfg = Path(__file__).parent / "mcp.json"
            data = json.loads(mcp_cfg.read_text()) if mcp_cfg.exists() else {}
            servers = data.get("mcpServers", {})
            active = [k for k, v in servers.items() if not v.get("disabled", False)]
            return (
                f"[green]✓[/green] MCP Servers: [green]Enabled[/green] "
                f"— [cyan]{len(active)}[/cyan] server(s): [dim]{', '.join(active)}[/dim]"
            )
        except Exception:
            return "[green]✓[/green] MCP Servers: [green]Enabled[/green]"

    console.print(Panel.fit(
        "[bold cyan]🤖 CoderX[/bold cyan]\n"
        "[dim]Autonomous AI Developer Bot[/dim]\n\n"
        f"[green]✓[/green] Antigravity CLI: [cyan]{config.ANTIGRAVITY_CLI}[/cyan]\n"
        f"[green]✓[/green] Default workspace: [cyan]{config.DEFAULT_WORKSPACE}[/cyan]\n"
        f"[green]✓[/green] OpenAI model: [cyan]{config.OPENAI_MODEL}[/cyan]\n"
        f"[green]✓[/green] OpenAI Key: [yellow]{mask_key(config.OPENAI_API_KEY)}[/yellow]\n"
        + _mcp_status_line(),
        title="CoderX Starting",
        border_style="cyan",
    ))

    # Validate config
    try:
        config.validate()
        console.print("[green]✓ Config validated[/green]")

        # Test OpenAI connection
        console.print("[cyan]Testing OpenAI connection...[/cyan]")
        ok, err = await test_openai_connection()
        if not ok:
            console.print(f"[red]✗ OpenAI Auth Error:[/red]\n{err}")
            console.print("\n[yellow]HINT:[/yellow] Kiểm tra file .env, đảm bảo OPENAI_API_KEY không có khoảng trắng dư thừa.")
            sys.exit(1)
        console.print("[green]✓ OpenAI Connection OK[/green]")

    except EnvironmentError as e:
        console.print(f"[red]✗ Config error:[/red]\n{e}")
        sys.exit(1)

    # ── Khởi động MCP ngay lúc bot start ──────────────────────────────────────
    mcp_bridge = None
    if config.MCP_ENABLED:
        from mcp_client.tools_bridge import get_mcp_bridge
        mcp_bridge = get_mcp_bridge()
        console.print("[cyan]Starting MCP servers...[/cyan]")
        try:
            await mcp_bridge.startup()
            if mcp_bridge.is_ready():
                tools = mcp_bridge.list_tools()
                servers = mcp_bridge._manager.connected_servers if mcp_bridge._manager else []
                console.print(
                    f"[bold green]✓ MCP ready:[/bold green] "
                    f"[cyan]{len(tools)}[/cyan] tools from [cyan]{servers}[/cyan]"
                )
            else:
                console.print("[yellow]⚠ MCP: No servers connected[/yellow]")
        except Exception as e:
            console.print(f"[red]✗ MCP startup failed:[/red] {e}")

    # Start bot
    console.print("[cyan]Starting Telegram bot...[/cyan]")
    app = create_bot()

    async with app:
        await setup_commands(app)
        await app.start()
        console.print("[bold green]✓ Bot is running! Send /start on Telegram.[/bold green]")

        await app.updater.start_polling(
            allowed_updates=["message"],
            drop_pending_updates=True,
        )

        # Keep alive with heartbeat
        try:
            last_heartbeat = 0
            while True:
                await asyncio.sleep(1)
                now = asyncio.get_event_loop().time()
                if now - last_heartbeat >= 60:
                    log("Bot is alive and listening for tasks...", style="dim")
                    last_heartbeat = now
        except (KeyboardInterrupt, asyncio.CancelledError):
            console.print("\n[yellow]Shutting down...[/yellow]")
        finally:
            await app.updater.stop()
            await app.stop()
            # ── Tắt MCP khi shutdown ───────────────────────────────────────────
            if mcp_bridge:
                try:
                    await mcp_bridge.shutdown()
                    console.print("[dim]MCP servers disconnected.[/dim]")
                except Exception:
                    pass


if __name__ == "__main__":
    asyncio.run(main())
