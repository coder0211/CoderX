"""
CoderX Configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip("'\" ")
    ALLOWED_USER_IDS: list[int] = [
        int(uid.strip())
        for uid in os.getenv("ALLOWED_USER_IDS", "").split(",")
        if uid.strip().isdigit()
    ]

    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip("'\" ")
    # SMART_MODEL: dùng cho reasoning nặng — TaskPlanner, AgentBrain
    SMART_MODEL: str = os.getenv("SMART_MODEL", "gpt-5-mini").strip("'\" ")
    # FAST_MODEL: dùng cho tác vụ đơn giản — summarize, final report, telegram chat
    FAST_MODEL: str = os.getenv("FAST_MODEL", "gpt-5-nano").strip("'\" ")
    OPENAI_BASE_URL: str | None = os.getenv("OPENAI_BASE_URL", None)


    # Workspace
    DEFAULT_WORKSPACE: str = os.path.abspath(os.path.expanduser(
        os.getenv("DEFAULT_WORKSPACE", "~/Documents")
    ))


    # Autonomous Agent
    MAX_ITERATIONS: int = int(os.getenv("MAX_ITERATIONS", "999"))

    # Task Queue
    MAX_QUEUE_SIZE: int = int(os.getenv("MAX_QUEUE_SIZE", "10"))

    # Git confirm timeout (giây) — quá thời gian này → skip git step
    GIT_CONFIRM_TIMEOUT: int = int(os.getenv("GIT_CONFIRM_TIMEOUT", "300"))  # 5 phút

    # CoderX internal dir (inside workspace)
    CODERX_DIR: str = ".coderx"

    # ── MCP Client ────────────────────────────────────────────────────────────
    # Master switch: nếu False, MCPToolsBridge sẽ không kết nối dù có cấu hình
    MCP_ENABLED: bool = os.getenv("MCP_ENABLED", "true").lower() in ("1", "true", "yes")
    # Timeout (giây) khi gọi tool từ MCP server
    MCP_TOOL_TIMEOUT: int = int(os.getenv("MCP_TOOL_TIMEOUT", "30"))

    # Timeout (giây) cho các cuộc gọi LLM chung (chat, summary, report)
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))
    # Timeout (giây) cho việc phân loại ý định (cần nhanh)
    INTENT_TIMEOUT: int = int(os.getenv("INTENT_TIMEOUT", "20"))


    @classmethod
    def validate(cls) -> None:
        errors = []
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN is required")
        if not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY is required")
        if not cls.SMART_MODEL:
            errors.append("SMART_MODEL is required")
        if not cls.FAST_MODEL:
            errors.append("FAST_MODEL is required")
        if errors:
            raise EnvironmentError("Config errors:\n" + "\n".join(f"  - {e}" for e in errors))


config = Config()
