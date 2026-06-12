"""E2E coverage for locker status tools exposed in agent.py."""

from __future__ import annotations

import os

import pytest

from .helpers import assert_timing, send_and_wait


DEFAULT_DEMO_LOCKER_ID = "DEMO00001"


@pytest.mark.e2e
def test_locker_status_tool_response(authenticated_page):
    device_id = os.environ.get("E2E_DEVICE_ID", DEFAULT_DEMO_LOCKER_ID).strip() or DEFAULT_DEMO_LOCKER_ID

    response = send_and_wait(
        authenticated_page,
        f"What is the locker status for device {device_id}?",
    )

    assert response.assistant_text.strip(), "Assistant response is empty"
    lowered = response.assistant_text.lower()
    assert "locker" in lowered
    assert "activation" in lowered or "status" in lowered
    assert_timing(response, wall_max_ms=45_000)


@pytest.mark.e2e
def test_locker_snapshot_tool_response(authenticated_page):
    device_id = os.environ.get("E2E_DEVICE_ID", DEFAULT_DEMO_LOCKER_ID).strip() or DEFAULT_DEMO_LOCKER_ID

    response = send_and_wait(
        authenticated_page,
        f"Give me a technical device snapshot for locker {device_id}.",
    )

    assert response.assistant_text.strip(), "Assistant response is empty"
    lowered = response.assistant_text.lower()
    assert "snapshot" in lowered or "rootzone" in lowered or "generation" in lowered
    assert_timing(response, wall_max_ms=45_000)


@pytest.mark.e2e
def test_nearby_lockers_tool_response(authenticated_page):
    lat = os.environ.get("E2E_LOCKER_LAT", "").strip()
    lon = os.environ.get("E2E_LOCKER_LON", "").strip()
    if not lat or not lon:
        pytest.skip("Set E2E_LOCKER_LAT and E2E_LOCKER_LON to run nearby lockers E2E test against INT data.")

    response = send_and_wait(
        authenticated_page,
        f"Find nearby lockers around latitude {lat} and longitude {lon} within 5 km.",
    )

    assert response.assistant_text.strip(), "Assistant response is empty"
    lowered = response.assistant_text.lower()
    assert "locker" in lowered
    assert "km" in lowered or "within" in lowered
    assert_timing(response, wall_max_ms=45_000)


@pytest.mark.e2e
def test_accessible_devices_tool_response(authenticated_page):
    response = send_and_wait(
        authenticated_page,
        "List all accessible devices I can access.",
    )

    assert response.assistant_text.strip(), "Assistant response is empty"
    lowered = response.assistant_text.lower()
    assert "accessible" in lowered or "device" in lowered or "locker" in lowered
    assert_timing(response, wall_max_ms=45_000)


@pytest.mark.e2e
def test_accessible_devices_by_status_tool_response(authenticated_page):
    response = send_and_wait(
        authenticated_page,
        "List all accessible devices in status ACTIVE or MAINTENANCE.",
    )

    assert response.assistant_text.strip(), "Assistant response is empty"
    lowered = response.assistant_text.lower()
    assert "active" in lowered or "maintenance" in lowered or "device" in lowered
    assert_timing(response, wall_max_ms=45_000)
