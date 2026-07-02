"""Tools for pickup code operations (Carrier Operation Manager)."""

from datetime import datetime, timezone
import uuid

from strands import tool

from .pmd_client import PMDClientError, client


def _resolve_parcel_id_from_number(parcel_number: str) -> tuple[str | None, str | None]:
    """Resolve parcel UUID from a parcel number using tracking-parcel search endpoint.

    Returns:
        (parcel_id, error_message)
    """
    number = (parcel_number or "").strip()
    if not number:
        return None, "Error: parcel_number is required."

    params = {
        "size": "100",
        "from": "0",
        "sortorder": "desc",
        "sortfield": "current.event.occurredAt",
        "attributes.handlingUnit.originalParcelNumber": f'"{number}"',
    }

    try:
        results = client.get("/api/tracking-parcel/parcels", params=params)
    except PMDClientError as exc:
        return None, f"Error: unable to look up parcel {number} (HTTP {exc.status_code})."

    data = results.get("data") if isinstance(results, dict) else []
    if not isinstance(data, list) or not data:
        return None, f"No parcel found with tracking number {number}."

    first = data[0] if isinstance(data[0], dict) else {}
    src = first.get("_source") if isinstance(first, dict) else {}
    attrs = src.get("attributes") if isinstance(src, dict) else {}
    parcel_id = str((attrs.get("id") if isinstance(attrs, dict) else "") or "").strip()
    if not parcel_id:
        return None, f"Unable to determine parcel ID for tracking number {number}."

    try:
        uuid.UUID(parcel_id)
    except ValueError:
        return None, f"Invalid parcel ID returned for tracking number {number}: {parcel_id}."

    return parcel_id, None


def _resolve_tracking_parcel_source(parcel_number: str) -> tuple[dict | None, str | None]:
    """Resolve the first tracking-parcel hit _source for a parcel number."""
    number = (parcel_number or "").strip()
    if not number:
        return None, "Error: parcel_number is required."

    params = {
        "size": "100",
        "from": "0",
        "sortorder": "desc",
        "sortfield": "current.event.occurredAt",
        "attributes.handlingUnit.originalParcelNumber": f'"{number}"',
    }

    try:
        results = client.get("/api/tracking-parcel/parcels", params=params)
    except PMDClientError as exc:
        return None, f"Error: unable to look up parcel {number} (HTTP {exc.status_code})."

    data = results.get("data") if isinstance(results, dict) else []
    if not isinstance(data, list) or not data:
        return None, f"No parcel found with tracking number {number}."

    first = data[0] if isinstance(data[0], dict) else {}
    source = first.get("_source") if isinstance(first, dict) else {}
    if not isinstance(source, dict):
        return None, f"Invalid tracking payload for parcel {number}."

    return source, None


