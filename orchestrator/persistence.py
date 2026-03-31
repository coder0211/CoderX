"""
CoderX — Persistence Utils
Lưu trữ và nạp lại hàng đợi từ file JSON.
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List

# Thư mục gốc project (chứa file này là orchestrator/, lên 1 cấp là project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class PersistenceManager:
    """
    Quản lý lưu trữ trạng thái của CoderX.
    Mặc định lưu vào thư mục `data/` ở gốc project.
    """

    def __init__(self, storage_dir: str = "data"):
        # Resolve relative paths from project root, không phải CWD
        p = Path(storage_dir)
        self.storage_dir = p if p.is_absolute() else _PROJECT_ROOT / p
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save_queue(self, user_id: int, tasks: List[Dict[str, Any]]) -> None:
        """Lưu danh sách tasks của một user vào file."""
        file_path = self.storage_dir / f"queue_{user_id}.json"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(tasks, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving queue for user {user_id}: {e}")

    def load_queue(self, user_id: int) -> List[Dict[str, Any]]:
        """Nạp danh sách tasks của một user từ file."""
        file_path = self.storage_dir / f"queue_{user_id}.json"
        if not file_path.exists():
            return []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading queue for user {user_id}: {e}")
            return []

    def list_users_with_queues(self) -> List[int]:
        """Liệt kê tất cả user đang có hàng đợi lưu trên đĩa."""
        users = []
        for f in self.storage_dir.glob("queue_*.json"):
            try:
                uid_str = f.stem.split("_")[1]
                if uid_str.isdigit():
                    users.append(int(uid_str))
            except (IndexError, ValueError):
                continue
        return users

    def delete_queue(self, user_id: int) -> None:
        """Xóa file hàng đợi của user."""
        file_path = self.storage_dir / f"queue_{user_id}.json"
        if file_path.exists():
            file_path.unlink()
