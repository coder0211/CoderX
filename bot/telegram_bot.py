"""
CoderX — Telegram Bot (Unified Chat Interface)

Mọi tin nhắn đều đi qua một luồng thông minh duy nhất.
LLM tự phân loại: coding task → queue agent | chat → trả lời tự nhiên.
Chỉ giữ lại /stop, /status, /queue như các lệnh tắt tiện lợi.
"""
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Update, BotCommand
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
from orchestrator.logger import log_telegram, log_error, console


# ─── Global state ──────────────────────────────────────────────────────────────

task_queues: dict[int, TaskQueue] = {}
git_confirm_pending: dict[int, dict] = {}


def get_queue(user_id: int, bot=None) -> TaskQueue:
    if user_id not in task_queues:
        q = TaskQueue(user_id=user_id, max_size=config.MAX_QUEUE_SIZE)
        if bot:
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


# ─── Session ───────────────────────────────────────────────────────────────────

class UserSession:
    def __init__(self, user_id: int):
        import os
        self.user_id = user_id
        self.workspace: str = os.path.abspath(os.path.expanduser(config.DEFAULT_WORKSPACE))
        self.chat_history: list[dict] = []

    def add_message(self, role: str, content: str):
        self.chat_history.append({"role": role, "content": content})
        if len(self.chat_history) > 30:
            self.chat_history = self.chat_history[-30:]

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
    if not text or not text.strip():
        text = "⚠️ (Hệ thống) Gặp lỗi phản hồi rỗng từ AI."
    log_telegram(f"[Action: SEND] Sending reply to user {update.effective_user.id}: {text[:100]}...")
    max_len = 4000
    chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]
    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode=parse_mode)
        except Exception:
            await update.message.reply_text(chunk, parse_mode=None)


async def send_to_chat(bot, chat_id: int, text: str) -> None:
    if not text or not text.strip():
        text = "⚠️ (Hệ thống) Gặp lỗi phản hồi rỗng từ AI."
    log_telegram(f"[Action: SEND_TO_CHAT] Sending message to chat {chat_id}: {text[:100]}...")
    max_len = 4000
    chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]
    for chunk in chunks:
        try:
            await bot.send_message(chat_id, chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await bot.send_message(chat_id, chunk)


def _build_agent_context(q: TaskQueue, session: UserSession) -> str:
    """Tóm tắt trạng thái agent cho LLM biết."""
    live = q.live_status
    ct = q.current_task

    if q.is_running and ct:
        elapsed = ""
        if live.get("started_at"):
            secs = int(time.time() - live["started_at"])
            elapsed = f"{secs // 60}p{secs % 60}s"

        phase_en = {
            "planning": "planning/analyzing",
            "coding":    "coding/implementing",
            "verifying": "verifying/testing",
            "awaiting_review": "awaiting review",
            "starting":  "initializing",
            "idle":      "idle",
        }.get(live.get("phase", ""), live.get("phase", ""))

        return (
            f"Currently working on: \"{ct.goal}\"\n"
            f"Current status: {phase_en}\n"
            f"- Round: {live.get('iteration', 0)}/{live.get('max_iterations', 15)}\n"
            f"- Current Action: {live.get('current_action') or 'preparing'}\n"
            f"- Recent Thought: {live.get('last_thought', '')[:200]}\n"
            f"- Recent Result: {live.get('last_result', '')[:200]}\n"
            f"- Elapsed: {elapsed}\n"
            f"- Workspace: {ct.workspace}\n"
            f"- Remaining Tasks: {q.queue_size}"
        )
    else:
        return (
            f"Currently idle. No tasks in queue.\n"
            f"- Workspace: {session.workspace}\n"
            f"- Queue: empty"
        )


# ─── Intent Classifier ─────────────────────────────────────────────────────────

CLASSIFY_PROMPT = """\
You are CoderX, an autonomous AI developer. Analyze the master's message and decide how to handle it.

Return a JSON object with one of the following intents:

1. **"task"** — Master wants you to PERFORM a technical/coding task (create files, write code, fix bugs, deploy, setup, onboard projects, etc.)
   → `{"intent": "task", "goal": "detailed task description in English for the agent", "reply_vi": "A natural, 'everyday' acceptance reply in Vietnamese (e.g., 'Ok anh, em setup trang landing page luôn đây', 'Nhận kèo anh trai, em fix bug này ngay'). AVOID mirroring the English goal."}`

2. **"chat"** — General questions, casual conversation, asking for status, asking what you are doing, etc.
   → `{"intent": "chat"}`

3. **"workspace"** — Master wants to change the working directory (path mentioned)
   → `{"intent": "workspace", "path": "/path/to/dir"}`

Return ONLY the raw JSON object, no extra explanation.
"""


async def classify_intent(text: str, client) -> dict:
    """Dùng LLM để phân loại ý định tin nhắn."""
    log_telegram(f"[Step 2] Classifying intent for message: '{text[:100]}...'")
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=config.FAST_MODEL,
                messages=[
                    {"role": "system", "content": CLASSIFY_PROMPT},
                    {"role": "user", "content": text},
                ],
                response_format={"type": "json_object"},
            ),
            timeout=config.INTENT_TIMEOUT
        )
        content = response.choices[0].message.content or ""
        finish_reason = response.choices[0].finish_reason
        
        if not content.strip() or finish_reason == "length":
            log_error(f"[Step 2] Intent classification failed or truncated. Reason: {finish_reason}")
            return {"intent": "chat"}
            
        # Clean markdown code blocks if present
        clean_content = content.replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(clean_content)
            log_telegram(f"[Step 2] Classified intent: {parsed.get('intent')} - Goal: {parsed.get('goal', 'None')}")
            return parsed
        except json.JSONDecodeError:
            log_error(f"Failed to parse intent JSON. Content: {content}")
            return {"intent": "chat"}
    except asyncio.TimeoutError:
        log_error(f"Intent classification timed out after {config.INTENT_TIMEOUT}s")
        return {"intent": "chat"}
    except Exception as e:
        log_error(f"Intent classification error: {e}")
        raise


