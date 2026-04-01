"""
CoderX — Antigravity Web Executor
Thay thế cho AntigravityExecutor (CLI/MCP chat) bằng browser automation.
Tự động khởi động `antigravity serve-web` và điều khiển browser qua Playwright.
"""
from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import time
from pathlib import Path

from orchestrator.logger import log

# ─── Constants ────────────────────────────────────────────────────────────────

ANTIGRAVITY_TUNNEL = (
    "/Applications/Antigravity.app/Contents/Resources/app/bin/antigravity-tunnel"
)
DEFAULT_PORT = 9876
SERVE_WEB_STARTUP_TIMEOUT = 20   # giây đợi server khởi động
RESPONSE_POLL_INTERVAL = 1.5     # giây poll một lần
RESPONSE_IDLE_TIMEOUT = 120      # giây không có thay đổi → coi là xong
RESPONSE_MAX_TIMEOUT = 600       # 10 phút hard limit


class AntigravityExecutor:
    """
    Executor sử dụng antigravity serve-web + Playwright để automation.
    Duy trì server và browser xuyên suốt vòng đời của executor.
    """

    def __init__(self):
        self.port = DEFAULT_PORT
        self.headless = False
        self.base_url = f"http://127.0.0.1:{self.port}"

        self._server_proc: subprocess.Popen | None = None
        self._browser = None
        self._page = None
        self._playwright_ctx = None
        self._current_workspace = None

    async def run(
        self,
        prompt: str,
        workspace: str,
        mode: str = "agent",
        context_files: list[str] = None,
        step_id: int | None = None,
        timeout: int = RESPONSE_MAX_TIMEOUT,
    ) -> tuple[bool, str]:
        """
        Gửi prompt cho Antigravity Agent qua web UI và đợi response.
        """
        try:
            # 1. Đảm bảo server và browser đã sẵn sàng cho đúng workspace
            await self._ensure_ready(workspace)

            # 2. Mở chat panel
            await self._open_chat_panel()

            # 3. Set mode (agent/ask/edit)
            await self._set_chat_mode(mode)

            # 4. Gõ prompt và gửi
            # Nếu có context_files, ta có thể cần logic để attach file (nhưng hiện tại CLI logic đơn giản hơn)
            # Hiện tại web UI Antigravity thường tự động quét workspace.
            # Ta sẽ tiêm done-marker nếu có step_id vào prompt.
            final_prompt = prompt
            if step_id is not None:
                done_marker = (
                    f"\n\n---\n"
                    f"CRITICAL INSTRUCTION: When you have fully completed ALL tasks above, "
                    f"you MUST create the file `.coderx/step_{step_id}_done.json` "
                    f"in the workspace root with this exact content:\n"
                    f'{{"status": "done", "summary": "brief summary of what you accomplished", '
                    f'"files_changed": ["list", "of", "files", "you", "modified"]}}\n'
                    f"This file is how the orchestrator knows you are finished. Do NOT skip this step."
                )
                if f".coderx/step_{step_id}_done.json" not in final_prompt:
                    final_prompt = prompt + done_marker

            await self._send_prompt(final_prompt)

            # 5. Đợi response hoàn chỉnh
            response = await self._wait_for_response(timeout=timeout)

            log(
                f"Response received ({len(response)} chars)",
                category="Executor",
                style="green",
            )
            return True, response

        except Exception as e:
            log(f"Executor error: {e}", category="Executor", style="bold red")
            # Debug: chụp screenshot
            try:
                if self._page:
                    await self._page.screenshot(path="/tmp/antigravity_error.png")
                    log("Screenshot saved to /tmp/antigravity_error.png", category="Executor", style="dim")
            except Exception:
                pass
            return False, str(e)

    async def _ensure_ready(self, workspace: str) -> None:
        """Khởi động server/browser nếu chưa có hoặc sai workspace."""
        # 1. Khởi động server (serve-web) nếu chưa chạy
        await self._start_server()

        # 2. Khởi động browser nếu chưa chạy
        if not self._browser:
            await self._start_browser()

        # 3. Chuyển sang đúng workspace nếu cần
        if self._current_workspace != workspace:
            workspace_encoded = workspace.replace("/", "%2F")
            url = f"{self.base_url}/?folder={workspace_encoded}"
            log(f"Switching workspace to: {workspace}", category="Executor", style="cyan")
            await self._page.goto(url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            await self._handle_startup_dialogs()
            self._current_workspace = workspace

    async def _handle_startup_dialogs(self) -> None:
        """Xử lý các dialog cản trở như 'Trust Workspace'."""
        page = self._page
        try:
            # 1. Trust dialog
            trust_btn = page.locator("button:has-text('Yes, I trust the authors')").first
            if await trust_btn.is_visible(timeout=3000):
                await trust_btn.click()
                log("Clicked 'Trust Workspace'", category="Executor", style="dim")
                await asyncio.sleep(1)

            # 2. Close Welcome tabs if any
            close_welcome = page.locator("[aria-label*='Welcome'], [title*='Welcome'] .action-label.codicon-close").first
            if await close_welcome.is_visible(timeout=1000):
                await close_welcome.click()
                await asyncio.sleep(0.5)

        except Exception as e:
            log(f"Startup dialog check error: {e}", category="Executor", style="dim")

    async def _start_server(self) -> None:
        """Spawn antigravity serve-web nếu chưa chạy."""
        # Check port đã bind chưa
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            already_running = s.connect_ex(("127.0.0.1", self.port)) == 0

        if already_running:
            return

        if not Path(ANTIGRAVITY_TUNNEL).exists():
            raise FileNotFoundError(f"antigravity-tunnel binary not found: {ANTIGRAVITY_TUNNEL}")

        log(f"Starting antigravity serve-web on port {self.port}...", category="Executor", style="cyan")

        self._server_proc = subprocess.Popen(
            ["antigravity", "serve-web", "--port", str(self.port), "--without-connection-token"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        deadline = time.time() + SERVE_WEB_STARTUP_TIMEOUT
        while time.time() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", self.port)) == 0:
                    log(f"serve-web ready at {self.base_url}", category="Executor", style="green")
                    return
            await asyncio.sleep(0.5)

        raise TimeoutError(f"serve-web did not start within {SERVE_WEB_STARTUP_TIMEOUT}s")

    async def _start_browser(self) -> None:
        """Khởi động Playwright browser."""
        from playwright.async_api import async_playwright

        log(f"Launching browser (headless={self.headless})...", category="Executor", style="cyan")
        self._playwright_ctx = async_playwright()
        pw = await self._playwright_ctx.__aenter__()

        self._browser = await pw.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await self._browser.new_context(viewport={"width": 1600, "height": 900})
        self._page = await context.new_page()

    async def _open_chat_panel(self) -> None:
        """Mở Antigravity chat panel."""
        page = self._page
        # 1. Check xem panel đã mở chưa (check sự hiện diện của input hoặc container)
        if await page.locator(".chat-view-container, .aichat-view, [aria-label='Chat input']").first.is_visible(timeout=500):
            return

        log("Opening chat panel...", category="Executor", style="dim")

        # 2. Danh sách các nút có thể mở chat
        chat_buttons = [
            page.locator("a.action-label.codicon-comment"), # Toolbar icon
            page.locator("[aria-label*='Chat']"),
            page.locator("[title*='Chat']"),
            page.locator(".codicon-comment"),
            page.locator("[data-testid='chat']"),
        ]

        for btn in chat_buttons:
            try:
                if await btn.first.is_visible(timeout=1000):
                    await btn.first.click()
                    await asyncio.sleep(1.5)
                    # Xác nhận đã mở
                    if await page.locator("[aria-label='Chat input']").first.is_visible(timeout=500):
                        log("Chat panel opened via click", category="Executor", style="dim")
                        return
            except Exception:
                continue

        # 3. Fallback shortcut
        modifier = "Meta" if os.uname().sysname == "Darwin" else "Control"
        await page.keyboard.press(f"{modifier}+i")
        await asyncio.sleep(2)
        log("Chat panel opened via shortcut", category="Executor", style="dim")

    async def _set_chat_mode(self, mode: str) -> None:
        """Chọn mode: agent / ask / edit."""
        page = self._page
        mode_map = {"ask": "Ask", "edit": "Edit", "agent": "Agent"}
        label = mode_map.get(mode, "Agent")
        try:
            mode_btn = page.locator(f"[aria-label*='{label}'], button:has-text('{label}')").first
            if await mode_btn.is_visible(timeout=1500):
                await mode_btn.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass

    async def _send_prompt(self, prompt: str) -> None:
        """Gõ prompt và gửi."""
        page = self._page
        # Thử lại trust dialog nếu chưa xử lý xong
        await self._handle_startup_dialogs()

        input_selectors = [
            ".aichat-input textarea", ".chat-input textarea", "[aria-label='Chat input']",
            "[placeholder*='Ask']", "[placeholder*='Describe']", "textarea.chat-editor-input",
            ".monaco-editor[aria-label*='chat'] textarea"
        ]
        input_elem = None
        for sel in input_selectors:
            try:
                elem = page.locator(sel).first
                if await elem.is_visible(timeout=2000):
                    input_elem = elem
                    break
            except Exception:
                continue

        if input_elem is None:
            raise RuntimeError("Cannot find chat input.")

        await input_elem.click()
        modifier = "Meta" if os.uname().sysname == "Darwin" else "Control"
        await page.keyboard.press(f"{modifier}+a")
        await page.keyboard.press("Delete")
        await input_elem.fill(prompt)
        await asyncio.sleep(0.3)
        await page.keyboard.press("Enter")

    async def _wait_for_response(self, timeout: int = RESPONSE_MAX_TIMEOUT) -> str:
        """Đợi response hoàn chỉnh."""
        page = self._page
        deadline = time.time() + timeout
        last_response = ""
        last_change_time = time.time()

        response_selectors = [".aichat-response", ".chat-response .rendered-markdown", ".chat-message-content"]
        running_selectors = ["[aria-label='Stop']", "button:has-text('Stop')", ".codicon-stop-circle"]

        while time.time() < deadline:
            await asyncio.sleep(RESPONSE_POLL_INTERVAL)
            is_running = False
            for sel in running_selectors:
                try:
                    if await page.locator(sel).first.is_visible(timeout=500):
                        is_running = True
                        break
                except Exception:
                    pass

            current_response = ""
            for sel in response_selectors:
                try:
                    texts = await page.locator(sel).all_text_contents()
                    if texts:
                        current_response = "\n".join(texts).strip()
                        break
                except Exception:
                    pass

            if current_response != last_response:
                last_response = current_response
                last_change_time = time.time()

            if not is_running and current_response:
                await asyncio.sleep(1.0)
                return last_response

            if time.time() - last_change_time > RESPONSE_IDLE_TIMEOUT and current_response:
                return current_response

        return last_response or "Timeout"

    async def stop(self) -> None:
        """Cleanup."""
        if self._browser:
            await self._browser.close()
        if self._playwright_ctx:
            await self._playwright_ctx.__aexit__(None, None, None)
        if self._server_proc and self._server_proc.poll() is None:
            self._server_proc.terminate()
