"""Shared pytest fixtures for COMBOT E2E Playwright tests.

Usage:
    pytest tests/e2e/ --headed
    pytest tests/e2e/ -k locker
    pytest tests/e2e/ --base-url http://...
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import pytest
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))

from playwright.sync_api import sync_playwright


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


DEFAULT_E2E_PORT = 8001
DEFAULT_E2E_BASE_URL = f"http://127.0.0.1:{DEFAULT_E2E_PORT}"


def pytest_addoption(parser):
    parser.addoption("--headed", action="store_true", default=False, help="Launch browser in headed mode")
    parser.addoption("--base-url", default=None, help="Override base URL")
    parser.addoption("--slow-mo", type=int, default=0, help="Slow-mo milliseconds")


@pytest.fixture(scope="session")
def base_url(request):
    return request.config.getoption("--base-url") or os.environ.get("BENCHMARK_BASE_URL", DEFAULT_E2E_BASE_URL)


def _is_port_open(host, port, timeout=0.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_port(host: str, port: int, timeout_seconds: float = 25.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _is_port_open(host, port, timeout=0.25):
            return True
        time.sleep(0.25)
    return False


@pytest.fixture(scope="session")
def e2e_server(base_url, request):
    """Start a dedicated local Uvicorn server for E2E when using default base URL.

    This avoids collisions with a manually running app on port 8000.
    """
    explicit_base_url = bool(request.config.getoption("--base-url") or os.environ.get("BENCHMARK_BASE_URL"))
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # Respect explicit external base URL configuration.
    if explicit_base_url:
        yield base_url
        return

    if _is_port_open(host, port):
        yield base_url
        return

    repo_root = Path(__file__).resolve().parents[2]
    venv_python = repo_root / ".venv" / "Scripts" / "python.exe"
    python_cmd = str(venv_python if venv_python.exists() else Path(sys.executable))

    env = os.environ.copy()
    proc = subprocess.Popen(
        [
            python_cmd,
            "-m",
            "uvicorn",
            "web_app:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=str(repo_root),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if not _wait_for_port(host, port):
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        pytest.fail(f"Unable to start local E2E Uvicorn server on {host}:{port}.")

    try:
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


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
def page(browser, e2e_server):
    ctx = browser.new_context()
    p = ctx.new_page()
    p.goto(e2e_server, wait_until="domcontentloaded", timeout=30000)
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
