"""Shared pytest fixtures for COMBOT E2E Playwright tests.

Usage:
    pytest tests/e2e/ --headed
    pytest tests/e2e/ -k locker
    pytest tests/e2e/ --base-url http://...
"""

import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))

from playwright.sync_api import sync_playwright


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def pytest_addoption(parser):
    parser.addoption("--headed", action="store_true", default=False, help="Launch browser in headed mode")
    parser.addoption("--base-url", default=None, help="Override base URL")
    parser.addoption("--slow-mo", type=int, default=0, help="Slow-mo milliseconds")


@pytest.fixture(scope="session")
def base_url(request):
    return request.config.getoption("--base-url") or os.environ.get("BENCHMARK_BASE_URL", "http://127.0.0.1:8000")


def _is_port_open(host, port, timeout=0.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def browser(request):
    headed = request.config.getoption("--headed")
    slow_mo = request.config.getoption("--slow-mo")
    pw = sync_playwright().start()
    b = pw.chromium.launch(headless=not headed, slow_mo=slow_mo)
    yield b
    b.close()
    pw.stop()


@pytest.fixture
def page(browser, base_url):
    ctx = browser.new_context()
    p = ctx.new_page()
    p.goto(base_url, wait_until="domcontentloaded", timeout=30000)
    p.locator("#header-auth-btn").wait_for(state="visible", timeout=10000)
    yield p
    p.close()
    ctx.close()


@pytest.fixture
def authenticated_page(page):
    """Page with PMD auth already established."""
    login = os.environ.get("PMD_LOGIN", "").strip()
    password = os.environ.get("PMD_PASSWORD", "")

    login_field = page.locator("#header-login")
    password_field = page.locator("#header-password")
    auth_btn = page.locator("#header-auth-btn")
    msg_input = page.locator("#msg-input")

    page.wait_for_function(
        "() => !!document.getElementById('header-auth-btn') && !!document.getElementById('msg-input')",
        timeout=10000,
    )

    if not login_field.is_disabled():
        if not login or not password:
            pytest.fail("PMD_LOGIN and PMD_PASSWORD must be available for E2E authentication.")
        login_field.fill(login)
        password_field.fill(password)
        auth_btn.click()

    page.wait_for_function(
        "() => { const overlay = document.getElementById('lock-overlay'); const input = document.getElementById('msg-input'); return !!overlay && !!input && overlay.style.display === 'none' && !input.disabled; }",
        timeout=15000,
    )
    expect_title = page.locator("#status-dot")
    expect_title.wait_for(state="attached", timeout=5000)
    assert msg_input.is_enabled(), "Message input should be enabled after authentication"

    return page
