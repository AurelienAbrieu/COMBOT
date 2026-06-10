"""Tools for locker and parcel status queries (Carrier Operation Manager)."""

import json
from strands import tool

from .pmd_client import PMDClientError, client


_ACTIVATION_BLOCKING_VALUES = {"BLOCKED", "INACTIVE", "MAINTENANCE", "ARCHIVED"}


def _normalize_device_payload(payload: object) -> dict:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                return item
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _iter_zones(zone: dict) -> list[dict]:
    if not isinstance(zone, dict):
        return []
    flattened = [zone]
    for child in zone.get("zone", []):
        if isinstance(child, dict):
            flattened.extend(_iter_zones(child))
    return flattened


def _state_value(zone: dict, state_name: str) -> object:
    state = zone.get("state")
    if not isinstance(state, dict):
        return None
    node = state.get(state_name)
    if not isinstance(node, dict):
        return None
    return node.get("value")


def _state_timestamp(zone: dict, state_name: str) -> str:
    state = zone.get("state")
    if not isinstance(state, dict):
        return "N/A"
    node = state.get(state_name)
    if not isinstance(node, dict):
        return "N/A"
    value = node.get("timestamp")
    return str(value) if value else "N/A"


def _format_state(zone: dict, state_name: str) -> str:
    value = _state_value(zone, state_name)
    timestamp = _state_timestamp(zone, state_name)
    if value is None:
        return "N/A"
    return f"{value} (at {timestamp})"


def _boolish(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "available", "empty", "connected", "active", "operational"}:
            return True
        if lowered in {"false", "0", "no", "n", "occupied", "full", "disconnected", "inactive", "damaged"}:
            return False
    return None


def _location_from_zone(root_zone: dict) -> str:
    attrs = root_zone.get("attributes")
    if not isinstance(attrs, dict):
        return "N/A"
    location = attrs.get("location")
    if not isinstance(location, dict):
        return "N/A"

    parts: list[str] = []
    address = location.get("address")
    if isinstance(address, list):
        parts.extend(str(x).strip() for x in address if str(x).strip())
    elif isinstance(address, str) and address.strip():
        parts.append(address.strip())

    for key in ("city", "postCode", "countryIsoCode", "country"):
        value = location.get(key)
        if value and str(value).strip():
            parts.append(str(value).strip())

    if not parts:
        return "N/A"
    return ", ".join(parts)


def _fetch_device(device_code: str, with_state_event: bool, use_cache: bool) -> dict:
    payload = client.get(
        f"/api/assets/devices/{device_code}",
        params={"withStateEvent": with_state_event, "cache": use_cache},
    )
    return _normalize_device_payload(payload)


@tool
def get_locker_status(device_id: str) -> str:
    """Search for the status of a locker based on its device ID.

    Args:
        device_id: The locker device ID (e.g. GBR00043, GBR22042).

    Returns:
        A text summary of the locker status including location, active/inactive state,
        number of blocked boxes, and expired parcels.
    """
    device_code = (device_id or "").strip()
    if not device_code:
        return "Error: device_id is required."

    try:
        device_payload = _fetch_device(device_code, with_state_event=True, use_cache=True)
    except PMDClientError as exc:
        return f"Error: unable to retrieve locker {device_code} (HTTP {exc.status_code})."

    if not device_payload:
        return f"No device payload returned for locker {device_code}."

    description = device_payload.get("deviceDescription")
    if not isinstance(description, dict):
        return f"Locker {device_code} has no deviceDescription in API payload."

    root_zone = description.get("zone")
    if not isinstance(root_zone, dict):
        return f"Locker {device_code} has no root zone in API payload."

    all_zones = _iter_zones(root_zone)
    box_zones = [z for z in all_zones if str(z.get("type", "")).upper() == "BOX"]

    available_count = 0
    occupied_count = 0
    blocked_count = 0
    damaged_count = 0

    for box in box_zones:
        available = _boolish(_state_value(box, "available"))
        filling = str(_state_value(box, "filling") or "").upper()
        activation = str(_state_value(box, "activation") or "").upper()
        hard = str(_state_value(box, "hard") or "").upper()
        security_breach = str(_state_value(box, "securityBreach") or "NONE").upper()

        if available is True:
            available_count += 1
        elif available is False:
            occupied_count += 1
        elif filling == "EMPTY":
            available_count += 1
        elif filling == "FULL":
            occupied_count += 1

        if activation in _ACTIVATION_BLOCKING_VALUES or security_breach != "NONE":
            blocked_count += 1
        if hard == "DAMAGED":
            damaged_count += 1

    name = str(device_payload.get("name") or device_code)
    generation = str(device_payload.get("generation") or "N/A")
    mode = str(description.get("mode") or "N/A")
    install_type = str(device_payload.get("installType") or "N/A")
    location = _location_from_zone(root_zone)
    activation_state = _format_state(root_zone, "activation")
    connection_state = _format_state(root_zone, "connection")

    lines = [
        f"Locker: {name} ({device_code})",
        f"Generation: {generation}",
        f"Mode: {mode}",
        f"Install type: {install_type}",
        f"Location: {location}",
        f"Activation: {activation_state}",
        f"Connection: {connection_state}",
        f"Total boxes: {len(box_zones)}",
        f"Available: {available_count}",
        f"Occupied: {occupied_count}",
        f"Blocked or restricted: {blocked_count}",
        f"Damaged: {damaged_count}",
    ]

    return "\n".join(lines)


