"""
CoderX — Shell Executor
Chạy shell commands (npm, pip, git...) trong workspace.
"""
import asyncio
import os
from pathlib import Path


class ShellExecutor:
    """Chạy các shell command an toàn trong workspace."""

    ALLOWED_PREFIXES = [
        "npm ", "npx ", "yarn ", "pnpm ",
        "pip ", "pip3 ", "python ", "python3 ",
        "git ", "mkdir ", "touch ", "ls ", "cat ",
        "node ", "ts-node ", "pytest ", "jest ",
        "go ", "cargo ", "make ",
        "echo ", "cp ", "mv ",
    ]

    def __init__(self, workspace: str):
        self.workspace = os.path.abspath(os.path.expanduser(workspace))

    def is_safe(self, command: str) -> bool:
        """Check xem command có an toàn không."""
        cmd = command.strip().lower()
        return any(cmd.startswith(prefix) for prefix in self.ALLOWED_PREFIXES)

    async def run(
        self,
        command: str,
        timeout: int = 120,
    ) -> tuple[bool, str, str]:
        """
        Chạy shell command trong workspace.

        Returns:
            (success, stdout, stderr)
        """
        if not self.is_safe(command):
            return False, "", f"Command not allowed: {command}"

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=self.workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "FORCE_COLOR": "0"},
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
            success = proc.returncode == 0
            return (
                success,
                stdout.decode(errors="replace"),
                stderr.decode(errors="replace"),
            )
        except asyncio.TimeoutError:
            return False, "", f"Command timed out after {timeout}s"
        except Exception as e:
            return False, "", str(e)
