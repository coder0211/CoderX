"""
CoderX — Telegram Bot (v2 with Task Queue + Git Confirm + Skills)
"""
import asyncio
import os
from pathlib import Path

from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import config
from orchestrator.task_queue import TaskQueue


# ─── Global task queue (one per bot instance) ─────────────────────────────────
task_queues: dict[int, TaskQueue] = {}  # user_id → TaskQueue
git_confirm_pending: dict[int, dict] = {}  # user_id → pending git confirm


def get_queue(user_id: int, bot=None) -> TaskQueue:
    if user_id not in task_queues:
        q = TaskQueue(user_id=user_id, max_size=config.MAX_QUEUE_SIZE)
        if bot:
            # Tái tạo hàm notify từ chat_id
            def notify_factory(chat_id: int):
                async def notify(msg: str):
                    await send_to_chat(bot, chat_id, msg)
                return notify
            
            count = q.load_from_disk(notify_factory)
            if count > 0:
                print(f"Loaded {count} tasks for user {user_id}")
                q.start_worker()
        
        task_queues[user_id] = q
    return task_queues[user_id]


# ─── Session state ─────────────────────────────────────────────────────────────

class UserSession:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.workspace: str = config.DEFAULT_WORKSPACE
        self.chat_history: list[dict] = []

    def add_message(self, role: str, content: str):
        self.chat_history.append({"role": role, "content": content})
        # Keep only last 20 messages (10 turns)
        if len(self.chat_history) > 20:
            self.chat_history = self.chat_history[-20:]

    def clear_history(self):
        self.chat_history = []


sessions: dict[int, UserSession] = {}


def get_session(user_id: int) -> UserSession:
    if user_id not in sessions:
        sessions[user_id] = UserSession(user_id)
    return sessions[user_id]


# ─── Auth ──────────────────────────────────────────────────────────────────────

def is_allowed(user_id: int) -> bool:
    if not config.ALLOWED_USER_IDS:
        return True
    return user_id in config.ALLOWED_USER_IDS


# ─── Helpers ───────────────────────────────────────────────────────────────────

async def send(update: Update, text: str, parse_mode=ParseMode.MARKDOWN) -> None:
    max_len = 4000
    chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode=parse_mode)
        except Exception:
            await update.message.reply_text(chunk, parse_mode=None)


