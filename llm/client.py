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
        
        original_create = _client.chat.completions.create
        
        async def logged_create(*args, **kwargs):
            from orchestrator.logger import log, log_error
            import time
            
            model = kwargs.get("model", "unknown")
            messages = kwargs.get("messages", [])
            
            log(f"--- [LLM OUTBOUND REQUEST | Model: {model}] ---", category="LLM", style="bold cyan")
            for msg in messages:
                role = msg.get("role", "unknown")
                content = str(msg.get("content", ""))
                trunc_content = content[:1000] + ("..." if len(content) > 1000 else "")
                log(f"[{role.upper()}]: {trunc_content}", category="LLM", style="cyan")
                
            start_t = time.time()
            try:
                response = await original_create(*args, **kwargs)
                elapsed = time.time() - start_t
                log(f"--- [LLM INBOUND RESPONSE | {elapsed:.2f}s] ---", category="LLM", style="bold green")
                if response.choices and len(response.choices) > 0:
                    resp_content = response.choices[0].message.content or ""
                    trunc_resp = resp_content[:1500] + ("..." if len(resp_content) > 1500 else "")
                    log(f"[ASSISTANT]:\n{trunc_resp}", category="LLM", style="green")
                return response
            except Exception as e:
                elapsed = time.time() - start_t
                log_error(f"[LLM ERROR | {elapsed:.2f}s]: {e}")
                raise

        _client.chat.completions.create = logged_create

    return _client

async def close_openai_client():
    global _client
    if _client:
        await _client.close()
        _client = None
