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


def get_queue(user_id: int) -> TaskQueue:
    if user_id not in task_queues:
        task_queues[user_id] = TaskQueue(max_size=config.MAX_QUEUE_SIZE)
    return task_queues[user_id]


# ─── Session state ─────────────────────────────────────────────────────────────

class UserSession:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.workspace: str = config.DEFAULT_WORKSPACE


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
        "  `/ask <question>` — Hỏi ChatGPT\n"
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

    success, task_id, msg = q.append(task_goal, session.workspace, notify)

    if not success:
        await send(update, f"⚠️ {msg}")
        return

    q.start_worker()  # No-op nếu đã running

    status = "🟡 *Đã xếp hàng*" if q.is_running else "🟢 *Bắt đầu ngay*"
    await send(update, f"{status}\n📌 Task #{task_id}: _{task_goal}_\n\n{msg}")


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
    task_queues[uid] = TaskQueue(max_size=config.MAX_QUEUE_SIZE)
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

    from openai import AsyncOpenAI
    question = " ".join(ctx.args)
    await send(update, "🤔 *Đang hỏi ChatGPT...*")

    client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Bạn là Senior Developer. Trả lời ngắn gọn, chính xác, dùng tiếng Việt.",
            },
            {"role": "user", "content": question},
        ],
        temperature=0.5,
    )
    await send(update, f"💡 {response.choices[0].message.content}")


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

    # Check if this is a git confirm reply
    if uid in git_confirm_pending:
        await handle_git_confirm(update, ctx)
        return

    await send(update, "🤖 Dùng `/code <task>` để thêm việc vào queue!\n`/help` để xem commands.")


# ─── Bot setup ─────────────────────────────────────────────────────────────────

def create_bot() -> Application:
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_start))
    app.add_handler(CommandHandler("code",      cmd_code))
    app.add_handler(CommandHandler("queue",     cmd_queue))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("stop",      cmd_stop))
    app.add_handler(CommandHandler("workspace", cmd_workspace))
    app.add_handler(CommandHandler("ls",        cmd_ls))
    app.add_handler(CommandHandler("ask",       cmd_ask))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


async def setup_commands(app: Application) -> None:
    await app.bot.set_my_commands([
        BotCommand("code",      "➕ Thêm coding task vào queue"),
        BotCommand("queue",     "📋 Xem hàng đợi tasks"),
        BotCommand("ask",       "💡 Hỏi ChatGPT kỹ thuật"),
        BotCommand("workspace", "📁 Xem/đổi workspace"),
        BotCommand("status",    "🔄 Trạng thái agent"),
        BotCommand("ls",        "📂 List files"),
        BotCommand("stop",      "🛑 Dừng & xóa queue"),
        BotCommand("help",      "❓ Trợ giúp"),
    ])