@tool
def get_locker_zone_status(device_id: str, zone_path: str) -> str:
    """Return detailed states for one device zone path from /api/assets/devices/{id}.

    Args:
        device_id: The locker device ID (e.g. GBR00043).
        zone_path: Exact zone path as stored in deviceDescription.zone.path.

    Returns:
        A text summary of key states for the requested zone.
    """
    device_code = (device_id or "").strip()
    expected_path = (zone_path or "").strip()
    if not device_code:
        return "Error: device_id is required."
    if not expected_path:
        return "Error: zone_path is required."

    try:
        device_payload = _fetch_device(device_code, with_state_event=True, use_cache=True)
    except PMDClientError as exc:
        return f"Error: unable to retrieve locker {device_code} (HTTP {exc.status_code})."

    root_zone = ((device_payload.get("deviceDescription") or {}).get("zone") or {})
    if not isinstance(root_zone, dict):
        return f"Locker {device_code} has no root zone in API payload."

    match = None
    for zone in _iter_zones(root_zone):
        if str(zone.get("path") or "").strip() == expected_path:
            match = zone
            break

    if match is None:
        return f"Zone path '{expected_path}' not found for locker {device_code}."

    zone_type = str(match.get("type") or "N/A")
    subtype = str(match.get("subtype") or "N/A")
    lines = [
        f"Locker: {device_code}",
        f"Zone path: {expected_path}",
        f"Zone type: {zone_type}",
        f"Zone subtype: {subtype}",
        f"Activation: {_format_state(match, 'activation')}",
        f"Door: {_format_state(match, 'door')}",
        f"Hard: {_format_state(match, 'hard')}",
        f"Filling: {_format_state(match, 'filling')}",
        f"Available: {_format_state(match, 'available')}",
        f"Security breach: {_format_state(match, 'securityBreach')}",
        f"Connection: {_format_state(match, 'connection')}",
        f"Battery: {_format_state(match, 'battery')}",
        f"Cleanliness: {_format_state(match, 'cleanliness')}",
    ]
    return "\n".join(lines)


@tool
def get_locker_device_snapshot(device_id: str) -> str:
    """Return a compact JSON snapshot of /api/assets/devices/{id}.

    Args:
        device_id: The locker device ID (e.g. GBR00043).

    Returns:
        A compact JSON object with key device fields and root zone states.
    """
    device_code = (device_id or "").strip()
    if not device_code:
        return "Error: device_id is required."

    try:
        device_payload = _fetch_device(device_code, with_state_event=True, use_cache=True)
    except PMDClientError as exc:
        return f"Error: unable to retrieve locker {device_code} (HTTP {exc.status_code})."

    if not device_payload:
        return f"No device payload returned for locker {device_code}."

    description = device_payload.get("deviceDescription")
    root_zone = (description or {}).get("zone") if isinstance(description, dict) else {}
    root_zone = root_zone if isinstance(root_zone, dict) else {}

    snapshot = {
        "id": device_payload.get("id"),
        "name": device_payload.get("name"),
        "generation": device_payload.get("generation"),
        "installType": device_payload.get("installType"),
        "mode": (description or {}).get("mode") if isinstance(description, dict) else None,
        "location": _location_from_zone(root_zone),
        "rootZone": {
            "path": root_zone.get("path"),
            "type": root_zone.get("type"),
            "state": root_zone.get("state"),
        },
        "boxCount": len([z for z in _iter_zones(root_zone) if str(z.get("type", "")).upper() == "BOX"]),
    }
    return json.dumps(snapshot, ensure_ascii=True, indent=2, default=str)


@tool
def check_parcel_status(parcel_number: str) -> str:
    """Search for the current status of a parcel based on its parcel/tracking number.

    Args:
        parcel_number: The parcel tracking number (e.g. H05QTA0216703036).

    Returns:
        A text summary of the parcel status including drop-off time, location,
        and current state.
    """
    number = (parcel_number or "").strip()
    if not number:
        return "Error: parcel_number is required."

    try:
        results = client.get("/api/parcels/tracking", params={"trackingNumber": number})
    except PMDClientError as exc:
        return f"Error: unable to look up parcel {number} (HTTP {exc.status_code})."

    if isinstance(results, list):
        parcels = results
    elif isinstance(results, dict):
        parcels = results.get("items") or results.get("parcels") or results.get("data") or []
        if not isinstance(parcels, list):
            parcels = [results]
    else:
        parcels = []

    if not parcels:
        return f"No parcel found with tracking number {number}."

    lines = []
    for parcel in parcels:
        if not isinstance(parcel, dict):
            continue
        p_number = parcel.get("trackingNumber") or parcel.get("parcelNumber") or number
        status = parcel.get("status") or parcel.get("lastEventCode") or "unknown"
        drop_date = parcel.get("dropDate") or parcel.get("createdAt") or "N/A"
        device = parcel.get("deviceCode") or parcel.get("deviceName") or "N/A"
        box = parcel.get("boxNumber") or parcel.get("box") or "N/A"
        recipient = parcel.get("recipientName") or parcel.get("recipient") or "N/A"

        lines.append(f"Parcel: {p_number}")
        lines.append(f"  Status: {status}")
        lines.append(f"  Drop date: {drop_date}")
        lines.append(f"  Device: {device}")
        lines.append(f"  Box: {box}")
        lines.append(f"  Recipient: {recipient}")

    return "\n".join(lines)
