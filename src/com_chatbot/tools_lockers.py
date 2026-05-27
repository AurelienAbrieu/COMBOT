"""Tools for locating available lockers by GPS coordinates (Carrier Operation Manager)."""

import math

from strands import tool

from .pmd_client import PMDClientError, client


@tool
def find_nearby_lockers(latitude: float, longitude: float, radius_km: float = 5.0) -> str:
    """Find available lockers near given GPS coordinates.

    Searches for lockers within a specified radius of the provided coordinates.
    Useful for carriers looking for drop-off points in an area (e.g. London area).

    Args:
        latitude: GPS latitude (e.g. 51.5074 for London).
        longitude: GPS longitude (e.g. -0.1278 for London).
        radius_km: Search radius in kilometers (default 5 km).

    Returns:
        A list of nearby lockers with their address, distance, and availability.
    """
    if not (-90 <= latitude <= 90):
        return "Error: latitude must be between -90 and 90."
    if not (-180 <= longitude <= 180):
        return "Error: longitude must be between -180 and 180."

    try:
        devices = client.get("/api/assets/devices")
    except PMDClientError as exc:
        return f"Error: unable to retrieve locker list (HTTP {exc.status_code})."

    if isinstance(devices, dict):
        devices = devices.get("items") or devices.get("devices") or devices.get("data") or []
    if not isinstance(devices, list):
        devices = []

    nearby = []
    for device in devices:
        if not isinstance(device, dict):
            continue

        address = device.get("address") or {}
        if not isinstance(address, dict):
            continue

        dev_lat = address.get("latitude") or address.get("lat")
        dev_lon = address.get("longitude") or address.get("lon") or address.get("lng")

        if dev_lat is None or dev_lon is None:
            continue

        try:
            dev_lat = float(dev_lat)
            dev_lon = float(dev_lon)
        except (ValueError, TypeError):
            continue

        distance = _haversine_km(latitude, longitude, dev_lat, dev_lon)
        if distance <= radius_km:
            code = device.get("code") or device.get("deviceCode") or "N/A"
            name = device.get("name") or code
            status = device.get("status") or "unknown"

            address_parts = []
            for field in ("streetLine1", "streetLine2", "city", "zipCode"):
                val = address.get(field)
                if val and str(val).strip():
                    address_parts.append(str(val).strip())
            address_str = ", ".join(address_parts) if address_parts else "N/A"

            nearby.append({
                "code": code,
                "name": name,
                "status": status,
                "address": address_str,
                "distance_km": round(distance, 2),
            })

    nearby.sort(key=lambda x: x["distance_km"])

    if not nearby:
        return f"No lockers found within {radius_km} km of ({latitude}, {longitude})."

    lines = [f"Found {len(nearby)} locker(s) within {radius_km} km:"]
    for loc in nearby:
        lines.append(
            f"- {loc['name']} ({loc['code']}) - {loc['status']} - "
            f"{loc['address']} - {loc['distance_km']} km away"
        )

    return "\n".join(lines)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two GPS points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c