def _first_non_empty(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _extract_box_path_from_events(source: dict) -> str:
    events = source.get("events")
    if not isinstance(events, list):
        return ""
    for event in events:
        if not isinstance(event, dict):
            continue
        locker = event.get("locker")
        if not isinstance(locker, dict):
            continue
        box_path = _first_non_empty(locker.get("boxPath"))
        if box_path:
            return box_path
    return ""


def _extract_box_allocated(source: dict) -> tuple[dict | None, str | None]:
    current = source.get("current") if isinstance(source, dict) else {}
    current_event = current.get("event") if isinstance(current, dict) else {}
    current_locker = current_event.get("locker") if isinstance(current_event, dict) else {}

    tracking_event = source.get("trackingEvent") if isinstance(source, dict) else {}
    tracking_box_allocated = tracking_event.get("boxAllocated") if isinstance(tracking_event, dict) else {}

    current_box_allocated = current_locker.get("boxAllocated") if isinstance(current_locker, dict) else {}

    code = _first_non_empty(
        current_box_allocated.get("code") if isinstance(current_box_allocated, dict) else "",
        tracking_box_allocated.get("code") if isinstance(tracking_box_allocated, dict) else "",
    )
    size = _first_non_empty(
        current_box_allocated.get("size") if isinstance(current_box_allocated, dict) else "",
        tracking_box_allocated.get("size") if isinstance(tracking_box_allocated, dict) else "",
    )

    if not code:
        return None, "Unable to determine boxAllocated.code from tracking parcel payload."
    if not size:
        return None, "Unable to determine boxAllocated.size from tracking parcel payload."

    return {"code": code, "size": size}, None


def _utc_now_iso_millis() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _build_pinres_payload(source: dict, requested_parcel_number: str) -> tuple[dict | None, str | None]:
    attrs = source.get("attributes") if isinstance(source, dict) else {}
    if not isinstance(attrs, dict):
        return None, "Invalid tracking parcel payload: attributes missing."

    logistician = attrs.get("logistician") if isinstance(attrs, dict) else {}
    if not isinstance(logistician, dict):
        return None, "Unable to determine logistician information from tracking parcel payload."

    current = source.get("current") if isinstance(source, dict) else {}
    current_event = current.get("event") if isinstance(current, dict) else {}
    current_locker = current_event.get("locker") if isinstance(current_event, dict) else {}
    device = source.get("device") if isinstance(source, dict) else {}

    device_code = _first_non_empty(
        current_locker.get("deviceCode") if isinstance(current_locker, dict) else "",
        device.get("deviceCode") if isinstance(device, dict) else "",
    )
    if not device_code:
        return None, "Unable to determine deviceCode from tracking parcel payload."

    logistician_code = _first_non_empty(logistician.get("code"))
    if not logistician_code:
        return None, "Unable to determine logisticianCode from tracking parcel payload."

    logistician_name = _first_non_empty(logistician.get("name"))
    if not logistician_name:
        return None, "Unable to determine logisticianName from tracking parcel payload."

    parcel_number = _first_non_empty(requested_parcel_number, attrs.get("parcelNumber"), attrs.get("parcelBarcode"))
    if not parcel_number:
        return None, "Unable to determine parcel.parcelNumber from tracking parcel payload."

    box_path = _first_non_empty(
        current_locker.get("boxPath") if isinstance(current_locker, dict) else "",
        _extract_box_path_from_events(source),
    )
    if not box_path:
        return None, "Unable to determine boxPath from tracking parcel payload."

    box_allocated, box_error = _extract_box_allocated(source)
    if box_error:
        return None, box_error

    pickup_allowed_until = _first_non_empty(attrs.get("expirationDate"))
    if not pickup_allowed_until:
        return None, "Unable to determine pickupAllowedUntil from tracking parcel payload."

    payload = {
        "timestamp": _utc_now_iso_millis(),
        "deviceCode": device_code,
        "logisticianCode": logistician_code,
        "logisticianName": logistician_name,
        "parcel": {"parcelNumber": parcel_number},
        "boxPath": box_path,
        "boxAllocated": box_allocated,
        "pickupAllowedUntil": pickup_allowed_until,
    }
    return payload, None


@tool
def view_pickup_code(parcel_id: str = "", parcel_number: str = "") -> str:
    """View the pickup PIN code for a parcel.

    Args:
        parcel_id: Optional parcel UUID used by PMD API.
        parcel_number: The parcel tracking number known by end users. Preferred user input.

    Returns:
        The pickup PIN code for the parcel, or an error message.
    """
    requested_id = (parcel_id or "").strip()
    number = (parcel_number or "").strip()

    if not requested_id and not number:
        return "Error: provide parcel_id (UUID) or parcel_number."

    resolved_id = requested_id
    if resolved_id:
        try:
            uuid.UUID(resolved_id)
        except ValueError:
            return "Error: parcel_id must be a valid UUID."

    if not resolved_id:
        resolved_id, error = _resolve_parcel_id_from_number(number)
        if error:
            return error

    try:
        pin_payload = client.get(f"/api/pincode/{resolved_id}")
    except PMDClientError as exc:
        return f"Error: unable to retrieve pickup PIN for parcel {resolved_id} (HTTP {exc.status_code})."

    pin = pin_payload.get("pinCode1") if isinstance(pin_payload, dict) else None
    if not pin:
        return f"Pickup PIN code not available for parcel {resolved_id}."

    if number:
        return f"Pickup PIN code for parcel {number} (id {resolved_id}): {pin}"
    return f"Pickup PIN code for parcel id {resolved_id}: {pin}"


@tool
def resend_pickup_code(parcel_number: str) -> str:
    """Resend the pickup notification (code) for a parcel to the recipient.

    This is a modification action - it triggers an SMS/email to the recipient.

    Args:
        parcel_number: The parcel tracking number for which to resend the pickup code.

    Returns:
        Confirmation that the pickup code was resent, or an error message.
    """
    number = (parcel_number or "").strip()
    if not number:
        return "Error: parcel_number is required."

    source, error = _resolve_tracking_parcel_source(number)
    if error:
        return error

    payload, payload_error = _build_pinres_payload(source or {}, number)
    if payload_error:
        return f"Error: failed to build PINRES payload for {number}. {payload_error}"

    try:
        client.post("/api/parcel_commands/add_event/PINRES", json_body=payload)
    except PMDClientError as exc:
        return f"Error: failed to resend pickup code for {number} (HTTP {exc.status_code})."

    return f"Pickup code for parcel {number} has been resent to the recipient."
