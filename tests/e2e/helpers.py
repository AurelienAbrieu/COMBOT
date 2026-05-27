"""Shared helper utilities for COMBOT E2E Playwright tests.

Provides:
- send_and_wait(): send a chat message and wait for the full response
- assert_timing(): assert wall-time thresholds
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


LLM_RESPONSE_TIMEOUT_MS = 120_000
DEFAULT_WALL_MAX_MS = 30_000


@dataclass
class ChatResponse:
    assistant_text: str = ""
    wall_time_ms: float = 0


def send_and_wait(page: Page, message: str, timeout_ms: int = LLM_RESPONSE_TIMEOUT_MS) -> ChatResponse:
    """Send a chat message and wait for the assistant response."""
    msg_input = page.locator("#msg-input")
    msg_input.wait_for(state="visible", timeout=10000)
    msg_input.fill(message)

    start = time.monotonic()
    page.locator("#send-btn").click()

    # Wait for an assistant message to appear
    page.wait_for_selector(".msg.assistant", timeout=timeout_ms)

    # Wait for streaming to complete (no more typing indicator)
    try:
        page.wait_for_selector("#typing", state="detached", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        pass

    # Small settle delay
    page.wait_for_timeout(500)

    wall_time_ms = (time.monotonic() - start) * 1000

    # Get the last assistant message text
    messages = page.locator(".msg.assistant")
    count = messages.count()
    assistant_text = messages.nth(count - 1).text_content() if count > 0 else ""

    return ChatResponse(
        assistant_text=assistant_text or "",
        wall_time_ms=wall_time_ms,
    )


def assert_timing(response: ChatResponse, wall_max_ms: float = DEFAULT_WALL_MAX_MS) -> None:
    assert response.wall_time_ms <= wall_max_ms, (
        f"Wall time {response.wall_time_ms:.0f}ms exceeds {wall_max_ms:.0f}ms"
    )