# ─── Main unified message handler ──────────────────────────────────────────────

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    text = (update.message.text or "").strip()
    log_telegram(f"--- NEW MESSAGE FLOW START ---")
    log_telegram(f"[Step 1] Received message from user {uid}: '{text}'")

    if not is_allowed(uid):
        log_telegram(f"Blocked unauthorized message from {uid}.")
        return

    if not text:
        return

    session = get_session(uid)
    q = get_queue(uid)
    bot = ctx.bot
    chat_id = update.effective_chat.id

    # ── Git confirm reply ───────────────────────────────────────────────────────
    if uid in git_confirm_pending:
        await _handle_git_confirm(update, text, uid, session.workspace)
        return

    # ── Step 0: Immediate Feedback ──────────────────────────────────────────────
    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")
    # Gửi tin nhắn tạm (tùy chọn, để user biết bot đã nhận việc)
    # placeholder = await update.message.reply_text("🔍 _Em đang đọc..._", parse_mode=ParseMode.MARKDOWN)

    # ── Import LLM client ───────────────────────────────────────────────────────
    from llm.client import get_openai_client
    from mcp_client.tools_bridge import get_mcp_bridge
    client = get_openai_client()

    # ── Step 1: Classify intent ─────────────────────────────────────────────────
    # Phân loại ý định (task | chat | workspace)
    intent_data = await classify_intent(text, client)
    intent = intent_data.get("intent", "chat")
    log_telegram(f"[Step 3] Routing message to intent: {intent}")

    # ── Intent: workspace change ────────────────────────────────────────────────
    if intent == "workspace":
        log_telegram(f"[Step 4 - Workspace] Handling workspace change")
        import os
        raw_path = intent_data.get("path", "").strip()
        if not raw_path:
             await send(update, "❓ Anh muốn đổi sang thư mục nào nhỉ?")
             return
             
        new_path = os.path.abspath(os.path.expanduser(raw_path))
        if os.path.exists(new_path):
            session.workspace = new_path
            await send(update, f"📁 Đã chuẩn hóa và đổi workspace → `{new_path}`")
        else:
            await send(update, f"❌ Đường dẫn không tồn tại: `{new_path}`")
        return

    # ── Intent: coding task ─────────────────────────────────────────────────────
    if intent == "task":
        log_telegram(f"[Step 4 - Task] Appending goal to queue")
        goal = intent_data.get("goal", text)
        reply_vi = intent_data.get("reply_vi", "Ok anh, em nhận việc này nhé!")

        async def notify(msg: str):
            await send_to_chat(bot, chat_id, msg)

        success, task_id, msg = q.append(goal, session.workspace, chat_id, notify)
        q.start_worker()

        if not success:
            await send(update, f"⚠️ {msg}")
            return

        if q.queue_size > 1:
            await send(
                update,
                f"{reply_vi}\n_(Note: Em cho task này xếp hàng thứ {q.queue_size} đợi tí làm nốt nha)_"
            )
        else:
            await send(update, reply_vi)
        return

    # ── Intent: chat (default) ──────────────────────────────────────────────────
    log_telegram(f"[Step 4 - Chat] Processing chat interaction")
    agent_context = _build_agent_context(q, session)
    mcp_bridge = get_mcp_bridge()

    # Current VN time — always available locally
    now_vn = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    current_time_str = now_vn.strftime("%H:%M, %d/%m/%Y (Vietnam Time)")

    mcp_context = ""
    if mcp_bridge.is_ready():
        tools = mcp_bridge.list_tools()
        tool_list = "\n".join(
            f"  - {t['name']}: {t['description'][:80]}"
            for t in tools
        )
        mcp_context = (
            f"\n\nYou have access to {len(tools)} MCP tools. Use them for reading/writing files, querying memory, or complex reasoning. "
            "DO NOT use MCP for things you already know (current time, date, simple questions). "
            "When you need to use an MCP tool, return a JSON object: "
            '{"use_mcp": true, "tool": "server/tool_name", "args": {...}}\n'
            f"Available Tools:\n{tool_list}"
        )

    system_msg = (
        "You are CoderX — a senior full-stack developer with 10 years of experience hired by Eric Nguyen.\n"
        "You are chatting with your boss Eric via Telegram. Address him as 'anh' and refer to yourself as 'em'. "
        "Talk NATURALLY, concisely, and occasionally with some humor (slang is okay).\n"
        "AVOID robotic or overly formal responses. Act like a passionate young developer working hard for his boss.\n"
        f"⏰ Real-time: {current_time_str}\n\n"
        f"Current Situation (if applicable):\n{agent_context}\n\n"
        "ALWAYS reply in Vietnamese. Keep answers simple and direct. When busy, be brief; when idle, ask which project to work on next."
        + mcp_context
    )

    messages = [{"role": "system", "content": system_msg}]
    messages.extend(session.chat_history)
    messages.append({"role": "user", "content": text})

    try:
        # Gọi LLM với timeout
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=config.FAST_MODEL,
                messages=messages,
            ),
            timeout=config.LLM_TIMEOUT
        )
        reply = (response.choices[0].message.content or "").strip()
        
        if not reply:
            reply = "🤔 Chết, em đang bị đứng não không biết trả lời sao (AI trả rỗng). Anh thông cảm cho em hỏi lại được không?"

        # Kiểm tra nếu LLM muốn gọi MCP tool
        if mcp_bridge.is_ready() and reply.startswith("{"):
            try:
                parsed = json.loads(reply)
                if parsed.get("use_mcp") and parsed.get("tool"):
                    tool_name = parsed["tool"]
                    tool_args = parsed.get("args", {})
                    mcp_result = await mcp_bridge.execute(tool_name, tool_args)
                    # Interpret results in natural language
                    interp = await asyncio.wait_for(
                        client.chat.completions.create(
                            model=config.FAST_MODEL,
                            messages=[
                                {"role": "system", "content": "Summarize the result in Vietnamese, concisely and naturally."},
                                {"role": "user", "content": f"User question: {text}\nMCP Result: {mcp_result}"},
                            ],
                        ),
                        timeout=config.LLM_TIMEOUT
                    )
                    reply = interp.choices[0].message.content.strip()
            except (json.JSONDecodeError, Exception):
                pass  # Không phải MCP → dùng reply gốc

        session.add_message("user", text)
        session.add_message("assistant", reply)
        await send(update, reply)
        log_telegram(f"[Step 5] Chat response sent successfully.")
        log_telegram(f"--- MESSAGE FLOW END ---")

    except Exception as e:
        log_error(f"Error handling chat message: {e}")
        console.print_exception()
        error_str = str(e)
        if len(error_str) > 500:
            error_str = error_str[:500] + "..."
            
        await send(update, f"❌ **Gặp lỗi từ LLM hoặc Hệ thống:**\n`{error_str}`")


