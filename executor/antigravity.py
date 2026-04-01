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

    # ─── Selectors ─────────────────────────────────────────────────────────────
    TRUST_SELECTORS = [
        "button:has-text('Yes, I trust the authors')",
        "button[aria-label*='Trust']",
        ".monaco-button:has-text('Trust')"
    ]
    CHAT_CONTAINER_SELECTORS = [
        ".chat-view-container", ".aichat-view", "[aria-label='Chat input']",
        ".composite.sidebar[aria-label*='Chat']"
    ]
    CHAT_BUTTONS_SELECTORS = [
        "a.action-label.codicon-comment",
        "[aria-label*='Antigravity']",
        "[title*='Antigravity']",
        "[aria-label*='Chat']",
        "[title*='Chat']",
        ".codicon-comment",
        "[data-testid='chat']",
    ]
    INPUT_SELECTORS = [
        "textarea.chat-editor-input",
        "[aria-label='Chat input']",
        ".aichat-input textarea",
        ".chat-input textarea",
        "[placeholder*='Ask']",
        "[placeholder*='Describe']",
        ".monaco-editor[aria-label*='chat'] textarea"
    ]
    RUNNING_SELECTORS = [
        "[aria-label='Stop']", "button:has-text('Stop')", ".codicon-stop-circle",
        "[aria-label='Interrupt']", ".chat-stop-button"
    ]
    RESPONSE_SELECTORS = [
        ".aichat-response", ".chat-response .rendered-markdown", 
        ".chat-message-content", ".markdown-content"
    ]

    def __init__(self):
        self.port = DEFAULT_PORT
        self.headless = False
        self.base_url = f"http://127.0.0.1:{self.port}"

        self._server_proc: subprocess.Popen | None = None
        self._browser = None
        self._page = None
        self._playwright_ctx = None
        self._current_workspace = None

    @property
    def modifier_key(self) -> str:
        """Trả về 'Meta' (Cmd) cho macOS và 'Control' cho các OS khác."""
        try:
            return "Meta" if os.uname().sysname == "Darwin" else "Control"
        except Exception:
            return "Control"

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
        """Xử lý các dialog cản trở như 'Trust Workspace' và dọn dẹp các tab Welcome."""
        page = self._page
        try:
            # 1. Trust dialog (nhiều biến thể selector)
            for sel in self.TRUST_SELECTORS:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=1000):
                        await btn.click()
                        log("Clicked 'Trust Workspace'", category="Executor", style="dim")
                        await asyncio.sleep(0.5)
                        break
                except Exception:
                    continue

            # 2. Shortcut để đóng tất cả các tab (Welcome, etc.)
            # Cmd+k w: Close All Editors
            await page.keyboard.press(f"{self.modifier_key}+k")
            await asyncio.sleep(0.1)
            await page.keyboard.press("w")
            log("Closed all tabs/editors via shortcut", category="Executor", style="dim")
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

        # Đặt CWD là thư mục cha chung (Documents) nếu có thể để tránh lỗi Access Denied khi chuyển workspace
        cwd = "/Users/hoa.nguyen3/Documents"
        
        self._server_proc = subprocess.Popen(
            ["antigravity", "serve-web", "--port", str(self.port), "--without-connection-token", "--accept-server-license-terms"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=cwd
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
        """Mở Antigravity chat panel và đảm bảo nó hiển thị."""
        page = self._page
        
        # 1. Check xem panel đã mở chưa
        for sel in self.CHAT_CONTAINER_SELECTORS:
            if await page.locator(sel).first.is_visible(timeout=500):
                return

        log("Opening chat panel...", category="Executor", style="dim")

        # 2. Danh sách các nút có thể mở chat
        for sel in self.CHAT_BUTTONS_SELECTORS:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    await asyncio.sleep(1.5)
                    # Xác nhận đã mở qua input hiện diện
                    for input_sel in self.INPUT_SELECTORS[:2]:
                        if await page.locator(input_sel).first.is_visible(timeout=500):
                            log("Chat panel opened via click", category="Executor", style="dim")
                            return
            except Exception:
                continue

        # 3. Fallback shortcuts
        # Thử Cmd+L (New Chat) hoặc Cmd+I (Inline/Side Chat)
        for key in ["l", "i"]:
            await page.keyboard.press(f"{self.modifier_key}+{key}")
            await asyncio.sleep(1.5)
            for input_sel in self.INPUT_SELECTORS[:2]:
                if await page.locator(input_sel).first.is_visible(timeout=500):
                    log(f"Chat panel opened via shortcut {self.modifier_key}+{key}", category="Executor", style="dim")
                    return

        log("Warning: Could not confirm chat panel is open", category="Executor", style="yellow")

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
        """Gõ prompt và gửi với các bước kiểm tra chắc chắn."""
        page = self._page
        # Đảm bảo các dialog không che khuất
        await self._handle_startup_dialogs()

        input_elem = None
        # Đợi tối đa 10s cho bất kỳ selector nào trong INPUT_SELECTORS xuất hiện
        for sel in self.INPUT_SELECTORS:
            try:
                elem = page.locator(sel).first
                if await elem.is_visible(timeout=2000):
                    input_elem = elem
                    break
            except Exception:
                continue

        if input_elem is None:
            raise RuntimeError(f"Cannot find chat input after waiting. Tried: {', '.join(self.INPUT_SELECTORS[:3])}...")

        log("Focusing and filling prompt...", category="Executor", style="dim")
        await input_elem.click()
        await asyncio.sleep(0.3)
        
        # Xóa nội dung cũ bằng keyboard shortcut cho chắc chắn
        await page.keyboard.press(f"{self.modifier_key}+a")
        await page.keyboard.press("Delete")
        await asyncio.sleep(0.2)
        
        await input_elem.fill(prompt)
        await asyncio.sleep(0.5)
        
        # Nhấn Enter để gửi
        await page.keyboard.press("Enter")
        log("Prompt sent.", category="Executor", style="dim")

    async def _wait_for_response(self, timeout: int = RESPONSE_MAX_TIMEOUT) -> str:
        """Đợi response hoàn chỉnh với cơ chế chống rung (debounce)."""
        page = self._page
        deadline = time.time() + timeout
        last_response = ""
        last_change_time = time.time()
        
        log(f"Waiting for agent response (timeout={timeout}s)...", category="Executor", style="dim")
        
        # Flag để kiểm tra xem đã bắt đầu nhận response chưa
        started_receiving = False

        while time.time() < deadline:
            await asyncio.sleep(RESPONSE_POLL_INTERVAL)
            
            # 1. Kiểm tra trạng thái "đang chạy"
            is_running = False
            for sel in self.RUNNING_SELECTORS:
                try:
                    if await page.locator(sel).first.is_visible(timeout=100):
                        is_running = True
                        break
                except Exception:
                    pass

            # 2. Lấy nội dung hiện tại từ các container khả thi
            current_response = ""
            for sel in self.RESPONSE_SELECTORS:
                try:
                    elements = await page.locator(sel).all()
                    if elements:
                        # Thường ta chỉ quan tâm message cuối cùng hoặc gom tất cả thành một stream
                        texts = [await el.inner_text() for el in elements]
                        current_response = "\n\n---\n\n".join(texts).strip()
                        if current_response:
                            break
                except Exception:
                    continue

            if current_response:
                if not started_receiving:
                    log("Started receiving response...", category="Executor", style="dim")
                    started_receiving = True
                
                if current_response != last_response:
                    last_response = current_response
                    last_change_time = time.time()

            # 3. Điều kiện kết thúc: Không còn chạy và đã có nội dung
            if not is_running and started_receiving:
                # Đợi thêm một nhịp ngắn để chắc chắn animation hoàn tất
                await asyncio.sleep(1.5)
                return last_response

            # 4. Timeout nếu không có thay đổi quá lâu (idle) sau khi đã bắt đầu nhận
            if started_receiving and (time.time() - last_change_time > RESPONSE_IDLE_TIMEOUT):
                log("Response idle timeout reached.", category="Executor", style="yellow")
                return last_response

        log("Hard timeout reached while waiting for response.", category="Executor", style="red")
        return last_response or "Timeout"

    async def stop(self) -> None:
        """Cleanup."""
        if self._browser:
            await self._browser.close()
        if self._playwright_ctx:
            await self._playwright_ctx.__aexit__(None, None, None)
        if self._server_proc and self._server_proc.poll() is None:
            self._server_proc.terminate()
