"""Marketing showcase E2E scenarios with screenshot evidence.

These tests focus on end-to-end user journeys and capture screenshots as
proof artifacts for non-technical stakeholders.
"""

from __future__ import annotations

import os

import pytest

from .helpers import assert_timing, capture_screenshot, send_and_wait


DEFAULT_E2E_DEVICE_ID = "DEMO00002"
DEFAULT_E2E_PARCEL_NUMBER = "1646015534"
DEFAULT_LOGISTICIAN_NAME = "Demo Logistician"


@pytest.mark.e2e
@pytest.mark.marketing
def test_showcase_locker_status_with_screenshots(authenticated_page):
    device_id = os.environ.get("E2E_DEVICE_ID", DEFAULT_E2E_DEVICE_ID).strip() or DEFAULT_E2E_DEVICE_ID

    response = send_and_wait(authenticated_page, f"What is the locker status for device {device_id}?")
    capture_screenshot(authenticated_page, "locker-status", "response")

    assert response.assistant_text.strip(), "Assistant response is empty"
    lowered = response.assistant_text.lower()
    error_markers = ["403", "forbidden", "error", "not have access", "may not have access"]
    assert not any(marker in lowered for marker in error_markers), (
        "Locker status showcase returned an error-like response instead of a valid status summary."
    )
    assert "locker" in lowered
    assert "status" in lowered or "activation" in lowered
    assert_timing(response, wall_max_ms=45_000)


@pytest.mark.e2e
@pytest.mark.marketing
def test_showcase_nearby_city_with_screenshots(authenticated_page):
    response = send_and_wait(authenticated_page, "Find available lockers near London.")
    capture_screenshot(authenticated_page, "nearby-city", "response")

    assert response.assistant_text.strip(), "Assistant response is empty"
    lowered = response.assistant_text.lower()
    assert "locker" in lowered or "device" in lowered
    assert "london" in lowered
    assert_timing(response, wall_max_ms=45_000)


@pytest.mark.e2e
@pytest.mark.marketing
def test_showcase_resend_pickup_code_with_screenshots(authenticated_page):
    parcel_number = (
        os.environ.get("E2E_PARCEL_NUMBER", DEFAULT_E2E_PARCEL_NUMBER).strip() or DEFAULT_E2E_PARCEL_NUMBER
    )

    prep = send_and_wait(
        authenticated_page,
        f"Please resend the pickup code for parcel {parcel_number}.",
    )
    capture_screenshot(authenticated_page, "pickup-resend", "confirmation-question")

    assert prep.assistant_text.strip(), "Assistant confirmation prompt is empty"

    done = send_and_wait(authenticated_page, "yes")
    capture_screenshot(authenticated_page, "pickup-resend", "response")

    assert done.assistant_text.strip(), "Assistant final response is empty"
    lowered = done.assistant_text.lower()
    assert "resend" in lowered or "resent" in lowered
    assert_timing(done, wall_max_ms=45_000)


@pytest.mark.e2e
@pytest.mark.marketing
def test_showcase_parcel_status_with_screenshots(authenticated_page):
    parcel_number = (
        os.environ.get("E2E_PARCEL_NUMBER", DEFAULT_E2E_PARCEL_NUMBER).strip() or DEFAULT_E2E_PARCEL_NUMBER
    )

    response = send_and_wait(
        authenticated_page,
        f"What is the current status of parcel {parcel_number}?",
    )
    capture_screenshot(authenticated_page, "parcel-status", "response")

    assert response.assistant_text.strip(), "Assistant response is empty"
    lowered = response.assistant_text.lower()
    assert "parcel" in lowered
    assert "status" in lowered or "delivered" in lowered or "pickup" in lowered
    assert_timing(response, wall_max_ms=45_000)


@pytest.mark.e2e
@pytest.mark.marketing
def test_showcase_accessible_devices_by_status_with_screenshots(authenticated_page):
    response = send_and_wait(
        authenticated_page,
        "List all accessible devices in status ACTIVE or MAINTENANCE.",
    )
    capture_screenshot(authenticated_page, "accessible-status", "response")

    assert response.assistant_text.strip(), "Assistant response is empty"
    lowered = response.assistant_text.lower()
    assert "device" in lowered or "locker" in lowered
    assert "active" in lowered or "maintenance" in lowered
    assert_timing(response, wall_max_ms=45_000)


