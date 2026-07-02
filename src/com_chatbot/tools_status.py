"""Tools for locker and parcel status queries (Carrier Operation Manager)."""

import json
from strands import tool

from .pmd_client import PMDClientError, client


_ACTIVATION_BLOCKING_VALUES = {"BLOCKED", "INACTIVE", "MAINTENANCE", "ARCHIVED"}
_OCCUPIED_PARCEL_STATUSES = {"LIVCFP", "RETCFM", "LIVBLK", "LIVEXP"}


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


def _fetch_box_view(device_code: str) -> dict:
    payload = client.get(f"/api/parcel_events_in_devices/{device_code}/boxView")
    if isinstance(payload, dict):
        return payload
    return {"boxes": []}


def _normalize_box_path(box_path: object) -> str:
    return str(box_path or "").strip().lstrip("/")


def _extract_box_view_occupancy(box_view_payload: dict) -> tuple[list[str], int]:
    boxes = box_view_payload.get("boxes")
    if not isinstance(boxes, list):
        return [], 0

    occupied_box_paths: set[str] = set()
    announced_without_box = 0

    for box in boxes:
        if not isinstance(box, dict):
            continue

        parcels = box.get("parcels")
        if not isinstance(parcels, list):
            parcels = []

        normalized_box_path = _normalize_box_path(box.get("boxPath"))

        if not normalized_box_path:
            announced_without_box += len(parcels)
            continue

        is_occupied = False
        for parcel in parcels:
            if not isinstance(parcel, dict):
                continue
            status = str(parcel.get("status") or "").upper().strip()
            if status in _OCCUPIED_PARCEL_STATUSES:
                is_occupied = True
                break

        if is_occupied:
            occupied_box_paths.add(normalized_box_path)

    return sorted(occupied_box_paths), announced_without_box


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

    available_by_state_count = 0
    blocked_count = 0
    damaged_count = 0

    for box in box_zones:
        available = _boolish(_state_value(box, "available"))
        filling = str(_state_value(box, "filling") or "").upper()
        activation = str(_state_value(box, "activation") or "").upper()
        hard = str(_state_value(box, "hard") or "").upper()
        security_breach = str(_state_value(box, "securityBreach") or "NONE").upper()

        if available is True:
            available_by_state_count += 1
        elif filling == "EMPTY":
            available_by_state_count += 1

        if activation in _ACTIVATION_BLOCKING_VALUES or security_breach != "NONE":
            blocked_count += 1
        if hard == "DAMAGED":
            damaged_count += 1

    occupied_box_paths: list[str] = []
    announced_without_box = 0
    box_view_error = None
    try:
        box_view_payload = _fetch_box_view(device_code)
        occupied_box_paths, announced_without_box = _extract_box_view_occupancy(box_view_payload)
    except PMDClientError as exc:
        box_view_error = f"HTTP {exc.status_code}"

    occupied_count = len(occupied_box_paths)
    estimated_free_count = max(len(box_zones) - occupied_count, 0)

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
        f"Available (device state): {available_by_state_count}",
        f"Blocked or restricted: {blocked_count}",
        f"Damaged: {damaged_count}",
    ]

    if box_view_error:
        lines.append(f"Occupied (parcel events boxView): unavailable ({box_view_error})")
    else:
        lines.append(f"Occupied (parcel events boxView): {occupied_count}")
        lines.append(f"Estimated free (total boxes - occupied): {estimated_free_count}")
        if announced_without_box:
            lines.append(f"Announced without allocated boxPath: {announced_without_box}")
        if occupied_box_paths:
            lines.append(f"Occupied box paths: {', '.join(occupied_box_paths)}")

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
def search_parcels(
    device_ids: str = "",
    statuses: str = "",
    parcel_number: str = "",
    logistician: str = "",
    logistician_code: str = "",
    logistician_name: str = "",
    exclude_statuses: str = "",
) -> str:
    """Search parcels in lockers by device ID(s) and/or status, or look up a parcel by tracking number.

    Args:
        device_ids: Comma-separated locker device IDs (e.g. "GBR00043,GBR22042"). Used to list parcels in specific lockers.
        statuses: Comma-separated parcel statuses to filter (e.g. "RETCFM,LIVEXP,LIVBLK" for parcels to pick up, "LIVCFP" for parcels already in a device, "EXPINI" for parcels awaiting delivery). Optional.
        parcel_number: A parcel tracking/barcode number to look up (e.g. "7614335752"). When provided, device_ids and statuses are ignored.
        logistician: Optional logistician identifier accepted as either code or exact name.
        logistician_code: Optional logistician code used to keep only parcels belonging to that logistician.
        logistician_name: Optional logistician exact name used to keep only parcels belonging to that logistician.
        exclude_statuses: Optional comma-separated statuses to exclude after retrieval (e.g. "LIVCFP").

    Returns:
        A text summary of matching parcels with status, box, recipient, and dates.
    """
    number = (parcel_number or "").strip()
    devices = (device_ids or "").strip()
    status_filter = (statuses or "").strip()
    logistician_any_filter = (logistician or "").strip()
    logistician_filter = (logistician_code or "").strip()
    logistician_name_filter = (logistician_name or "").strip()
    excluded_statuses = {s.strip().upper() for s in (exclude_statuses or "").split(",") if s.strip()}

    if not number and not devices and not logistician_filter and not logistician_name_filter and not logistician_any_filter:
        return "Error: provide at least device_ids, logistician, logistician_code, logistician_name, or parcel_number."

    params: dict = {"size": "100", "from": "0", "sortorder": "desc", "sortfield": "current.event.occurredAt"}

    if number:
        params["attributes.handlingUnit.originalParcelNumber"] = f'"{number}"'
    else:
        if devices:
            # Canonical endpoint contract for parcels by locker state.
            params["fterms_events.locker.deviceCode"] = devices
        params["nestedSearch"] = "false"
        if status_filter:
            status_values = [s.strip().upper() for s in status_filter.split(",") if s.strip()]
            # In tracking-parcel views, loaded parcels are reliably exposed via trackingEvent filters.
            if status_values and all(s == "LIVCFP" for s in status_values):
                params["fterms_trackingEvent.status"] = "LIVCFP"
                params["fterms_trackingEvent.isInDevice"] = "true"
            else:
                params["fterms_current.event.status"] = status_filter

    try:
        results = client.get("/api/tracking-parcel/parcels", params=params)
    except PMDClientError as exc:
        return f"Error: unable to search parcels (HTTP {exc.status_code})."

    data = results.get("data") if isinstance(results, dict) else []
    if not isinstance(data, list) or not data:
        if number:
            return f"No parcel found with tracking number {number}."
        if logistician_filter or logistician_name_filter or logistician_any_filter:
            requested = logistician_filter or logistician_name_filter or logistician_any_filter
            return f"No parcels found for logistician {requested}."
        return f"No parcels found for device(s) {devices}."

    filtered_items: list[dict] = []
    logistician_filter_upper = logistician_filter.upper()
    logistician_name_filter_folded = logistician_name_filter.casefold()
    logistician_any_filter_upper = logistician_any_filter.upper()
    logistician_any_filter_folded = logistician_any_filter.casefold()
    for item in data:
        if not isinstance(item, dict):
            continue

        src = item.get("_source") or {}
        attrs = src.get("attributes") or {}
        current = src.get("current") if isinstance(src.get("current"), dict) else {}
        current_event = current.get("event") if isinstance(current.get("event"), dict) else {}
        tracking_event = src.get("trackingEvent") if isinstance(src.get("trackingEvent"), dict) else {}
        te = tracking_event or current_event

        current_status = str(te.get("status") or "").upper().strip()
        if excluded_statuses and current_status in excluded_statuses:
            continue

        item_logistician = attrs.get("logistician") or {}
        item_logistician_code = str(item_logistician.get("code") or "").upper().strip()
        item_logistician_name = str(item_logistician.get("name") or "").strip()
        item_logistician_name_folded = item_logistician_name.casefold()

        if logistician_filter_upper:
            if item_logistician_code != logistician_filter_upper:
                continue

        if logistician_name_filter_folded:
            if item_logistician_name_folded != logistician_name_filter_folded:
                continue

        if logistician_any_filter:
            if item_logistician_code != logistician_any_filter_upper and item_logistician_name_folded != logistician_any_filter_folded:
                continue

        filtered_items.append(item)

    if not filtered_items:
        if number:
            return f"No parcel found with tracking number {number}."
        effective_logistician = logistician_filter or logistician_name_filter or logistician_any_filter
        if effective_logistician and status_filter and excluded_statuses:
            return (
                f"No parcels found for logistician {effective_logistician} "
                f"with statuses {status_filter} excluding {', '.join(sorted(excluded_statuses))}."
            )
        if effective_logistician:
            return f"No parcels found for logistician {effective_logistician}."
        return "No parcels found with the requested filters."

    total = len(filtered_items)
    lines = [f"Total parcels: {total}"]

    for item in filtered_items:
        src = item.get("_source") or {} if isinstance(item, dict) else {}
        attrs = src.get("attributes") or {}
        current = src.get("current") if isinstance(src.get("current"), dict) else {}
        current_event = current.get("event") if isinstance(current.get("event"), dict) else {}
        tracking_event = src.get("trackingEvent") if isinstance(src.get("trackingEvent"), dict) else {}
        te = tracking_event or current_event
        contact = attrs.get("contact") or {}
        logist = attrs.get("logistician") or {}
        locker = te.get("locker") if isinstance(te.get("locker"), dict) else {}
        box = te.get("boxAllocated") if isinstance(te.get("boxAllocated"), dict) else (locker.get("boxAllocated") or {})

        barcode = attrs.get("parcelBarcode") or attrs.get("parcelNumber") or "N/A"
        cur_status = te.get("status") or "N/A"
        phase = te.get("phase") or "N/A"
        in_device = te.get("isInDevice") if te.get("isInDevice") is not None else locker.get("isInDevice")
        expired = te.get("isExpired") if te.get("isExpired") is not None else locker.get("isExpired")
        blocked = te.get("isBlocked") if te.get("isBlocked") is not None else locker.get("isBlocked")

        box_alias = locker.get("boxAlias") or box.get("boxAlias") or locker.get("boxNumber") or "N/A"
        box_size = box.get("size") or "?"
        box_info = f"{box_alias} ({box_size})" if box else box_alias
        recipient = f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip() or "N/A"
        delivery = attrs.get("deliveryDate") or "N/A"
        expiration = attrs.get("expirationDate") or "N/A"
        logist_info = f"{logist.get('name', '')} ({logist.get('code', '')})".strip(" ()") if logist else "N/A"
        device_code = locker.get("deviceCode") or (src.get("device") or {}).get("deviceCode") or "N/A"

        flags = []
        if in_device:
            flags.append("inDevice")
        if expired:
            flags.append("expired")
        if blocked:
            flags.append("blocked")

        lines.append(f"---\nParcel: {barcode} | Device: {device_code}")
        lines.append(f"  Status: {cur_status} ({phase})" + (f" [{', '.join(flags)}]" if flags else ""))
        lines.append(f"  Box: {box_info} | Recipient: {recipient}")
        lines.append(f"  Delivered: {delivery} | Expires: {expiration}")
        lines.append(f"  Logistician: {logist_info}")

    return "\n".join(lines)