async def send_to_chat(bot, chat_id: int, text: str) -> None:
    max_len = 4000
    chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    for chunk in chunks:
        try:
            await bot.send_message(chat_id, chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await bot.send_message(chat_id, chunk)


# ─── Commands ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_allowed(uid):
        return
    session = get_session(uid)
    q = get_queue(uid)

    text = (
        "👾 *CoderX* — Autonomous AI Developer\n\n"
        f"📁 Workspace: `{session.workspace}`\n"
        f"📋 Queue: {q.queue_size} tasks\n\n"
        "*Commands:*\n"
        "  `/code <task>` — Thêm coding task vào queue\n"
        "  `/queue` — Xem hàng đợi\n"
        "  `/ask <question>` — Hỏi ChatGPT (có nhớ lịch sử)\n"
        "  `/clear` — Xóa lịch sử chat\n"
        "  `/workspace <path>` — Đổi workspace\n"
        "  `/status` — Trạng thái agent\n"
        "  `/stop` — Dừng task hiện tại\n"
        "  `/ls` — List files\n"
    )
    await send(update, text)


async def cmd_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_allowed(uid):
        return
    if not ctx.args:
        await send(update, "💡 Usage: `/code <mô tả task>`")
        return

    session = get_session(uid)
    task_goal = " ".join(ctx.args)
    q = get_queue(uid)

    # Make notifier bound to this chat
    bot = ctx.bot
    chat_id = update.effective_chat.id

    async def notify(msg: str):
        await send_to_chat(bot, chat_id, msg)

    success, task_id, msg = q.append(task_goal, session.workspace, chat_id, notify)

    if not success:
        await send(update, f"⚠️ {msg}")
        return

    q.start_worker()  # No-op nếu đã running

    status = "🟡 *Đã xếp hàng*" if q.is_running else "🟢 *Bắt đầu ngay*"
    pos = q.queue_size
    text = (
        f"{status}\n"
        f"📌 Task #{task_id}: _{task_goal}_\n"
        f"📋 Vị trí trong queue: {pos}\n"
        f"{msg}"
    )
    await send(update, text)


async def cmd_queue(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_allowed(uid):
        return

    q = get_queue(uid)
    if q.is_running and q.current_task:
        ct = q.current_task
        text = (
            f"🔄 *Đang chạy:* Task #{ct.task_id}\n"
            f"🎯 _{ct.goal}_\n\n"
            f"📋 Queue: {q.queue_size} tasks chờ"
        )
    else:
        text = f"✅ *Rảnh.* Queue: {q.queue_size} tasks"

    await send(update, text)


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_queue(update, ctx)


async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_allowed(uid):
        return

    q = get_queue(uid)
    await q.stop()
    task_queues[uid] = TaskQueue(user_id=uid, max_size=config.MAX_QUEUE_SIZE)
    task_queues[uid].persistence.delete_queue(uid) # Xóa file trên đĩa
    await send(update, "🛑 *Đã dừng agent và xóa queue.*")


async def cmd_workspace(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_allowed(uid):
        return

    if not ctx.args:
        session = get_session(uid)
        await send(update, f"📁 Workspace: `{session.workspace}`")
        return

    new_path = os.path.expanduser(" ".join(ctx.args).strip())
    if not Path(new_path).exists():
        await send(update, f"❌ Path không tồn tại: `{new_path}`")
        return

    get_session(uid).workspace = new_path
    await send(update, f"✅ Workspace → `{new_path}`")


async def cmd_onboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_allowed(uid):
        return

    session = get_session(uid)
    q = get_queue(uid)

    bot = ctx.bot
    chat_id = update.effective_chat.id

    async def notify(msg: str):
        await send_to_chat(bot, chat_id, msg)

    goal = (
        "Project Onboarding: Khám phá kiến trúc codebase này. "
        "Phân tích tech stack, cấu trúc thư mục, entry points và conventions. "
        "Viết kết quả chi tiết bằng Tiếng Việt vào file `.coderx/onboarding.md`."
    )

    success, task_id, msg = q.append(goal, session.workspace, chat_id, notify)

    if not success:
        await send(update, f"⚠️ {msg}")
        return

    q.start_worker()
    await send(update, f"🔍 *Bắt đầu Onboarding Task #{task_id}*\n🎯 _{goal}_")


async def cmd_ls(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_allowed(uid):
        return

    session = get_session(uid)
    path = Path(session.workspace)

    try:
        items = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        lines = [
            f"{'📁' if item.is_dir() else '📄'} `{item.name}`"
            for item in items[:30]
            if not item.name.startswith(".")
        ]
        text = f"📂 *{path.name}/*\n" + ("\n".join(lines) or "_Trống_")
    except Exception as e:
        text = f"❌ {e}"

    await send(update, text)


async def cmd_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_allowed(uid):
        return
    if not ctx.args:
        await send(update, "💡 Usage: `/ask <câu hỏi>`")
        return

    from llm.client import get_openai_client
    question = " ".join(ctx.args)
    session = get_session(uid)
    await send(update, "🤔 *Đang suy nghĩ...*")

    client = get_openai_client()

    messages = [
        {
            "role": "system",
            "content": "Bạn là Senior Developer. Trả lời ngắn gọn, chính xác, dùng tiếng Việt.",
        },
    ]
    messages.extend(session.chat_history)
    messages.append({"role": "user", "content": question})

    response = await client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=messages,
        temperature=0.5,
    )
    reply = response.choices[0].message.content
    session.add_message("user", question)
    session.add_message("assistant", reply)
    await send(update, f"💡 {reply}")


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_allowed(uid):
        return
    session = get_session(uid)
    session.clear_history()
    await send(update, "🧹 *Đã xóa lịch sử trò chuyện.*")


# ─── Git Confirm Handler ───────────────────────────────────────────────────────

async def handle_git_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Xử lý khi user reply YES/NO cho git confirm request.
    """
    uid = update.effective_user.id
    if not is_allowed(uid) or uid not in git_confirm_pending:
        return

    text = (update.message.text or "").strip().upper()
    pending = git_confirm_pending.pop(uid, None)
    if not pending:
        return

    if text in ("YES", "CÓ", "Y", "OK"):
        # Ghi confirmation file để agent pick up
        coderx_dir = Path(pending["workspace"]) / config.CODERX_DIR
        coderx_dir.mkdir(exist_ok=True)
        confirm_file = coderx_dir / "git_confirmed.json"
        confirm_file.write_text('{"confirmed": true, "command": "' + pending["command"] + '"}')
        await send(update, f"✅ Xác nhận! Đang chạy: `{pending['command']}`")
    else:
        coderx_dir = Path(pending["workspace"]) / config.CODERX_DIR
        coderx_dir.mkdir(exist_ok=True)
        skip_file = coderx_dir / "git_confirmed.json"
        skip_file.write_text('{"confirmed": false}')
        await send(update, "⏭️ Bỏ qua git operation, tiếp tục...")


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_allowed(uid):
        return

    text = (update.message.text or "").strip()

    # ── 1. Git confirm reply ────────────────────────────────────────
    if uid in git_confirm_pending:
        await handle_git_confirm(update, ctx)
        return

    # ── 2. Build agent context for ChatGPT ──────────────────────────
    q = get_queue(uid)
    session = get_session(uid)
    live = q.live_status
    ct = q.current_task

    # Build a context description of what's happening
    if q.is_running and ct:
        import time
        elapsed = ""
        if live.get("started_at"):
            secs = int(time.time() - live["started_at"])
            elapsed = f"{secs // 60}phút {secs % 60}giây"

        phase_vi = {
            "reasoning": "🧠 đang suy nghĩ",
            "acting":    "⚡ đang thực thi",
            "observing": "🔍 đang đánh giá kết quả",
            "starting":  "🚀 đang khởi động",
            "idle":      "✅ đang rảnh",
        }.get(live.get("phase", ""), live.get("phase", ""))

        agent_context = (
            f"Tôi đang làm việc.\n"
            f"- Nhiệm vụ: {ct.goal}\n"
            f"- Trạng thái: {phase_vi}\n"
            f"- Vòng lặp: {live.get('iteration', 0)}/{live.get('max_iterations', 15)}\n"
            f"- Đang làm: {live.get('current_action') or 'chuẩn bị'}\n"
            f"- Săn sóc nhất: {live.get('last_thought', '')[:200]}\n"
            f"- Kết quả gần nhất: {live.get('last_result', '')[:200]}\n"
            f"- Bản tin cuối: {live.get('last_log', '')[:200]}\n"
            f"- Thời gian đang chạy: {elapsed}\n"
            f"- Workspace: {ct.workspace}\n"
            f"- Queue còn: {q.queue_size} task"
        )
    else:
        agent_context = (
            f"Tôi đang rảnh.\n"
            f"- Workspace: {session.workspace}\n"
            f"- Queue: trống"
        )

    # ── 3. Ask ChatGPT to respond naturally ─────────────────────────
    try:
        from llm.client import get_openai_client
        client = get_openai_client()

        messages = [
            {
                "role": "system",
                "content": (
                    "Bạn là CoderX, một AI developer tự hành. "
                    "Bạn đang trao đổi với chủ nhân qua Telegram trong khi làm việc.\n\n"
                    f"Trạng thái hiện tại của bạn:\n{agent_context}\n\n"
                    "Hãy trả lời câu hỏi của chủ nhân một cách TỰ NHIÊN, NGẮN GỌN, bằng tiếng Việt. "
                    "Nếu được hỏi đang làm gì, hãy mô tả cụ thể từ trạng thái trên."
                ),
            },
        ]
        messages.extend(session.chat_history)
        messages.append({"role": "user", "content": text})

        response = await client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=messages,
            temperature=0.6,
            max_tokens=400,
        )
        reply = response.choices[0].message.content
        session.add_message("user", text)
        session.add_message("assistant", reply)
        await send(update, reply)

    except Exception as e:
        # Fallback: simple status
        if q.is_running and ct:
            await send(update, f"🔄 Đang chạy task: _{ct.goal}_")
        else:
            await send(update, "✅ Rảnh. Dùng `/code <task>` để giao việc!")



# ─── Bot setup ─────────────────────────────────────────────────────────────────

def create_bot() -> Application:
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_start))
    app.add_handler(CommandHandler("code",      cmd_code))
    app.add_handler(CommandHandler("onboard",   cmd_onboard))
    app.add_handler(CommandHandler("queue",     cmd_queue))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("stop",      cmd_stop))
    app.add_handler(CommandHandler("workspace", cmd_workspace))
    app.add_handler(CommandHandler("ls",        cmd_ls))
    app.add_handler(CommandHandler("ask",       cmd_ask))
    app.add_handler(CommandHandler("clear",     cmd_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


async def setup_commands(app: Application) -> None:
    # ─── Nạp lại hàng đợi cũ ───────────────────────────────────────────
    from orchestrator.persistence import PersistenceManager
    pm = PersistenceManager()
    users = pm.list_users_with_queues()
    for uid in users:
        get_queue(uid, bot=app.bot)

    await app.bot.set_my_commands([
        BotCommand("code",      "➕ Thêm coding task vào queue"),
        BotCommand("onboard",   "🔍 Tự khám phá architecture của project"),
        BotCommand("queue",     "📋 Xem hàng đợi tasks"),
        BotCommand("ask",       "💡 Hỏi ChatGPT kỹ thuật (có nhớ lịch sử)"),
        BotCommand("clear",     "🧹 Xóa lịch sử chat"),
        BotCommand("workspace", "📁 Xem/đổi workspace"),
        BotCommand("status",    "🔄 Trạng thái agent"),
        BotCommand("ls",        "📂 List files"),
        BotCommand("stop",      "🛑 Dừng & xóa queue"),
        BotCommand("help",      "❓ Trợ giúp"),
    ])
