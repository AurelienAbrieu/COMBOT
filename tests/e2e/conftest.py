"""Shared pytest fixtures for COMBOT E2E Playwright tests.

Usage:
    pytest tests/e2e/ --headed
    pytest tests/e2e/ -k locker
    pytest tests/e2e/ --base-url http://...
"""

import os
import socket
import sys
from urllib.parse import urlparse

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from playwright.sync_api import sync_playwright


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
    p.goto(base_url)
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

    if login_field.is_disabled():
        auth_btn.click()
        page.wait_for_function("() => document.getElementById('lock-overlay').style.display === 'none'", timeout=10000)
    else:
        if login and password:
            login_field.fill(login)
            password_field.fill(password)
        auth_btn.click()
        page.wait_for_function("() => document.getElementById('lock-overlay').style.display === 'none'", timeout=10000)

    return page
