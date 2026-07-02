"""Tools for pickup code operations (Carrier Operation Manager)."""

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

    parcel_id, error = _resolve_parcel_id_from_number(number)
    if error:
        return error

    try:
        client.post(f"/api/parcels/{parcel_id}/resendPinCode")
    except PMDClientError as exc:
        return f"Error: failed to resend pickup code for {number} (HTTP {exc.status_code})."

    return f"Pickup code for parcel {number} has been resent to the recipient."
