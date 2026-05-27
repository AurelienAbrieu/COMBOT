"""Tools for locker and parcel status queries (Carrier Operation Manager)."""

from strands import tool

from .pmd_client import PMDClientError, client


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
        device_payload = client.get(f"/api/assets/devices/{device_code}")
    except PMDClientError as exc:
        return f"Error: unable to retrieve locker {device_code} (HTTP {exc.status_code})."

    # Extract basic info
    name = device_payload.get("name", device_code)
    status = device_payload.get("status", "unknown")
    address_parts = []
    address = device_payload.get("address") or {}
    if isinstance(address, dict):
        for field in ("streetLine1", "streetLine2", "city", "zipCode", "countryCode"):
            val = address.get(field)
            if val and str(val).strip():
                address_parts.append(str(val).strip())
    location = ", ".join(address_parts) if address_parts else "N/A"

    # Get box view for occupancy info
    blocked_count = 0
    expired_count = 0
    total_boxes = 0
    occupied_count = 0
    available_count = 0
    try:
        boxview = client.get(f"/api/parcel_events_in_devices/{device_code}/boxView")
        boxes = boxview.get("boxes", [])
        if isinstance(boxes, list):
            total_boxes = len(boxes)
            for box in boxes:
                if not isinstance(box, dict):
                    continue
                box_status = str(box.get("status", "")).lower()
                if box_status == "blocked":
                    blocked_count += 1
                elif box_status in ("occupied", "loaded"):
                    occupied_count += 1
                    # Check for expired parcels
                    if box.get("expired", False):
                        expired_count += 1
                elif box_status in ("available", "free"):
                    available_count += 1
    except PMDClientError:
        pass

    lines = [
        f"Locker: {name} ({device_code})",
        f"Location: {location}",
        f"Status: {status}",
        f"Total boxes: {total_boxes}",
        f"Available: {available_count}",
        f"Occupied: {occupied_count}",
        f"Blocked: {blocked_count}",
        f"Expired parcels: {expired_count}",
    ]

    return "\n".join(lines)


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
