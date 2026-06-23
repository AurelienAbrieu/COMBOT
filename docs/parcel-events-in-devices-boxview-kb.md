# Parcel Events In Devices - boxView Knowledge Base

## Scope
This document describes how to use `GET /api/parcel_events_in_devices/{deviceCode}/boxView`
as the source of truth for parcel occupation inside locker boxes.

It is based on source code and contract tests from:
- `C:/VSProj/Packcity/quadient-pls/packcity/pmd-core/parcel/parcel-cqrs-device-query/app/api/http/server/parcel-events-in-devices.js`
- `C:/VSProj/Packcity/quadient-pls/packcity/pmd-core/parcel/parcel-cqrs-device-query/app/service/box-view.js`
- `C:/VSProj/Packcity/quadient-pls/packcity/pmd-core/parcel/parcel-cqrs-device-query/app/api/lib/events.js`
- `C:/VSProj/Packcity/quadient-pls/packcity/pmd-core/parcel/parcel-cqrs-device-query/tests/contracts/parcel_in_device_by_box.feature`

## Endpoint Contract

### Method and path
- Method: `GET`
- Path (gateway): `/api/parcel_events_in_devices/{deviceCode}/boxView`
- Path (service direct): `/v1/parcel_events_in_devices/{deviceCode}/boxView`

### Parameters
- Path:
  - `deviceCode` (string, required): locker/device identifier.

### Authentication and authorization
- A JWT organization context is evaluated server-side.
- If the organization has no rights on the device, response is `403`.
- If user context is logistician-scoped, visibility is partially masked (details below).

## Response Shape
Top-level payload:
- `boxes`: array

Each element in `boxes` can be:
1. A physical box group:
- `boxPath`: string
- `parcels`: array

2. An announced-only group (no allocated box yet):
- no `boxPath`
- `parcels`: array of announced parcels (typically `EXPINI`)

Common parcel fields (when visible):
- `status`, `statusDate`
- `parcelId`, `parcelNumber`, `parcelBarcode`
- `code`, `name` (logistician)
- `contact`
- `boxPath`
- `boxRequested`, `boxAllocated`
- `deliveryDate`, `unloadDate`
- `expiryDate`, `validityDate`

## Behavioral Rules From Source Code

### 1) Grouping rule
- The service groups data by parcel first, then aggregates by `boxPath`.
- One `boxes[]` entry is created per distinct `boxPath`.
- Parcels without `boxPath` are grouped in a special entry without `boxPath`.

### 2) Event ordering and parcel projection
- Events are sorted with these rules:
  - `EXPINI` forced first.
  - then by event timestamp ascending.
- Parcel projection is built by scanning the ordered events and keeping latest known values for fields.

### 3) Status derivation
- `EXPUPD` and `REMIND` do not become current status.
- Current status is derived from event history excluding those technical updates.
- Special case:
  - if computed status is `LIVEXP` and `expiryDate` is still in the future, status is rewritten to `LIVCFP`.

### 4) Logistician masking behavior
For organization contexts that resolve to a logistician code:
- if parcel logistician code matches caller code: full parcel details are returned.
- if it does not match: payload returns only `{ "status": "..." }` for that parcel.

Important implication:
- the endpoint can still be used to estimate occupation by status,
  even when parcel identity fields are masked.

### 5) End-of-life remnants
- `boxView` is not strictly "currently occupied only".
- Depending on event history and cleanup timing, parcels with statuses such as `COLCFM` or `ENDCFP` can still appear.
- Cleanup/purge flows remove historical remnants later.

## Recommended Occupancy Interpretation For COMBOT
To answer "which boxes are occupied by parcels now":

1. Fetch `boxView`.
2. Ignore entries without `boxPath` for physical occupancy counts.
3. For each `boxPath`, classify parcels with status in:
   - `LIVCFP`, `RETCFM`, `LIVBLK`, `LIVEXP`
4. A box is occupied if at least one parcel in that box is in those statuses.
5. Keep announced-only parcels separate from occupied-box metrics.

Rationale:
- This aligns with parcel-cqrs-device-query logic used by `availableFreeBoxes` service, where occupied statuses are `LIVCFP`, `RETCFM`, `LIVBLK`, `LIVEXP`.

## Integration Notes For COMBOT
- Use `boxView` as source of truth for parcel occupation.
- Use `/api/assets/devices/{id}` for hardware/device state (activation, connection, damage, door, etc.).
- Do not add implicit fallback to unrelated endpoints when `boxView` is empty or fails.

## Practical Example
Request:
- `GET /api/parcel_events_in_devices/DEMO00002/boxView`

Interpretation pattern:
- Count distinct `boxPath` entries containing at least one parcel with status in occupied set.
- Report each occupied `boxPath` and visible parcel details when present.
- If details are masked, report at least status-based occupancy.

## Known Caveats
- `200` with `{"boxes": []}` is possible when no parcel events are currently stored.
- Mixed statuses may exist in the same box due to history remnants.
- Unannounced/announced-only parcels can appear without `boxPath`; do not treat them as occupying a physical box.

## Last analysis date
- 2026-06-12
