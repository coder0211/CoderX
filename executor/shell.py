"""
CoderX — Shell Executor
Chạy shell commands (npm, pip, git...) trong workspace.
"""
import asyncio
import os
import traceback
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
        """
        Check xem command có an toàn và nằm trong phạm vi workspace không.
        Chặn tuyệt đối việc thoát khỏi root dự án qua '../' hoặc đường dẫn tuyệt đối.
        """
        cmd = command.strip()
        cmd_lower = cmd.lower()
        
        # 1. Kiểm tra prefix hợp lệ
        if not any(cmd_lower.startswith(prefix) for prefix in self.ALLOWED_PREFIXES):
            return False
            
        # 2. Chặn thoát khỏi thư mục qua '..'
        if ".." in cmd:
            return False
            
        # 3. Chặn đường dẫn tuyệt đối (/) hoặc đường dẫn người dùng (~) 
        # TRỪ KHI nó chính là workspace root (hiếm gặp nhưng cần cẩn thận)
        parts = cmd.split()
        for part in parts:
            if part.startswith("/") or part.startswith("~"):
                # Nếu là đường dẫn tuyệt đối, nó phải bắt đầu bằng path tới workspace
                if not part.startswith(self.workspace):
                    return False
                    
        return True

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
            error_msg = f"Shell subprocess error: {str(e)}\n{traceback.format_exc()}"
            return False, "", error_msg.strip()
