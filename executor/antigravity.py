"""
CoderX — Antigravity CLI Executor
Gọi `antigravity chat --mode agent` với prompt, mở đúng workspace.
"""
import asyncio
import os
import subprocess
from pathlib import Path

from config import config


class AntigravityExecutor:
    """
    Wrapper cho Antigravity CLI.
    Mỗi lần gọi run() sẽ:
    1. Đảm bảo Antigravity đang chạy
    2. Mở workspace đúng
    3. Gọi `antigravity chat --mode agent "<prompt>"`
    """

    def __init__(self):
        self.cli = config.ANTIGRAVITY_CLI
        self._current_workspace: str | None = None

    def is_running(self) -> bool:
        """Check xem Antigravity process có đang chạy không."""
        result = subprocess.run(
            ["pgrep", "-f", "Antigravity.app"],
            capture_output=True,
        )
        return result.returncode == 0

    async def ensure_open(self, workspace: str) -> None:
        """Đảm bảo Antigravity đang mở với đúng workspace."""
        if not self.is_running():
            # Mở Antigravity
            subprocess.Popen(
                ["open", "/Applications/Antigravity.app"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await asyncio.sleep(3)  # Đợi app khởi động

        # Mở workspace nếu chưa mở hoặc workspace thay đổi
        if workspace != self._current_workspace:
            proc = await asyncio.create_subprocess_exec(
                self.cli,
                "--reuse-window",
                workspace,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            self._current_workspace = workspace
            await asyncio.sleep(1)  # Đợi workspace load

    async def run(
        self,
        prompt: str,
        workspace: str,
        mode: str = "agent",
    ) -> tuple[bool, str]:
        """
        Gọi Antigravity chat với prompt.

        Args:
            prompt: Yêu cầu gửi cho Antigravity Agent
            workspace: Đường dẫn workspace
            mode: 'agent' | 'ask' | 'edit'

        Returns:
            (success, message)
        """
        await self.ensure_open(workspace)

        cmd = [
            self.cli,
            "chat",
            "--mode", mode,
            "--reuse-window",
            prompt,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=10,  # CLI sẽ return ngay sau khi mở chat
            )
            return True, stdout.decode() if stdout else ""
        except asyncio.TimeoutError:
            # Bình thường — CLI mở chat rồi return, agent vẫn đang chạy trong GUI
            return True, "Chat opened in Antigravity"
        except Exception as e:
            return False, str(e)
