"""
CoderX — OpenAI Shared Client
Dùng duy nhất 1 instance Client để tránh lỗi 'aclose' và tối ưu connection pool.
"""
from openai import AsyncOpenAI
from config import config

_client = None

def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL,
        )
    return _client

async def close_openai_client():
    global _client
    if _client:
        await _client.close()
        _client = None
