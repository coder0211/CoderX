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
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o").strip("'\" ")

    # Antigravity
    ANTIGRAVITY_CLI: str = os.getenv(
        "ANTIGRAVITY_CLI",
        "/Applications/Antigravity.app/Contents/Resources/app/bin/antigravity",
    )

    # Workspace
    DEFAULT_WORKSPACE: str = os.getenv(
        "DEFAULT_WORKSPACE",
        os.path.expanduser("~/Documents"),
    )

    # Timeouts — Antigravity agent
    # Không set timeout nhỏ: đợi Antigravity làm xong
    # Nếu sau 15 phút chưa có done-marker → cancel + continue (không stuck)
    STEP_TIMEOUT: int = int(os.getenv("STEP_TIMEOUT", "900"))       # 15 phút hard cancel
    STEP_IDLE_TIMEOUT: int = int(os.getenv("STEP_IDLE_TIMEOUT", "60"))  # 60s không có file change

    # Autonomous Agent
    MAX_ITERATIONS: int = int(os.getenv("MAX_ITERATIONS", "15"))

    # Task Queue
    MAX_QUEUE_SIZE: int = int(os.getenv("MAX_QUEUE_SIZE", "10"))

    # Git confirm timeout (giây) — quá thời gian này → skip git step
    GIT_CONFIRM_TIMEOUT: int = int(os.getenv("GIT_CONFIRM_TIMEOUT", "300"))  # 5 phút

    # CoderX internal dir (inside workspace)
    CODERX_DIR: str = ".coderx"


    @classmethod
    def validate(cls) -> None:
        errors = []
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN is required")
        if not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY is required")
        if not os.path.exists(cls.ANTIGRAVITY_CLI):
            errors.append(f"Antigravity CLI not found at: {cls.ANTIGRAVITY_CLI}")
        if errors:
            raise EnvironmentError("Config errors:\n" + "\n".join(f"  - {e}" for e in errors))


config = Config()
