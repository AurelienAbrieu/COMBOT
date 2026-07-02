# Asset Manager Device Endpoint Knowledge Base

## Scope
This knowledge base documents the PMD Asset Manager contract for `GET /api/assets/devices/{id}` and the related device schemas under:
- `.../app/schemas/swagger.yaml`
- `.../app/schemas/v1/device/*.json`

It is intended to avoid repeated reverse-engineering and to keep COMBOT tools aligned with the real API model.

## Endpoint Contract: GET /api/assets/devices/{id}
Source: `swagger.yaml`.

### Method and path
- Method: `GET`
- Path: `/api/assets/devices/{id}`

### Parameters
- Path:
  - `id` (string, required): device identifier.
- Query:
  - `withStateEvent` (boolean, optional, default `true`): include state events in payload.
  - `cache` (boolean, optional): use cache when available.

### Response (important caveat)
Swagger currently describes `200` as an **array of** `device.v1.json` items, even for lookup by ID.

Practical implication for client code:
- Accept both list and object payloads.
- If list, use first object entry as the device record.

### Error responses
- `404`: device not found.
- `500`: internal server error.

## Canonical Device Structure
Primary schema: `v1/device/device.v1.json`

Top-level fields commonly relevant to status:
- `id`
- `name`
- `generation` (enum `1`..`8`)
- `installType` (`INDOOR`, `OUTDOOR`)
- `deviceDescription`
  - `mode` (`CARRIER_RETAIL`, `RESIDENT`)
  - `features` (booleans)
  - `monitoring` (booleans)
  - `zone` (recursive zone tree, schema `zone.v1.json`)

## Zone Tree Model
Schema: `v1/device/zone.v1.json`

The device status is mostly represented through the root zone and child zones:
- recursive child list in `zone` property
- each node has `type`, `subtype`, `path`, and optional `state`
- box-level operational data is usually in zones where `type == BOX`

## Zone State Model
Schema: `v1/device/zone-state.v1.json`

Important state keys:
- `activation`
- `connection`
- `door`
- `hard`
- `filling`
- `available`
- `securityBreach`
- `cleanliness`
- `battery`
- `printer`

Each state generally follows:
- `value`
- `timestamp`

Note: `activation` value has a strict enum in `zone-state.v1.json`:
- `ACTIVE`, `INACTIVE`, `PLAN`, `BLOCKED`, `ARCHIVED`, `MAINTENANCE`

## Event Schemas and Value Domains
Device event schemas under `v1/device/*-state-event.v1.json` provide state value domains.

### Activation
- `ACTIVE`, `INACTIVE`, `PLAN`, `PENDING`, `MAINTENANCE`

### Connection
- `CONNECTED`, `DISCONNECTED`

### Door
- `OPENED`, `CLOSED`

### Hard
- `OPERATIONAL`, `DAMAGED`

### Filling
- `FULL`, `EMPTY`, `ERROR`

### Available
- event payload `value` is **boolean**.

### Cleanliness
- `SOILED`, `CLEANED`

### Security breach
- `NONE`, `DOORBLOCKED`, `BOXFULL`, `BOXFULLDOORBLOCKED`, `BURGLARY`, `BOXFULLBURGLARY`, `DOORBLOCKEDBURGLARY`, `BOXFULLDOORBLOCKEDBURGLARY`

### Battery
- event payload value is a string percentage-like value (`0..100` pattern).

### Source enum
- `MANAGER`, `DEVICE`

## Known Modeling Inconsistencies
These are critical for robust client parsing:

1. GET by ID modeled as array
- Swagger response schema for `/api/assets/devices/{id}` is array, despite semantic singular lookup.
- Tools must normalize list/object responses.

2. `available` typing mismatch
- `available-state-event.v1.json` defines `value` as boolean.
- `zone-state.value.v1.json` defines generic state `value` as string.
- Consumers should accept both bool and string forms (`true`/`false`, `EMPTY`/`FULL`, etc.).

3. Status location mismatch vs legacy assumptions
- Locker status is not a top-level `status` field in this contract.
- Operational status must be derived from zone states (root and boxes), especially `activation`, `connection`, `hard`, `filling`, and `securityBreach`.

4. Address/location location mismatch vs legacy assumptions
- Address is usually under `deviceDescription.zone.attributes.location`, not top-level `address`.

## COMBOT Tooling Guidance

### Principles
- Use `/api/assets/devices/{id}` as the source of truth for locker/device status.
- Use `/api/parcel_events_in_devices/{deviceCode}/boxView` as the source of truth for parcel occupancy in boxes (see `docs/parcel-events-in-devices-boxview-kb.md`).
- Do not perform implicit fallback to unrelated endpoints when this endpoint fails or is empty.
- Derive status from schema-backed fields only.

### Exposed read-only tools
1. `get_locker_status(device_id)`
- Human summary from `/api/assets/devices/{id}`.
- Includes core identity, mode/install type, root activation/connection, and box aggregates.

2. `get_locker_zone_status(device_id, zone_path)`
- Detailed state view for one exact zone path.
- Useful for troubleshooting one box/module.

3. `get_locker_device_snapshot(device_id)`
- Compact JSON snapshot for technical diagnostics.
- Good for advanced LLM reasoning without full payload dumping.

## Tool Pertinence Matrix (post-status refactor)

### Locker/device tools
1. `get_locker_status`
- Pertinent as first-line operational summary.
- Uses only `/api/assets/devices/{id}` and schema-backed derivation.

2. `get_locker_zone_status`
- Pertinent for troubleshooting one exact box/module zone.
- Complements global locker status when user asks "why blocked" or "which box".

3. `get_locker_device_snapshot`
- Pertinent for technical support and low-level diagnostics.
- Avoids free-form hallucination by returning compact structured JSON.

4. `find_nearby_lockers`
- Still pertinent after status enrichment.
- Different user intent: geo search and candidate selection, not device deep-dive.
- Must rely on root zone location coordinates (`deviceDescription.zone.attributes.location.coordinates`) and root state, not legacy top-level `address/status`.

### Parcel/pickup/courier/report tools
1. `search_parcels`
- Pertinent: searches parcels by device ID(s), status filter, or tracking number via `/api/tracking-parcel/parcels`.

2. `view_pickup_code` and `resend_pickup_code`
- Pertinent: recipient support operations, not overlapping with device status.

3. `add_courier` and `remove_courier`
- Pertinent: carrier management actions; keep explicit confirmation flow.

4. `generate_report`
- Pertinent: operational KPI/reporting workflow, complementary to real-time status.

## Status Derivation Heuristics in COMBOT (device-state scope)
For device-state interpretation from `/api/assets/devices/{id}`, current implementation uses schema-safe heuristics:
- Available vs occupied: based on `available` bool-ish value, then fallback to `filling` (`EMPTY`/`FULL`).
- Blocked/restricted count: box activation in `{BLOCKED, INACTIVE, MAINTENANCE, ARCHIVED}` or non-`NONE` security breach.
- Damaged count: box `hard == DAMAGED`.

For parcel-in-box occupancy, follow the dedicated `boxView` KB in `docs/parcel-events-in-devices-boxview-kb.md`.

## Maintenance Checklist
When PMD schemas change:
1. Recheck `swagger.yaml` for `/api/assets/devices/{id}` response shape and params.
2. Recheck `device.v1.json`, `zone.v1.json`, `zone-state.v1.json`.
3. Recheck all `*-state-event.v1.json` enums for value domain changes.
4. Update COMBOT tools and this KB in the same commit.
5. Ensure `agent.py` tool selection hints are still aligned with registered tools.

## Last analysis date
- 2026-06-12
