"""
CoderX — Workspace File System Monitor
Theo dõi file changes để phát hiện khi Antigravity Agent hoàn thành một step.

Completion detection priority:
  1. `.coderx/step_{id}_done.json` xuất hiện → DONE (agent signal)
  2. `.coderx/git_confirm_needed.json` → GIT_CONFIRM (cần user hỏi)
  3. Idle 60s không có file changes → IDLE_DONE (assume complete)
  4. Hard 15 phút → CANCELLED_CONTINUE (cancel, chuyển sang step tiếp)
"""
import asyncio
import json
import time
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from config import config


class _ChangeHandler(FileSystemEventHandler):
    def __init__(self):
        self.last_change_time: float = time.time()
        self.changed_files: set[str] = set()

    def on_any_event(self, event: FileSystemEvent):
        self.last_change_time = time.time()
        self.changed_files.add(event.src_path)


class WorkspaceMonitor:
    """
    Monitor workspace để detect:
    - Done marker → step xong
    - Git confirm needed → hỏi user
    - Idle → assume xong
    - 15 min hard → cancel + continue
    """

    def __init__(self, workspace: str):
        self.workspace = workspace
        self.coderx_dir = Path(workspace) / config.CODERX_DIR
        self._handler = _ChangeHandler()
        self._observer = Observer()

    def start(self):
        self.coderx_dir.mkdir(parents=True, exist_ok=True)
        self._observer.schedule(self._handler, self.workspace, recursive=True)
        self._observer.start()

    def stop(self):
        self._observer.stop()
        self._observer.join()

    def get_changed_files(self) -> list[str]:
        files = list(self._handler.changed_files)
        self._handler.changed_files.clear()
        return files

    async def wait_for_step_done(
        self,
        step_id: int,
        timeout: int = None,
        idle_timeout: int = None,
        progress_callback: Optional[Callable] = None,
    ) -> dict:
        """
        Đợi Antigravity hoàn thành step.
        
        Returns dict với keys: status, summary, files_changed, elapsed
        status values:
          done              — Agent tự signal xong
          idle_done         — 60s không có changes → assume xong
          git_confirm       — Agent cần confirm trước khi push git
          cancelled_continue — Quá 15 phút → cancel, tiếp tục
        """
        timeout      = timeout      or config.STEP_TIMEOUT       # 900s = 15 min
        idle_timeout = idle_timeout or config.STEP_IDLE_TIMEOUT  # 60s

        done_file        = self.coderx_dir / f"step_{step_id}_done.json"
        git_confirm_file = self.coderx_dir / "git_confirm_needed.json"

        start_time    = time.time()
        last_activity = time.time()
        last_progress = time.time()
        check_interval = 1.0

        # Reset activity baseline to now (ignore pre-existing noise)
        self._handler.last_change_time = time.time()
        self._handler.changed_files.clear()

        while True:
            await asyncio.sleep(check_interval)
            now     = time.time()
            elapsed = now - start_time

            # ── 1. Done marker (highest priority) ─────────────────────────────
            if done_file.exists():
                try:
                    result = json.loads(done_file.read_text())
                    done_file.unlink()
                    return {
                        "status":        "done",
                        "summary":       result.get("summary", "Agent completed step"),
                        "files_changed": result.get("files_changed", []),
                        "elapsed":       elapsed,
                    }
                except (json.JSONDecodeError, OSError):
                    pass  # File đang ghi dở, đợi thêm 1 tick

            # ── 2. Git confirm needed ──────────────────────────────────────────
            if git_confirm_file.exists():
                try:
                    data = json.loads(git_confirm_file.read_text())
                    git_confirm_file.unlink()
                    return {
                        "status":        "git_confirm",
                        "summary":       data.get("reason", "Git operation needs confirmation"),
                        "git_command":   data.get("command", ""),
                        "files_changed": self.get_changed_files(),
                        "elapsed":       elapsed,
                    }
                except (json.JSONDecodeError, OSError):
                    pass

            # ── 3. Track file activity ─────────────────────────────────────────
            if self._handler.last_change_time > last_activity:
                last_activity = self._handler.last_change_time
                changed = self.get_changed_files()
                relevant = [
                    f for f in changed
                    if ".coderx" not in f and ".git" not in f
                ]
                if relevant and progress_callback:
                    name = Path(relevant[-1]).name
                    await progress_callback(f"📝 `{name}`")

            # ── 4. Progress heartbeat every 30s ───────────────────────────────
            if now - last_progress >= 30 and progress_callback:
                last_progress = now
                mins = int(elapsed // 60)
                secs = int(elapsed % 60)
                remain = int((timeout - elapsed) // 60)
                await progress_callback(
                    f"⌛ Antigravity vẫn đang chạy... {mins}:{secs:02d} "
                    f"(tối đa {remain} phút nữa)"
                )

            # ── 5. Idle timeout — không có gì thay đổi trong 60s ─────────────
            idle_secs = now - last_activity
            if idle_secs >= idle_timeout and elapsed > 5:
                files = self.get_changed_files()
                if progress_callback:
                    await progress_callback(
                        f"💤 Không có file changes trong {idle_timeout}s "
                        f"→ Coi như bước đã xong"
                    )
                return {
                    "status":        "idle_done",
                    "summary":       f"⚠️ Không nhận được signal 'done' từ Agent sau {idle_timeout}s im lặng. "
                                     f"Có thể Agent đã xong hoặc bị kẹt. Cần kiểm tra lại workspace.",
                    "files_changed": files,
                    "elapsed":       elapsed,
                }

            # ── 6. Hard 15-min timeout → cancel + continue ────────────────────
            if elapsed >= timeout:
                if progress_callback:
                    await progress_callback(
                        f"⚡ Quá {timeout//60} phút — tự cancel bước này, "
                        f"chuyển sang bước tiếp theo"
                    )
                return {
                    "status":        "cancelled_continue",
                    "summary":       f"Step cancelled after {timeout//60}min, agent will continue",
                    "files_changed": self.get_changed_files(),
                    "elapsed":       elapsed,
                }

    def get_step_context(self, workspace: str) -> str:
        context_parts = []
        coderx_dir = Path(workspace) / config.CODERX_DIR

        for done_file in sorted(coderx_dir.glob("step_*_done.json")):
            try:
                data = json.loads(done_file.read_text())
                step_id = done_file.stem.split("_")[1]
                context_parts.append(
                    f"Step {step_id} completed: {data.get('summary', '')}\n"
                    f"Files changed: {', '.join(data.get('files_changed', []))}"
                )
            except Exception:
                pass

        return "\n\n".join(context_parts) if context_parts else ""

