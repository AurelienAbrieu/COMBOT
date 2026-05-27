"""Centralized application settings backed by `pydantic-settings`."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


_LOCAL_SAFE_APP_ENVS: frozenset[str] = frozenset({"local", "development", "dev", "test"})


class Settings(BaseSettings):
    """Typed view over the subset of env vars the app reads explicitly."""

    model_config = SettingsConfigDict(
        env_file=None,
        case_sensitive=False,
        extra="ignore",
    )

    # --- Runtime mode / session ---
    app_env: str = Field(default="", alias="APP_ENV")
    app_session_secret: str = Field(default="", alias="APP_SESSION_SECRET")

    # --- PMD transport ---
    pmd_api_base_url: str = Field(
        default="https://api-uat.us.parcelpending.com",
        alias="PMD_API_BASE_URL",
    )
    pmd_login: str = Field(default="", alias="PMD_LOGIN")
    pmd_password: str = Field(default="", alias="PMD_PASSWORD")

    # --- Security / abuse controls ---
    auth_login_rate_limit: int = Field(default=10, alias="AUTH_LOGIN_RATE_LIMIT")
    auth_login_rate_window_seconds: int = Field(
        default=300, alias="AUTH_LOGIN_RATE_WINDOW_SECONDS"
    )
    chat_stream_max_seconds: int = Field(
        default=300, alias="CHAT_STREAM_MAX_SECONDS"
    )

    # --- CSRF ---
    csrf_cookie_name: str = Field(default="com_chatbot_csrf", alias="CSRF_COOKIE_NAME")
    csrf_header_name: str = Field(default="X-CSRF-Token", alias="CSRF_HEADER_NAME")

    @property
    def is_local_safe_mode(self) -> bool:
        return (self.app_env or "").strip().lower() in _LOCAL_SAFE_APP_ENVS


def get_settings() -> Settings:
    return Settings()
