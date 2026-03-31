"""
CoderX — Shared Logging System
Unifies all console output to ensure visibility and consistency.
"""
import sys
from rich.console import Console

# Unified console for the whole application
# force_terminal=True ensures colors and formatting even in some background/piped envs
console = Console(force_terminal=True, file=sys.stdout)

def log(message: str, category: str = "System", style: str = "dim"):
    """Dòng log chuẩn có prefix."""
    prefix = f"[{style}][{category}][/{style}]"
    console.print(f"{prefix} {message}")

def log_error(message: str):
    log(message, category="Error", style="bold red")

def log_success(message: str):
    log(message, category="Success", style="bold green")

def log_agent(message: str):
    # Strip markdown symbols for clean terminal output
    clean = message.replace("*", "").replace("_", "").replace("`", "")
    log(clean, category="Agent", style="cyan")

def log_queue(message: str):
    log(message, category="Queue", style="bold magenta")