@pytest.mark.e2e
@pytest.mark.marketing
def test_showcase_technical_snapshot_with_screenshots(authenticated_page):
    device_id = os.environ.get("E2E_DEVICE_ID", DEFAULT_E2E_DEVICE_ID).strip() or DEFAULT_E2E_DEVICE_ID

    response = send_and_wait(
        authenticated_page,
        f"Give me a technical device snapshot for locker {device_id}.",
    )
    capture_screenshot(authenticated_page, "device-snapshot", "response")

    assert response.assistant_text.strip(), "Assistant response is empty"
    lowered = response.assistant_text.lower()
    assert "snapshot" in lowered or "generation" in lowered or "rootzone" in lowered
    assert_timing(response, wall_max_ms=45_000)


@pytest.mark.e2e
@pytest.mark.marketing
def test_showcase_pickup_code_view_with_screenshots(authenticated_page):
    parcel_number = (
        os.environ.get("E2E_PARCEL_NUMBER", DEFAULT_E2E_PARCEL_NUMBER).strip() or DEFAULT_E2E_PARCEL_NUMBER
    )

    response = send_and_wait(
        authenticated_page,
        f"Show me the pickup code for parcel {parcel_number}.",
    )
    capture_screenshot(authenticated_page, "pickup-code-view", "response")

    assert response.assistant_text.strip(), "Assistant response is empty"
    lowered = response.assistant_text.lower()
    assert "code" in lowered or "pin" in lowered
    assert_timing(response, wall_max_ms=45_000)


@pytest.mark.e2e
@pytest.mark.marketing
def test_showcase_parcels_to_deliver_by_logistician_name_with_screenshots(authenticated_page):
    logistician_name = (
        os.environ.get("E2E_LOGISTICIAN_NAME", DEFAULT_LOGISTICIAN_NAME).strip() or DEFAULT_LOGISTICIAN_NAME
    )

    response = send_and_wait(
        authenticated_page,
        f"List parcels to deliver for logistician {logistician_name}.",
    )
    capture_screenshot(authenticated_page, "parcels-to-deliver", "response")

    assert response.assistant_text.strip(), "Assistant response is empty"
    lowered = response.assistant_text.lower()
    assert "deliver" in lowered or "parcel" in lowered
    assert_timing(response, wall_max_ms=45_000)


@pytest.mark.e2e
@pytest.mark.marketing
def test_showcase_occupied_boxes_with_screenshots(authenticated_page):
    device_id = os.environ.get("E2E_DEVICE_ID", DEFAULT_E2E_DEVICE_ID).strip() or DEFAULT_E2E_DEVICE_ID

    response = send_and_wait(
        authenticated_page,
        f"For device {device_id}, how many boxes are occupied?",
    )
    capture_screenshot(authenticated_page, "occupied-boxes", "response")

    assert response.assistant_text.strip(), "Assistant response is empty"
    lowered = response.assistant_text.lower()
    if "occupied" not in lowered:
        response = send_and_wait(
            authenticated_page,
            f"For device {device_id}, how many boxes are occupied? Please include the word occupied.",
        )
        capture_screenshot(authenticated_page, "occupied-boxes", "response-retry")
        lowered = response.assistant_text.lower()

    assert "occupied" in lowered
    assert_timing(response, wall_max_ms=45_000)


@pytest.mark.e2e
@pytest.mark.marketing
def test_showcase_all_accessible_devices_with_screenshots(authenticated_page):
    response = send_and_wait(
        authenticated_page,
        "List all accessible devices I can access.",
    )
    capture_screenshot(authenticated_page, "accessible-all", "response")

    assert response.assistant_text.strip(), "Assistant response is empty"
    lowered = response.assistant_text.lower()
    assert "accessible" in lowered or "device" in lowered or "locker" in lowered
    assert_timing(response, wall_max_ms=45_000)
