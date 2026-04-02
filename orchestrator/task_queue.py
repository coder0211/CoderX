"""
CoderX — Task Queue Manager
Hỗ trợ append nhiều tasks — bot tự xử lý lần lượt đến khi hết queue.
User có thể gửi nhiều /code commands, chúng se được xếp hàng và tự chạy.
"""
import asyncio
import os
from dataclasses import dataclass, field
from typing import Callable, Optional
from orchestrator.logger import log_queue


@dataclass
class QueuedTask:
    task_id: int
    user_id: int
    chat_id: int
    goal: str
    workspace: str
    notify: Callable        # Re-created on load


class TaskQueue:
    """
    FIFO queue cho autonomous agent tasks.
    - append(task) → thêm vào cuối hàng đợi
    - Bot tự xử lý khi rảnh
    - Mỗi task chạy đến COMPLETE/STUCK/FAILED trước khi lấy task tiếp
    """

    def __init__(self, user_id: int, max_size: int = 10):
        self.user_id = user_id
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._running: bool = False
        self._current_task: Optional[QueuedTask] = None
        self._task_counter: int = 0
        self._worker_task: Optional[asyncio.Task] = None
        self._current_agent = None  # AutonomousAgent instance đang chạy
        
        from orchestrator.persistence import PersistenceManager
        self.persistence = PersistenceManager()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_task(self) -> Optional[QueuedTask]:
        return self._current_task

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def live_status(self) -> dict:
        """Snapshot thực trạng agent đang chạy."""
        if self._current_agent and self._running:
            return dict(self._current_agent.live)
        return {"phase": "idle"}

    def append(self, goal: str, workspace: str, chat_id: int, notify: Callable) -> tuple[bool, int, str]:
        """
        Thêm task vào queue.
        Returns: (success, task_id, message)
        """
        from config import config
        if self._queue.qsize() >= config.MAX_QUEUE_SIZE:
            return False, -1, f"Queue đầy ({config.MAX_QUEUE_SIZE} tasks). Đợi xong rồi thêm."

        self._task_counter += 1
        # Normalize workspace path to avoid typos and relative path issues
        norm_workspace = os.path.abspath(os.path.expanduser(workspace))
        
        task = QueuedTask(
            task_id=self._task_counter,
            user_id=self.user_id,
            chat_id=chat_id,
            goal=goal,
            workspace=norm_workspace,
            notify=notify,
        )

        try:
            self._queue.put_nowait(task)
            self._save_queue()
        except asyncio.QueueFull:
            return False, -1, "Queue đầy."

        position = self._queue.qsize()
        if self._running:
            return True, task.task_id, f"Task #{task.task_id} xếp hàng (vị trí {position})"
        else:
            return True, task.task_id, f"Task #{task.task_id} bắt đầu ngay"

    def _save_queue(self) -> None:
        """Lưu trạng thái hàng đợi hiện tại xuống đĩa."""
        pending_list = list(self._queue._queue)
        tasks_data = []
        for t in pending_list:
            tasks_data.append({
                "task_id":   t.task_id,
                "user_id":   t.user_id,
                "chat_id":   t.chat_id,
                "goal":      t.goal,
                "workspace": t.workspace,
            })
        self.persistence.save_queue(self.user_id, tasks_data)

    def load_from_disk(self, notify_factory: Callable[[int], Callable]) -> int:
        """
        Nạp tasks từ đĩa vào hàng đợi.
        `notify_factory` là hàm nhận `chat_id` và trả về hàm `notify`.
        """
        tasks_data = self.persistence.load_queue(self.user_id)
        count = 0
        for data in tasks_data:
            # Normalize reloaded paths (fixes legacy typos)
            norm_workspace = os.path.abspath(os.path.expanduser(data["workspace"]))
            
            task = QueuedTask(
                task_id   = data["task_id"],
                user_id   = data["user_id"],
                chat_id   = data["chat_id"],
                goal      = data["goal"],
                workspace = norm_workspace,
                notify    = notify_factory(data["chat_id"]),
            )
            try:
                self._queue.put_nowait(task)
                self._task_counter = max(self._task_counter, task.task_id)
                count += 1
            except asyncio.QueueFull:
                break
        return count

    def start_worker(self) -> None:
        """Khởi động background worker xử lý queue."""
        if self._worker_task and not self._worker_task.done():
            return
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _worker_loop(self) -> None:
        """Background worker: lấy task từ queue và chạy."""
        from orchestrator.orchestrator_loop import OpenClawOrchestrator
        from orchestrator.agent_loop import AutonomousAgent

        while True:
            task = await self._queue.get()
            self._running = True
            self._current_task = task

            try:
                log_msg = f"[Queue Worker: Step 1] Task #{task.task_id} bắt đầu: {task.goal}"
                log_queue(log_msg)
                
                # Use Orchestrator (OpenClaw Style)
                orchestrator = OpenClawOrchestrator(notify=task.notify)
                self._current_agent = orchestrator  # Track for status status
                await orchestrator.run(task.goal, task.workspace)
                self._current_agent = None

                remaining = self._queue.qsize()
                log_queue(f"[Queue Worker: Step 2] Task #{task.task_id} hoàn thành!")
                if remaining > 0:
                    await task.notify(
                        f"✅ Em làm xong Task #{task.task_id} rồi nha!\n"
                        f"👉 Quay lại chiến tiếp {remaining} task còn lại trong hàng đợi..."
                    )
                else:
                    await task.notify(
                        f"✅ Em làm xong Task #{task.task_id} rồi nha!\n"
                        f"☕ Hết việc rồi, anh check thử xem oke chưa nhé!"
                    )

            except asyncio.CancelledError:
                await task.notify(f"🛑 Task #{task.task_id} bị hủy.")
                raise
            except Exception as e:
                import traceback
                from orchestrator.logger import log_error
                log_error(f"[Queue Error] Task #{task.task_id} crashed:\n{traceback.format_exc()}")
                await task.notify(f"❌ Task #{task.task_id} lỗi: `{e}`")
            finally:
                self._queue.task_done()
                self._running = False
                self._current_task = None
                self._save_queue() # Cập nhật lại queue sau khi hoàn thành task
