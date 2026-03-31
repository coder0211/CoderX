"""
CoderX — Entry Point
"""
import asyncio
import sys
from rich.console import Console
from rich.panel import Panel

from config import config
from bot.telegram_bot import create_bot, setup_commands

console = Console()


async def main():
    console.print(Panel.fit(
        "[bold cyan]🤖 CoderX[/bold cyan]\n"
        "[dim]Autonomous AI Developer Bot[/dim]\n\n"
        f"[green]✓[/green] Antigravity CLI: [cyan]{config.ANTIGRAVITY_CLI}[/cyan]\n"
        f"[green]✓[/green] Default workspace: [cyan]{config.DEFAULT_WORKSPACE}[/cyan]\n"
        f"[green]✓[/green] OpenAI model: [cyan]{config.OPENAI_MODEL}[/cyan]",
        title="CoderX Starting",
        border_style="cyan",
    ))

    # Validate config
    try:
        config.validate()
        console.print("[green]✓ Config validated[/green]")
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
