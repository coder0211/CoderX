import os
from pathlib import Path
from datetime import datetime

class MemoryManager:
    """
    Quản lý bộ nhớ dài hạn (Memory Bridge) theo kiến trúc OpenClaw.
    Lưu trữ trạng thái, kết quả và context vào .coderx/MEMORY.md.
    """

    def __init__(self, workspace: str):
        self.workspace = Path(workspace)
        self.coderx_dir = self.workspace / ".coderx"
        self.memory_file = self.coderx_dir / "MEMORY.md"
        self._ensure_exists()

    def _ensure_exists(self):
        """Đảm bảo thư mục và file MEMORY.md tồn tại."""
        self.coderx_dir.mkdir(parents=True, exist_ok=True)
        if not self.memory_file.exists():
            content = (
                "# 🧠 CoderX Long-Term Memory (OpenClaw Bridge)\n"
                "Đây là bộ nhớ liên tục chia sẻ giữa các thành phần của CoderX.\n\n"
                "## 🎯 Mục tiêu hiện tại\n"
                "(Chưa có mục tiêu nào)\n\n"
                "## 📜 Lịch sử các bước\n"
            )
            self.memory_file.write_text(content, encoding="utf-8")

    def reset_with_goal(self, task_goal: str):
        """Reset bộ nhớ cho một task mới."""
        content = (
            "# 🧠 CoderX Long-Term Memory (OpenClaw Bridge)\n"
            "Đây là bộ nhớ liên tục chia sẻ giữa các thành phần của CoderX.\n"
            "Mọi thay đổi, quyết định quan trọng đều được ghi lại ở đây.\n\n"
            "## 🎯 Mục tiêu hiện tại\n"
            f"**[ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ]** {task_goal}\n\n"
            "## 📜 Lịch sử các bước\n"
        )
        self.memory_file.write_text(content, encoding="utf-8")

    def append_decision(self, step_id: int, title: str, status: str, summary: str):
        """Ghi nhận một quyết định / kết quả bước vừa thực hiện."""
        icon = "✅" if status in ("done", "idle_done") else ("❌" if status == "error" else "⚠️")
        entry = (
            f"\n### Bước {step_id}: {title}\n"
            f"- **Thời gian:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"- **Trạng thái:** {icon} {status}\n"
            f"- **Tóm tắt:**\n{summary}\n"
        )
        with open(self.memory_file, "a", encoding="utf-8") as f:
            f.write(entry)

    def read_memory(self) -> str:
        """Đọc toàn bộ nội dung trong bộ nhớ hiện hành."""
        if not self.memory_file.exists():
            return "No memory file exists yet."
        return self.memory_file.read_text(encoding="utf-8")

    def get_memory_path(self) -> str:
        """Trả về đường dẫn tuyệt đối của MEMORY.md để truyền cho CLI."""
        return str(self.memory_file.absolute())
