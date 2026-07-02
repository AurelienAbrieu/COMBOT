"""E2E coverage for pickup-code tools exposed in agent.py."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from .helpers import assert_timing, send_and_wait


DEFAULT_E2E_PARCEL_NUMBER = "1646015534"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _latest_pinres_post_after(log_path: Path, started_at: datetime) -> str:
    if not log_path.exists():
        return ""

    marker = "REQ  POST /api/parcel_commands/add_event/PINRES"
    latest = ""

    with log_path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if marker not in line:
                continue

            # Log timestamp format: 2026-07-02 12:52:36 | ...
            ts_text = line[:19]
            try:
                ts = datetime.strptime(ts_text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except ValueError:
                continue

            if ts >= started_at:
                latest = line.strip()

    return latest


def _extract_pinres_body_from_log_line(line: str) -> str:
    marker = " body="
    idx = line.find(marker)
    if idx < 0:
        return ""
    return line[idx + len(marker):].strip()


@pytest.mark.e2e
def test_resend_pickup_code_uses_pinres_endpoint(authenticated_page):
    parcel_number = os.environ.get("E2E_PARCEL_NUMBER", DEFAULT_E2E_PARCEL_NUMBER).strip() or DEFAULT_E2E_PARCEL_NUMBER
    log_path = Path(__file__).resolve().parents[2] / "var" / "log" / "com-chatbot" / "pmd_api.log"

    started_at = _now_utc()

    preparation = send_and_wait(
        authenticated_page,
        f"Please resend the pickup code for parcel {parcel_number}.",
    )
    assert preparation.assistant_text.strip(), "Assistant response is empty before confirmation"

    confirmation = send_and_wait(authenticated_page, "yes")

    assert confirmation.assistant_text.strip(), "Assistant response is empty after confirmation"
    lowered = confirmation.assistant_text.lower()
    assert "resent" in lowered or "resend" in lowered
    assert_timing(confirmation, wall_max_ms=45_000)

    pinres_line = _latest_pinres_post_after(log_path, started_at)
    assert pinres_line, "Expected PMD log to contain POST /api/parcel_commands/add_event/PINRES after resend confirmation."


@pytest.mark.e2e
def test_resend_pickup_code_pinres_body_contains_expected_fields(authenticated_page):
    parcel_number = os.environ.get("E2E_PARCEL_NUMBER", DEFAULT_E2E_PARCEL_NUMBER).strip() or DEFAULT_E2E_PARCEL_NUMBER
    log_path = Path(__file__).resolve().parents[2] / "var" / "log" / "com-chatbot" / "pmd_api.log"

    started_at = _now_utc()

    _ = send_and_wait(
        authenticated_page,
        f"Please resend the pickup code for parcel {parcel_number}.",
    )
    _ = send_and_wait(authenticated_page, "yes")

    pinres_line = _latest_pinres_post_after(log_path, started_at)
    assert pinres_line, "Expected PMD log to contain POST /api/parcel_commands/add_event/PINRES after resend confirmation."

    body = _extract_pinres_body_from_log_line(pinres_line)
    if not body:
        pytest.skip(
            "PMD request body is not logged. Set PMD_LOG_VERBOSE_PAYLOADS=1 on the app server to validate PINRES JSON fields."
        )

    expected_fragments = [
        '"deviceCode": "DEMO00002"',
        '"logisticianCode": "LODEMO"',
        '"logisticianName": "Demo Logistician"',
        f'"parcelNumber": "{parcel_number}"',
        '"boxPath": "DEMO00002/H201708420131/1/1"',
        '"pickupAllowedUntil": "2026-07-07T08:50:50.577Z"',
    ]

    for fragment in expected_fragments:
        assert fragment in body, f"Missing expected PINRES body fragment: {fragment}"
