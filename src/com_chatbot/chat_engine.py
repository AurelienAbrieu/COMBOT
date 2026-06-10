"""
Unified chat engine for both CLI and web interfaces.
Simplified version for COMBOT - no card injection, raw LLM text output.
"""

import asyncio
import json
import os
import re
import uuid
from threading import Lock
from typing import Optional
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from .agent import create_agent
from .app_logging import get_component_logger
from .request_context import (
    reset_correlation_context,
    set_correlation_context,
)


LLM_TRACE_LOGGER = get_component_logger("llm", "llm_trace.log")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


LLM_LOG_VERBOSE_STREAM_EVENTS = _env_bool("APP_LLM_LOG_VERBOSE_STREAM_EVENTS", default=False)


def extract_assistant_text(response) -> str:
    """Extract plain assistant text from Strands AgentResult."""
    message = getattr(response, "message", None)
    if isinstance(message, dict):
        content = message.get("content", [])
        if isinstance(content, list):
            text_parts = [block.get("text", "") for block in content if isinstance(block, dict)]
            text = "\n".join(part.strip() for part in text_parts if part and part.strip())
            if text:
                return text
    return str(response)


def _usage_to_dict(usage: object) -> dict:
    if not isinstance(usage, dict):
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
    return {
        "input_tokens": int(usage.get("inputTokens", 0) or 0),
        "output_tokens": int(usage.get("outputTokens", 0) or 0),
        "total_tokens": int(usage.get("totalTokens", 0) or 0),
    }


def _extract_token_usage_payload(response: object, is_first_turn: bool) -> dict:
    metrics = getattr(response, "metrics", None)
    if metrics is None:
        metrics = getattr(response, "event_loop_metrics", None)
    if metrics is None:
        return {
            "turn": _usage_to_dict({}),
            "session": _usage_to_dict({}),
        }

    latest_invocation = getattr(metrics, "latest_agent_invocation", None)
    turn_usage = _usage_to_dict(getattr(latest_invocation, "usage", None))
    session_usage = _usage_to_dict(getattr(metrics, "accumulated_usage", None))

    return {
        "turn": turn_usage,
        "session": session_usage,
    }


def _extract_stream_tool_calls(event: object) -> list[dict]:
    tool_calls: list[dict] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            lowered = {str(k).lower(): v for k, v in node.items()}
            for key in ("tooluse", "tool_use"):
                if key in lowered and isinstance(lowered[key], dict):
                    tu = lowered[key]
                    tool_calls.append({
                        "type": "tool_use",
                        "name": tu.get("name") or tu.get("toolname") or tu.get("tool_name"),
                    })
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(event)
    return tool_calls


_TOOL_LABELS: dict[str, str] = {
    "get_locker_status": "Checking locker status...",
    "get_locker_zone_status": "Checking locker zone status...",
    "get_locker_device_snapshot": "Collecting locker technical snapshot...",
    "check_parcel_status": "Looking up parcel...",
    "view_pickup_code": "Retrieving pickup code...",
    "resend_pickup_code": "Resending pickup code...",
    "find_nearby_lockers": "Searching nearby lockers...",
    "add_courier": "Adding courier...",
    "remove_courier": "Removing courier...",
    "generate_report": "Generating report...",
}


def _tool_friendly_label(tool_name: str) -> str:
    return _TOOL_LABELS.get(tool_name, f"Running {tool_name.replace('_', ' ')}...")


class SessionManager:
    """Thread-safe session storage for maintaining conversation history."""

    def __init__(self):
        self._sessions = {}
        self._session_agents = {}
        self._session_last_access_utc = {}
        self._lock = Lock()
        self._max_sessions = int(os.environ.get("CHAT_MAX_SESSIONS", "200"))
        self._session_ttl_seconds = int(os.environ.get("CHAT_SESSION_TTL_SECONDS", "3600"))
        self._max_history_messages = int(os.environ.get("CHAT_MAX_HISTORY_MESSAGES", "100"))

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def _cleanup_expired_sessions(self) -> None:
        if self._session_ttl_seconds <= 0:
            return
        now = self._now_utc()
        expired_ids = [
            sid for sid, last in self._session_last_access_utc.items()
            if (now - last).total_seconds() > self._session_ttl_seconds
        ]
        for sid in expired_ids:
            self._sessions.pop(sid, None)
            self._session_agents.pop(sid, None)
            self._session_last_access_utc.pop(sid, None)

    def _enforce_session_capacity(self) -> None:
        if self._max_sessions <= 0:
            return
        while len(self._sessions) > self._max_sessions:
            oldest = min(
                self._session_last_access_utc.keys(),
                key=lambda sid: self._session_last_access_utc.get(sid, self._now_utc()),
            )
            self._sessions.pop(oldest, None)
            self._session_agents.pop(oldest, None)
            self._session_last_access_utc.pop(oldest, None)

    def get_or_create_session(self, session_id: Optional[str] = None) -> tuple[str, list]:
        if not session_id:
            session_id = str(uuid.uuid4())
        with self._lock:
            self._cleanup_expired_sessions()
            if session_id not in self._sessions:
                self._sessions[session_id] = []
                self._session_agents[session_id] = create_agent()
            self._session_last_access_utc[session_id] = self._now_utc()
            self._enforce_session_capacity()
            return session_id, self._sessions[session_id]

    def get_agent(self, session_id: str):
        with self._lock:
            self._session_last_access_utc[session_id] = self._now_utc()
            return self._session_agents.get(session_id, create_agent())

    def add_message(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].append({"role": role, "content": content})
                if self._max_history_messages > 0:
                    self._sessions[session_id] = self._sessions[session_id][-self._max_history_messages:]
                self._session_last_access_utc[session_id] = self._now_utc()


