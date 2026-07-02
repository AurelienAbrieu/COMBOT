"""Tools for locating accessible lockers/devices (Carrier Operation Manager)."""

from strands import tool

from .pmd_client import PMDClientError, client


def _normalize_tracking_device_payload(payload: object) -> tuple[list[dict], int | None]:
    if not isinstance(payload, dict):
        return [], None

    data = payload.get("data")
    if not isinstance(data, list):
        return [], payload.get("total") if isinstance(payload.get("total"), int) else None

    items = [item for item in data if isinstance(item, dict)]
    total = payload.get("total")
    return items, total if isinstance(total, int) else None


def _normalize_statuses(statuses: str) -> list[str]:
    values = []
    for raw_value in (statuses or "").split(","):
        normalized = raw_value.strip().upper()
        if normalized:
            values.append(normalized)
    return values


def _search_tracking_devices(
    city: str | None,
    latitude: float | None,
    longitude: float | None,
    radius_km: float,
    statuses: list[str],
    limit: int,
) -> tuple[list[dict], int | None]:
    params: dict[str, object] = {"from": 0, "size": limit}

    if statuses:
        params["fterms_attributes.status"] = ",".join(statuses)

    if city:
        params["fterms_attributes.site.city"] = city
    elif latitude is not None and longitude is not None:
        params["fgeo_attributes.site.coordinates"] = f"{latitude},{longitude}_{radius_km}_km"

    payload = client.get("/api/tracking-device/devices", params=params)
    return _normalize_tracking_device_payload(payload)


def _device_attributes(hit: dict) -> dict:
    source = hit.get("_source")
    if not isinstance(source, dict):
        return {}
    attributes = source.get("attributes")
    return attributes if isinstance(attributes, dict) else {}


def _site_details(attributes: dict) -> dict:
    site = attributes.get("site")
    return site if isinstance(site, dict) else {}


def _format_site_location(site: dict) -> str:
    parts: list[str] = []
    for key in ("name", "address", "city", "postCode", "country"):
        value = site.get(key)
        if isinstance(value, list):
            parts.extend(str(item).strip() for item in value if str(item).strip())
            continue
        if value and str(value).strip():
            parts.append(str(value).strip())
    return ", ".join(parts) if parts else "N/A"


def _format_distance(hit: dict) -> str | None:
    sort_values = hit.get("sort")
    if not isinstance(sort_values, list) or not sort_values:
        return None

    distance = sort_values[0]
    try:
        return f"{float(distance):.2f} km"
    except (TypeError, ValueError):
        return None


def _format_device_line(hit: dict, include_distance: bool) -> str:
    attributes = _device_attributes(hit)
    site = _site_details(attributes)
    device_id = str(attributes.get("id") or "N/A")
    status = str(attributes.get("status") or "N/A")
    generation = str(attributes.get("generation") or "N/A")
    install_type = str(attributes.get("installType") or "N/A")
    usage = str(attributes.get("usage") or "N/A")
    location = _format_site_location(site)

    details = [
        f"status={status}",
        f"generation={generation}",
        f"installType={install_type}",
        f"usage={usage}",
        f"site={location}",
    ]

    if include_distance:
        distance = _format_distance(hit)
        if distance is not None:
            details.append(f"distance={distance}")

    return f"- {device_id} [{', '.join(details)}]"


@tool
def find_nearby_lockers(
    city: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
    radius_km: float = 5.0,
    statuses: str = "",
    limit: int = 10,
) -> str:
    """List accessible lockers/devices, optionally filtered by area and status.

    Uses the tracking-device/device-view API, which already enforces the current user's
    access scope. If city is provided, filtering is delegated to the API with exact city matching.
    Otherwise, if latitude/longitude are provided, the search is restricted to SITE-based devices
    around those coordinates. If statuses are provided, filtering is delegated to the API.

    Args:
        city: Optional city name (for example "London").
        latitude: Optional GPS latitude.
        longitude: Optional GPS longitude.
        radius_km: Search radius in kilometers when coordinates are provided.
        statuses: Optional comma-separated statuses such as "ACTIVE,MAINTENANCE".
        limit: Maximum number of devices to return (default 10).

    Returns:
        A text list of accessible devices, optionally constrained by status and/or location.
    """
    city_filter = city.strip()
    use_city_filter = bool(city_filter)

    if not use_city_filter and (latitude is None) != (longitude is None):
        return "Error: latitude and longitude must be provided together."
    if not use_city_filter and latitude is not None and not (-90 <= latitude <= 90):
        return "Error: latitude must be between -90 and 90."
    if not use_city_filter and longitude is not None and not (-180 <= longitude <= 180):
        return "Error: longitude must be between -180 and 180."
    if not use_city_filter and radius_km <= 0:
        return "Error: radius_km must be greater than 0."
    if limit <= 0:
        return "Error: limit must be greater than 0."

    normalized_statuses = _normalize_statuses(statuses)
    if statuses and not normalized_statuses:
        return "Error: statuses must contain at least one non-empty value."

    try:
        devices, total = _search_tracking_devices(
            city=city_filter if use_city_filter else None,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            statuses=normalized_statuses,
            limit=limit,
        )
    except PMDClientError as exc:
        return f"Error: unable to retrieve accessible devices (HTTP {exc.status_code})."

    if not devices:
        if use_city_filter:
            return f"No accessible devices found in city: {city_filter}."
        if latitude is not None and longitude is not None:
            return f"No accessible devices found within {radius_km} km of ({latitude}, {longitude})."
        if normalized_statuses:
            return f"No accessible devices found for statuses: {', '.join(normalized_statuses)}."
        return "No accessible devices found."

    filters: list[str] = []
    if normalized_statuses:
        filters.append(f"statuses={','.join(normalized_statuses)}")
    if use_city_filter:
        filters.append(f"city={city_filter}")
    elif latitude is not None and longitude is not None:
        filters.append(f"within={radius_km}km around ({latitude}, {longitude})")

    header = f"Found {len(devices)} accessible device(s)"
    if total is not None:
        header += f" (total={total})"
    if filters:
        header += f" with {'; '.join(filters)}"
    header += ":"

    lines = [header]
    include_distance = (not use_city_filter) and latitude is not None and longitude is not None
    for device in devices:
        lines.append(_format_device_line(device, include_distance=include_distance))

    return "\n".join(lines)
