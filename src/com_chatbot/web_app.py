"""
COMBOT - Web API
Simplified FastAPI interface for Carrier Operation Manager chatbot.
No card rendering - raw LLM text output only.
"""

import json
import os
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import contextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse, Response
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware


_SESSION_COOKIE_NAME = "com_chatbot_session"
_SESSION_MAX_AGE_SECONDS = 14 * 24 * 60 * 60
_CHAT_MESSAGE_MAX_LENGTH = 4000


load_dotenv()

from .settings import get_settings  # noqa: E402

_settings = get_settings()


def _is_local_safe_mode() -> bool:
    return _settings.is_local_safe_mode


def _resolve_session_secret() -> str:
    session_secret = (_settings.app_session_secret or "").strip()
    if session_secret:
        return session_secret
    if _is_local_safe_mode():
        return secrets.token_urlsafe(32)
    raise RuntimeError(
        "APP_SESSION_SECRET is required when APP_ENV is not one of "
        "local, development, dev, or test. "
        f"Current APP_ENV={_settings.app_env!r}."
    )


_SESSION_MIDDLEWARE_OPTIONS = {
    "secret_key": _resolve_session_secret(),
    "session_cookie": _SESSION_COOKIE_NAME,
    "max_age": _SESSION_MAX_AGE_SECONDS,
    "same_site": "lax",
    "https_only": not _is_local_safe_mode(),
}

from .chat_engine import get_chat_engine
from .pmd_client import PMDClientError, client
from .agent import get_loaded_model_info, get_loaded_model_metadata
from .request_context import reset_pmd_session_context, set_pmd_session_context


# --- CSRF double-submit cookie middleware ---

_CSRF_COOKIE_NAME = _settings.csrf_cookie_name
_CSRF_HEADER_NAME = _settings.csrf_header_name
_CSRF_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_CSRF_EXEMPT_PATHS: frozenset[str] = frozenset()


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cookie_token = request.cookies.get(_CSRF_COOKIE_NAME) or ""
        method = request.method.upper()
        path = request.url.path or ""

        if (
            method not in _CSRF_SAFE_METHODS
            and path.startswith("/api/")
            and path not in _CSRF_EXEMPT_PATHS
        ):
            header_token = request.headers.get(_CSRF_HEADER_NAME) or ""
            if not cookie_token or not header_token or not secrets.compare_digest(
                cookie_token, header_token
            ):
                return Response(
                    content='{"detail":"CSRF validation failed"}',
                    status_code=403,
                    media_type="application/json",
                )

        response = await call_next(request)

        if not cookie_token:
            new_token = secrets.token_urlsafe(32)
            response.set_cookie(
                key=_CSRF_COOKIE_NAME,
                value=new_token,
                max_age=_SESSION_MAX_AGE_SECONDS,
                httponly=False,
                samesite="lax",
                secure=not _is_local_safe_mode(),
                path="/",
            )
        return response


# --- Rate limiter ---

class _FixedWindowRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int):
        self._max_attempts = max(1, int(max_attempts))
        self._window_seconds = max(1, int(window_seconds))
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check_and_record(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window_seconds
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self._max_attempts:
                return False
            bucket.append(now)
            return True


_login_rate_limiter = _FixedWindowRateLimiter(
    max_attempts=_settings.auth_login_rate_limit,
    window_seconds=_settings.auth_login_rate_window_seconds,
)


def _client_ip(request: Request) -> str:
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    _CSP = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", self._CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=()",
        )
        return response


app = FastAPI(title="COMBOT - Carrier Operation Manager Assistant")
app.add_middleware(SessionMiddleware, **_SESSION_MIDDLEWARE_OPTIONS)
app.add_middleware(CSRFMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

_UI_DIR = os.path.join(os.path.dirname(__file__), "ui")
_UI_ASSETS_DIR = os.path.join(_UI_DIR, "assets")
if os.path.isdir(_UI_ASSETS_DIR):
    app.mount("/ui/assets", StaticFiles(directory=_UI_ASSETS_DIR), name="ui-assets")


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=_CHAT_MESSAGE_MAX_LENGTH)
    session_id: str | None = None