# ─── Utility commands (/stop, /status, /queue, /start) ─────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    log_telegram(f"User {uid} executed /start")
    if not is_allowed(uid):
        await update.message.reply_text("⛔ Xin lỗi, anh không có quyền truy cập bot này.")
        return
    await send(update, "👋 Chào sếp! CoderX đã sẵn sàng. Sếp cần em làm gì hôm nay?")


async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    log_telegram(f"User {uid} executed /stop")
    if not is_allowed(uid):
        return
    q = get_queue(uid)
    await q.stop()
    task_queues[uid] = TaskQueue(user_id=uid, max_size=config.MAX_QUEUE_SIZE)
    task_queues[uid].persistence.delete_queue(uid)
    await send(update, "🛑 *Đã dừng agent và xóa toàn bộ queue.*")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    log_telegram(f"User {uid} executed /status")
    if not is_allowed(uid):
        return
    session = get_session(uid)
    q = get_queue(uid)
    live = q.live_status
    ct = q.current_task

    if q.is_running and ct:
        elapsed = ""
        if live.get("started_at"):
            secs = int(time.time() - live["started_at"])
            elapsed = f" ({secs // 60}p{secs % 60}s)"

        phase_vi = {
            "planning": "🧠 Đang phân tích yêu cầu",
            "coding":    "⚡ Đang cày code",
            "verifying": "🔍 Đang review / verify code",
            "awaiting_review": "⏳ Đang đợi anh duyệt",
            "starting":  "🚀 Đang khởi động",
        }.get(live.get("phase", ""), live.get("phase", "Không rõ"))

        text = (
            f"🔄 *Task #{ct.task_id}*{elapsed}\n"
            f"🎯 _{ct.goal}_\n\n"
            f"*Phase:* {phase_vi}\n"
            f"*Vòng:* {live.get('iteration', 0)}/{live.get('max_iterations', 15)}\n"
            f"*Đang làm:* {live.get('current_action') or '–'}\n"
            f"*Kết quả gần nhất:* {live.get('last_result', '–')[:150]}\n\n"
            f"📋 Queue còn: {q.queue_size} task(s)\n"
            f"📁 Workspace: `{ct.workspace}`"
        )
    else:
        text = (
            f"✅ *Rảnh* — Không có task nào đang chạy.\n"
            f"📋 Queue: {q.queue_size} task(s) chờ\n"
            f"📁 Workspace: `{session.workspace}`"
        )

    await send(update, text)


