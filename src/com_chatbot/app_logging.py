"""Centralized application logging configuration."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock

from .request_context import get_correlation_fields


_LOGGER_PREFIX = "com_chatbot"
_LOGGER_LOCK = Lock()


class CorrelationContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        session_id, turn_id = get_correlation_fields()
        record.session_id = session_id or "-"
        record.turn_id = turn_id or "-"
        return True


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _running_in_docker() -> bool:
    return os.path.exists("/.dockerenv") or _as_bool(os.environ.get("RUNNING_IN_DOCKER"), False)


def _resolve_log_dir() -> Path:
    default_dir = "/var/log/com-chatbot" if _running_in_docker() else "var/log/com-chatbot"
    configured = os.environ.get("APP_LOG_DIR", default_dir).strip()
    return Path(configured)


def _resolve_log_level() -> int:
    configured = os.environ.get("APP_LOG_LEVEL", "INFO").strip().upper()
    return getattr(logging, configured, logging.INFO)


def _resolve_external_log_level(name: str, default: str) -> int:
    configured = os.environ.get(name, default).strip().upper()
    return getattr(logging, configured, getattr(logging, default, logging.WARNING))


def _configure_external_loggers() -> None:
    logging.getLogger("strands").setLevel(_resolve_external_log_level("APP_STRANDS_LOG_LEVEL", "WARNING"))


def _win_safe_rotate(source: str, dest: str) -> None:
    try:
        os.replace(source, dest)
    except OSError:
        pass


def get_component_logger(component: str, file_name: str | None = None) -> logging.Logger:
    logger_name = f"{_LOGGER_PREFIX}.{component}"

    with _LOGGER_LOCK:
        logger = logging.getLogger(logger_name)
        if getattr(logger, "_com_chatbot_configured", False):
            return logger

        _configure_external_loggers()

        logger.setLevel(_resolve_log_level())
        logger.propagate = False

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(session_id)s | %(turn_id)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        correlation_filter = CorrelationContextFilter()

        if _as_bool(os.environ.get("APP_LOG_TO_STDOUT"), True):
            stream_handler = logging.StreamHandler()
            stream_handler.addFilter(correlation_filter)
            stream_handler.setFormatter(formatter)
            logger.addHandler(stream_handler)

        if _as_bool(os.environ.get("APP_ENABLE_FILE_LOGS"), True) and file_name:
            log_dir = _resolve_log_dir()
            log_dir.mkdir(parents=True, exist_ok=True)

            max_bytes = int(os.environ.get("APP_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
            backup_count = int(os.environ.get("APP_LOG_BACKUP_COUNT", "5"))

            file_handler = RotatingFileHandler(
                log_dir / file_name,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            if sys.platform == "win32":
                file_handler.rotate = _win_safe_rotate
            file_handler.addFilter(correlation_filter)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        logger._com_chatbot_configured = True
        return logger
