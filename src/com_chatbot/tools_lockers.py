"""Tools for locating available lockers by GPS coordinates (Carrier Operation Manager)."""

import math

from strands import tool

from .pmd_client import PMDClientError, client


def _normalize_devices_payload(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "devices", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _fetch_all_devices(page_size: int = 200) -> list[dict]:
    devices: list[dict] = []
    subset_from = 0

    while True:
        subset_to = subset_from + page_size
        payload = client.get(
            "/api/assets/devices",
            params={"subsetFrom": subset_from, "subsetTo": subset_to},
        )
        page = _normalize_devices_payload(payload)
        if not page:
            break
        devices.extend(page)
        if len(page) < page_size:
            break
        subset_from += page_size

    return devices


def _root_zone(device: dict) -> dict:
    description = device.get("deviceDescription")
    if not isinstance(description, dict):
        return {}
    zone = description.get("zone")
    return zone if isinstance(zone, dict) else {}


def _extract_coordinates(device: dict) -> tuple[float, float] | None:
    zone = _root_zone(device)
    attrs = zone.get("attributes")
    if not isinstance(attrs, dict):
        return None
    location = attrs.get("location")
    if not isinstance(location, dict):
        return None
    coordinates = location.get("coordinates")
    if not isinstance(coordinates, dict):
        return None

    lat = coordinates.get("lat")
    lon = coordinates.get("lon")
    if lat is None or lon is None:
        return None

    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def _extract_location(device: dict) -> str:
    zone = _root_zone(device)
    attrs = zone.get("attributes")
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

    return ", ".join(parts) if parts else "N/A"


def _extract_root_state_value(device: dict, state_name: str) -> str:
    zone = _root_zone(device)
    state = zone.get("state")
    if not isinstance(state, dict):
        return "N/A"
    node = state.get(state_name)
    if not isinstance(node, dict):
        return "N/A"
    value = node.get("value")
    return str(value) if value is not None else "N/A"


def _derive_operational_status(device: dict) -> str:
    activation = _extract_root_state_value(device, "activation").upper()
    connection = _extract_root_state_value(device, "connection").upper()

    if activation in {"ACTIVE", "PENDING"} and connection == "CONNECTED":
        return "OPERATIONAL"
    if activation in {"ACTIVE", "PENDING"} and connection == "DISCONNECTED":
        return "ACTIVE_BUT_OFFLINE"
    if activation == "MAINTENANCE":
        return "MAINTENANCE"
    if activation == "BLOCKED":
        return "BLOCKED"
    if activation in {"INACTIVE", "ARCHIVED", "PLAN"}:
        return activation
    return "UNKNOWN"


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
        devices = _fetch_all_devices(page_size=200)
    except PMDClientError as exc:
        return f"Error: unable to retrieve locker list (HTTP {exc.status_code})."

    nearby = []
    for device in devices:
        coords = _extract_coordinates(device)
        if coords is None:
            continue

        dev_lat, dev_lon = coords

        distance = _haversine_km(latitude, longitude, dev_lat, dev_lon)
        if distance <= radius_km:
            code = device.get("id") or "N/A"
            name = device.get("name") or code
            mode = str((device.get("deviceDescription") or {}).get("mode") or "N/A")
            activation = _extract_root_state_value(device, "activation")
            connection = _extract_root_state_value(device, "connection")
            status = _derive_operational_status(device)
            address_str = _extract_location(device)

            nearby.append({
                "code": code,
                "name": name,
                "status": status,
                "activation": activation,
                "connection": connection,
                "mode": mode,
                "address": address_str,
                "distance_km": round(distance, 2),
            })

    nearby.sort(key=lambda x: x["distance_km"])

    if not nearby:
        return f"No lockers found within {radius_km} km of ({latitude}, {longitude})."

    lines = [f"Found {len(nearby)} locker(s) within {radius_km} km:"]
    for loc in nearby:
        lines.append(
            f"- {loc['name']} ({loc['code']}) - {loc['status']} "
            f"[mode={loc['mode']}, activation={loc['activation']}, connection={loc['connection']}] - "
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