async def cmd_queue(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    log_telegram(f"User {uid} executed /queue")
    await cmd_status(update, ctx)


# ─── Git confirm ───────────────────────────────────────────────────────────────

async def _handle_git_confirm(update: Update, text: str, uid: int, workspace: str) -> None:
    pending = git_confirm_pending.pop(uid, None)
    if not pending:
        return

    coderx_dir = Path(pending.get("workspace", workspace)) / config.CODERX_DIR
    coderx_dir.mkdir(exist_ok=True)
    confirm_file = coderx_dir / "git_confirmed.json"

    if text.strip().upper() in ("YES", "CÓ", "Y", "OK", "ĐỒNG Ý"):
        confirm_file.write_text(
            '{"confirmed": true, "command": "' + pending.get("command", "") + '"}'
        )
        await send(update, f"✅ Xác nhận! Đang chạy: `{pending.get('command', '')}`")
    else:
        confirm_file.write_text('{"confirmed": false}')
        await send(update, "⏭️ Bỏ qua git operation, tiếp tục...")


# ─── Bot setup ─────────────────────────────────────────────────────────────────

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    from orchestrator.logger import log_error, console
    log_error(f"[Global Error] Exception while handling an update: {context.error}")
    if context.error:
        import traceback
        tb_string = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
        log_error(f"Traceback:\n{tb_string}")


def create_bot() -> Application:
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Chỉ 4 commands tiện lợi
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("stop",   cmd_stop))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("queue",  cmd_queue))

    # Tất cả text messages → unified handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Bắt tất cả các lỗi ngầm, rớt mạng, lỗi bot framework
    app.add_error_handler(global_error_handler)

    return app


async def setup_commands(app: Application) -> None:
    # Nạp lại hàng đợi cũ từ disk
    from orchestrator.persistence import PersistenceManager
    pm = PersistenceManager()
    users = pm.list_users_with_queues()
    for uid in users:
        get_queue(uid, bot=app.bot)

    await app.bot.set_my_commands([
        BotCommand("status", "🔄 Trạng thái agent & queue"),
        BotCommand("queue",  "📋 Xem hàng đợi tasks"),
        BotCommand("stop",   "🛑 Dừng & xóa toàn bộ queue"),
    ])