class ChatMessageResponse(BaseModel):
    session_id: str
    assistant_text: str
    token_usage: dict = Field(default_factory=dict)
    error: str | None = None


class AuthRequest(BaseModel):
    login: str = Field(min_length=1)
    password: str = Field(min_length=1)


_WEB_SESSION_KEY_FIELD = "web_session_key"


def _ensure_web_session_key(request: Request) -> str:
    web_session_key = str(request.session.get(_WEB_SESSION_KEY_FIELD) or "").strip()
    if not web_session_key:
        web_session_key = uuid.uuid4().hex
        request.session[_WEB_SESSION_KEY_FIELD] = web_session_key
    return web_session_key


@contextmanager
def _bind_request_pmd_context(request: Request):
    web_session_key = _ensure_web_session_key(request)
    organization_id = str(request.session.get("organization_id") or "").strip()
    pmd_context_tokens = set_pmd_session_context(
        web_session_key=web_session_key,
        organization_id=organization_id,
    )
    try:
        yield web_session_key
    finally:
        reset_pmd_session_context(pmd_context_tokens)


def _require_pmd_auth():
    if not client.is_authenticated:
        raise HTTPException(status_code=401, detail="User is not connected to PMD")


@app.get("/", response_class=FileResponse)
def index():
    ui_path = os.path.join(_UI_DIR, "carrier_operation_manager_assistant.html")
    return FileResponse(ui_path)


@app.get("/api/chat/health")
def health():
    return {"status": "ok"}


@app.get("/api/model-info")
def model_info():
    metadata = get_loaded_model_metadata()
    return {
        "model": get_loaded_model_info(),
        "configured_model": metadata.get("configured_model"),
        "resolved_model": metadata.get("resolved_model"),
        "max_context_tokens": metadata.get("max_context_tokens"),
        "max_context_source": metadata.get("max_context_source"),
    }


@app.get("/api/ui/auth-defaults")
def ui_auth_defaults(request: Request):
    with _bind_request_pmd_context(request):
        return {
            "is_authenticated": client.is_authenticated,
        }


@app.post("/api/ui/auth/login")
def ui_auth_login(payload: AuthRequest, request: Request):
    if not _login_rate_limiter.check_and_record(_client_ip(request)):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please wait before retrying.",
        )
    with _bind_request_pmd_context(request):
        try:
            client.login_with_credentials(payload.login, payload.password)
        except PMDClientError as exc:
            status = exc.status_code if exc.status_code and exc.status_code > 0 else 401
            raise HTTPException(status_code=status, detail="PMD authentication failed")

        request.session["organization_id"] = client.organization_id
        return {
            "ok": True,
            "organization_id": client.organization_id,
        }


@app.post("/api/ui/auth/logout")
def ui_auth_logout(request: Request):
    with _bind_request_pmd_context(request) as web_session_key:
        client.logout()
    request.session.clear()
    request.session[_WEB_SESSION_KEY_FIELD] = web_session_key
    return {"ok": True}


@app.post("/api/chat/message", response_model=ChatMessageResponse)
def chat_message(payload: ChatMessageRequest, request: Request):
    with _bind_request_pmd_context(request):
        _require_pmd_auth()
        chat_engine = get_chat_engine()
        result = chat_engine.chat(payload.message, session_id=payload.session_id)

    return ChatMessageResponse(
        session_id=result["session_id"],
        assistant_text=result["assistant_text"],
        token_usage=result.get("token_usage") or {},
        error=result["error"],
    )


@app.post("/api/chat/message/stream")
async def chat_message_stream(payload: ChatMessageRequest, request: Request):
    _ensure_web_session_key(request)
    chat_engine = get_chat_engine()
    max_stream_seconds = max(1, int(_settings.chat_stream_max_seconds))

    async def event_generator():
        started_at = time.monotonic()
        with _bind_request_pmd_context(request):
            _require_pmd_auth()
            async for event in chat_engine.chat_stream_async(payload.message, session_id=payload.session_id):
                if time.monotonic() - started_at >= max_stream_seconds:
                    break
                event_type = event.get("type", "message")
                encoded = json.dumps(event, ensure_ascii=False)
                yield f"event: {event_type}\ndata: {encoded}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
