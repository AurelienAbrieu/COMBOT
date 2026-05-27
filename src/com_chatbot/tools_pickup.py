"""Tools for pickup code operations (Carrier Operation Manager)."""

from strands import tool

from .pmd_client import PMDClientError, client


@tool
def view_pickup_code(parcel_number: str = "", recipient_name: str = "") -> str:
    """View the pickup code for a parcel. Search by parcel number or recipient name.

    Args:
        parcel_number: The parcel tracking number. Preferred lookup method.
        recipient_name: The recipient name to search for. Used when parcel number is unknown.

    Returns:
        The pickup code (PIN) for the parcel, or an error message.
    """
    number = (parcel_number or "").strip()
    name = (recipient_name or "").strip()

    if not number and not name:
        return "Error: provide either a parcel_number or a recipient_name."

    # If parcel number is provided, look up directly
    if number:
        try:
            results = client.get("/api/parcels/tracking", params={"trackingNumber": number})
        except PMDClientError as exc:
            return f"Error: unable to look up parcel {number} (HTTP {exc.status_code})."

        parcels = results if isinstance(results, list) else (results.get("items") or results.get("parcels") or [])
        if not parcels:
            return f"No parcel found with tracking number {number}."

        parcel = parcels[0] if isinstance(parcels, list) and parcels else parcels
        if isinstance(parcel, dict):
            pin = parcel.get("pinCode") or parcel.get("pickupCode") or parcel.get("accessCode")
            if pin:
                return f"Pickup code for parcel {number}: {pin}"
            parcel_id = parcel.get("id") or parcel.get("parcelId")
            if parcel_id:
                try:
                    detail = client.get(f"/api/parcels/{parcel_id}/pincode")
                    pin = detail.get("pinCode") or detail.get("code") or detail.get("pin")
                    if pin:
                        return f"Pickup code for parcel {number}: {pin}"
                except PMDClientError:
                    pass
            return f"Pickup code not available for parcel {number}."

    # Search by recipient name
    try:
        results = client.get("/api/parcels", params={"query": name, "status": "LOADED"})
    except PMDClientError as exc:
        return f"Error: unable to search parcels for recipient '{name}' (HTTP {exc.status_code})."

    parcels = results if isinstance(results, list) else (results.get("items") or results.get("parcels") or [])
    if not parcels:
        return f"No loaded parcels found for recipient '{name}'."

    lines = []
    for p in (parcels if isinstance(parcels, list) else [parcels]):
        if not isinstance(p, dict):
            continue
        p_num = p.get("trackingNumber") or p.get("parcelNumber") or "N/A"
        pin = p.get("pinCode") or p.get("pickupCode") or "N/A"
        lines.append(f"Parcel {p_num}: pickup code = {pin}")

    return "\n".join(lines) if lines else f"No pickup codes found for '{name}'."


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

    # Look up the parcel to get its ID
    try:
        results = client.get("/api/parcels/tracking", params={"trackingNumber": number})
    except PMDClientError as exc:
        return f"Error: unable to look up parcel {number} (HTTP {exc.status_code})."

    parcels = results if isinstance(results, list) else (results.get("items") or results.get("parcels") or [])
    if not parcels:
        return f"No parcel found with tracking number {number}."

    parcel = parcels[0] if isinstance(parcels, list) else parcels
    if not isinstance(parcel, dict):
        return f"Unexpected response format for parcel {number}."

    parcel_id = parcel.get("id") or parcel.get("parcelId")
    if not parcel_id:
        return f"Unable to determine parcel ID for {number}."

    try:
        client.post(f"/api/parcels/{parcel_id}/resendPinCode")
    except PMDClientError as exc:
        return f"Error: failed to resend pickup code for {number} (HTTP {exc.status_code})."

    return f"Pickup code for parcel {number} has been resent to the recipient."
