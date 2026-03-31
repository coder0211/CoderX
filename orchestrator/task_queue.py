"""
CoderX — Task Queue Manager
Hỗ trợ append nhiều tasks — bot tự xử lý lần lượt đến khi hết queue.
User có thể gửi nhiều /code commands, chúng se được xếp hàng và tự chạy.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class QueuedTask:
    task_id: int
    goal: str
    workspace: str
    notify: Callable


class TaskQueue:
    """
    FIFO queue cho autonomous agent tasks.
    - append(task) → thêm vào cuối hàng đợi
    - Bot tự xử lý khi rảnh
    - Mỗi task chạy đến COMPLETE/STUCK/FAILED trước khi lấy task tiếp
    """

    def __init__(self, max_size: int = 10):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._running: bool = False
        self._current_task: Optional[QueuedTask] = None
        self._task_counter: int = 0
        self._worker_task: Optional[asyncio.Task] = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_task(self) -> Optional[QueuedTask]:
        return self._current_task

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    def append(self, goal: str, workspace: str, notify: Callable) -> tuple[bool, int, str]:
        """
        Thêm task vào queue.
        Returns: (success, task_id, message)
        """
        from config import config
        if self._queue.qsize() >= config.MAX_QUEUE_SIZE:
            return False, -1, f"Queue đầy ({config.MAX_QUEUE_SIZE} tasks). Đợi xong rồi thêm."

        self._task_counter += 1
        task = QueuedTask(
            task_id=self._task_counter,
            goal=goal,
            workspace=workspace,
            notify=notify,
        )

        try:
            self._queue.put_nowait(task)
        except asyncio.QueueFull:
            return False, -1, "Queue đầy."

        position = self._queue.qsize()
        if self._running:
            return True, task.task_id, f"Task #{task.task_id} xếp hàng (vị trí {position})"
        else:
            return True, task.task_id, f"Task #{task.task_id} bắt đầu ngay"

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
        from orchestrator.agent_loop import AutonomousAgent

        while True:
            task = await self._queue.get()
            self._running = True
            self._current_task = task

            try:
                await task.notify(
                    f"🤖 *[Task #{task.task_id}] Bắt đầu*\n"
                    f"🎯 _{task.goal}_"
                )

                agent = AutonomousAgent(notify=task.notify)
                await agent.run(task.goal, task.workspace)

                remaining = self._queue.qsize()
                if remaining > 0:
                    await task.notify(
                        f"✅ Task #{task.task_id} xong!\n"
                        f"📋 Còn {remaining} task trong hàng đợi..."
                    )

            except asyncio.CancelledError:
                await task.notify(f"🛑 Task #{task.task_id} bị hủy.")
                raise
            except Exception as e:
                await task.notify(f"❌ Task #{task.task_id} lỗi: `{e}`")
            finally:
                self._queue.task_done()
                self._running = False
                self._current_task = None
