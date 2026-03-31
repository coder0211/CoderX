import asyncio
import os
import sys

from executor.antigravity import AntigravityExecutor

async def main():
    executor = AntigravityExecutor()
    success, msg = await executor.run(
        prompt="hello from test!",
        workspace="/Users/hoa.nguyen3/Documents/our/CoderX",
        mode="agent"
    )
    print(f"Success: {success}, Message: {msg}")

if __name__ == "__main__":
    asyncio.run(main())
