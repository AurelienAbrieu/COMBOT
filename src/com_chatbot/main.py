"""
COMBOT - Console Mode
Uses the same unified chat engine as web_app for ISO functionality.
"""

import asyncio
import getpass
import os

from .chat_engine import get_chat_engine
from .agent import get_loaded_model_info
from .pmd_client import PMDClientError, client


async def _stream_console_reply(chat_engine, user_input: str, session_id: str | None) -> tuple[str, dict | None]:
    final_payload = None
    has_printed_chunk = False
    processing_banner_shown = False

    print("\nAssistant: ", end="", flush=True)

    async for event in chat_engine.chat_stream_async(user_input, session_id=session_id):
        event_type = event.get("type")

        if event_type == "status" and not processing_banner_shown:
            print("...", end="", flush=True)
            processing_banner_shown = True
            continue

        if event_type == "text_delta":
            delta = event.get("delta", "")
            if not isinstance(delta, str) or not delta:
                continue
            if processing_banner_shown and not has_printed_chunk:
                print("\rAssistant: ", end="", flush=True)
            print(delta, end="", flush=True)
            has_printed_chunk = True
            continue

        if event_type == "done":
            final_payload = event
            continue

        if event_type == "error":
            error = event.get("error") or "Unknown streaming error"
            print(f"\nError: {error}")
            return event.get("session_id") or session_id, None

    if not has_printed_chunk and isinstance(final_payload, dict):
        fallback_text = final_payload.get("assistant_text") or ""
        if fallback_text:
            if processing_banner_shown:
                print("\rAssistant: ", end="", flush=True)
            print(fallback_text, end="", flush=True)

    print()
    if isinstance(final_payload, dict):
        return final_payload.get("session_id") or session_id, final_payload

    return session_id, None


def main():
    """Interactive console mode for the Carrier Operation Manager assistant."""
    if not client.is_authenticated:
        env_login = os.environ.get("PMD_LOGIN", "").strip()
        env_password = os.environ.get("PMD_PASSWORD", "")

        if env_login and env_password:
            try:
                client.login_with_credentials(env_login, env_password)
                print("PMD authentication loaded from environment.")
            except PMDClientError as exc:
                print(f"PMD environment authentication failed: HTTP {exc.status_code}")

        if not client.is_authenticated:
            print("PMD login required for console mode.")
            login = input("PMD login: ").strip()
            password = getpass.getpass("PMD password: ")
            try:
                client.login_with_credentials(login, password)
            except PMDClientError as exc:
                print(f"Unable to authenticate with PMD: HTTP {exc.status_code}")
                return

    chat_engine = get_chat_engine()

    print(get_loaded_model_info())
    print("Carrier Operation Manager Assistant ready. Type 'quit' to exit.")

    session_id = None

    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        if not user_input:
            continue

        session_id, _payload = asyncio.run(
            _stream_console_reply(chat_engine, user_input, session_id)
        )
