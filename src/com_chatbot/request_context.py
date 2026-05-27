"""Request correlation context shared across LLM and PMD logging."""

from __future__ import annotations

from contextvars import ContextVar, Token


_SESSION_ID: ContextVar[str] = ContextVar("com_chatbot_session_id", default="")
_TURN_ID: ContextVar[str] = ContextVar("com_chatbot_turn_id", default="")
_WEB_SESSION_KEY: ContextVar[str] = ContextVar("com_chatbot_web_session_key", default="")
_ORGANIZATION_ID: ContextVar[str] = ContextVar("com_chatbot_organization_id", default="")


def set_correlation_context(session_id: str, turn_id: str) -> tuple[Token, Token]:
    session_token = _SESSION_ID.set((session_id or "").strip())
    turn_token = _TURN_ID.set((turn_id or "").strip())
    return session_token, turn_token


def reset_correlation_context(tokens: tuple[Token, Token]) -> None:
    session_token, turn_token = tokens
    _SESSION_ID.reset(session_token)
    _TURN_ID.reset(turn_token)


def get_correlation_fields() -> tuple[str, str]:
    return _SESSION_ID.get(), _TURN_ID.get()


def get_current_turn_id() -> str:
    return _TURN_ID.get()


def get_correlation_log_suffix() -> str:
    session_id, turn_id = get_correlation_fields()
    if not session_id and not turn_id:
        return ""
    return f" session_id={session_id or '-'} turn_id={turn_id or '-'}"


def set_pmd_session_context(
    web_session_key: str = "",
    organization_id: str = "",
) -> tuple[Token, Token]:
    web_session_token = _WEB_SESSION_KEY.set((web_session_key or "").strip())
    organization_token = _ORGANIZATION_ID.set((organization_id or "").strip())
    return web_session_token, organization_token


def reset_pmd_session_context(tokens: tuple[Token, Token]) -> None:
    web_session_token, organization_token = tokens
    _WEB_SESSION_KEY.reset(web_session_token)
    _ORGANIZATION_ID.reset(organization_token)


def get_pmd_session_fields() -> tuple[str, str]:
    return _WEB_SESSION_KEY.get(), _ORGANIZATION_ID.get()


def get_web_session_key() -> str:
    return _WEB_SESSION_KEY.get()