class ChatEngine:
    """Unified chat interface for both CLI and web modes."""

    def __init__(self):
        self.session_manager = SessionManager()

    def chat(self, user_message: str, session_id: Optional[str] = None) -> dict:
        session_id, history = self.session_manager.get_or_create_session(session_id)
        is_first_turn = len(history) == 0
        turn_id = uuid.uuid4().hex[:12]
        correlation_tokens = set_correlation_context(session_id=session_id, turn_id=turn_id)

        self.session_manager.add_message(session_id, "user", user_message)
        LLM_TRACE_LOGGER.info("llm.request history_size=%s user_message=%s", len(history), user_message)

        try:
            agent = self.session_manager.get_agent(session_id)
            response = agent(user_message)
            token_usage = _extract_token_usage_payload(response, is_first_turn=is_first_turn)
            assistant_text = extract_assistant_text(response)

            LLM_TRACE_LOGGER.info("llm.final assistant_text=%s", assistant_text)
            self.session_manager.add_message(session_id, "assistant", assistant_text)

            return {
                "session_id": session_id,
                "assistant_text": assistant_text,
                "token_usage": token_usage,
                "error": None,
            }
        except Exception as e:
            LLM_TRACE_LOGGER.exception("llm.error error=%s", str(e))
            return {
                "session_id": session_id,
                "assistant_text": "Error while processing the request.",
                "token_usage": _extract_token_usage_payload(response={}, is_first_turn=is_first_turn),
                "error": str(e),
            }
        finally:
            reset_correlation_context(correlation_tokens)

    async def chat_stream_async(self, user_message: str, session_id: Optional[str] = None) -> AsyncIterator[dict]:
        """Stream chat events as they are produced by the model.

        Event types:
        - status: backend/model processing state
        - tool_activity: a tool is being invoked
        - text_delta: incremental assistant text
        - done: stream completed with metadata
        - error: terminal error payload
        """
        session_id, history = self.session_manager.get_or_create_session(session_id)
        is_first_turn = len(history) == 0
        turn_id = uuid.uuid4().hex[:12]
        correlation_tokens = set_correlation_context(session_id=session_id, turn_id=turn_id)
        self.session_manager.add_message(session_id, "user", user_message)
        LLM_TRACE_LOGGER.info("llm.stream_request user_message=%s", user_message)

        yield {
            "type": "status",
            "session_id": session_id,
            "status": "processing",
        }

        try:
            agent = self.session_manager.get_agent(session_id)
            raw_chunks: list[str] = []
            logged_tool_names: set[str] = set()

            async for event in agent.stream_async(user_message):
                if isinstance(event, dict):
                    # Check for tool use events
                    tool_calls = _extract_stream_tool_calls(event)
                    for tc in tool_calls:
                        tool_name = tc.get("name")
                        if tool_name and tool_name not in logged_tool_names:
                            logged_tool_names.add(tool_name)
                            LLM_TRACE_LOGGER.info("llm.tool_called name=%s", tool_name)
                            yield {
                                "type": "tool_activity",
                                "tool_name": tool_name,
                                "label": _tool_friendly_label(tool_name),
                            }

                    # Check for text delta
                    delta = event.get("data", "")
                    if isinstance(delta, str) and delta:
                        raw_chunks.append(delta)
                        yield {
                            "type": "text_delta",
                            "delta": delta,
                        }
                elif isinstance(event, str) and event:
                    raw_chunks.append(event)
                    yield {
                        "type": "text_delta",
                        "delta": event,
                    }

            full_text = "".join(raw_chunks)
            assistant_text = full_text.strip() if full_text else ""

            if not assistant_text:
                # Fallback: get text from agent response
                response = getattr(agent, "last_response", None)
                if response:
                    assistant_text = extract_assistant_text(response)

            LLM_TRACE_LOGGER.info("llm.stream_final assistant_text=%s", assistant_text)
            self.session_manager.add_message(session_id, "assistant", assistant_text)

            token_usage = {}
            response = getattr(agent, "last_response", None)
            if response:
                token_usage = _extract_token_usage_payload(response, is_first_turn=is_first_turn)

            yield {
                "type": "done",
                "session_id": session_id,
                "assistant_text": assistant_text,
                "token_usage": token_usage,
            }

        except Exception as e:
            LLM_TRACE_LOGGER.exception("llm.stream_error error=%s", str(e))
            yield {
                "type": "error",
                "session_id": session_id,
                "error": str(e),
            }

        finally:
            reset_correlation_context(correlation_tokens)


# Singleton
_chat_engine: ChatEngine | None = None
_chat_engine_lock = Lock()


def get_chat_engine() -> ChatEngine:
    global _chat_engine
    with _chat_engine_lock:
        if _chat_engine is None:
            _chat_engine = ChatEngine()
        return _chat_engine
