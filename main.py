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

    console.print(Panel.fit(
        "[bold cyan]🤖 CoderX[/bold cyan]\n"
        "[dim]Autonomous AI Developer Bot[/dim]\n\n"
        f"[green]✓[/green] Antigravity CLI: [cyan]{config.ANTIGRAVITY_CLI}[/cyan]\n"
        f"[green]✓[/green] Default workspace: [cyan]{config.DEFAULT_WORKSPACE}[/cyan]\n"
        f"[green]✓[/green] OpenAI model: [cyan]{config.OPENAI_MODEL}[/cyan]\n"
        f"[green]✓[/green] OpenAI Key: [yellow]{mask_key(config.OPENAI_API_KEY)}[/yellow]",
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

        # Keep alive
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            console.print("\n[yellow]Shutting down...[/yellow]")
        finally:
            await app.updater.stop()
            await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
