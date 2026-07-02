# Tracking Parcel /parcels Parsing KB (COMBOT)

## Scope
This document defines the only allowed source for parcel state in a locker:
- `GET /api/tracking-parcel/parcels?fterms_events.locker.deviceCode={DEVICE_CODE}`

For COMBOT:
- Parcel-state questions in a locker must use this endpoint.
- `boxView` is reserved for locker/device status context, not parcel-state listing logic.

## Canonical Query Pattern
Minimum request for one locker:
- `GET /api/tracking-parcel/parcels`
- Query params:
  - `fterms_events.locker.deviceCode={DEVICE_CODE}`
  - `size=100`
  - `from=0`
  - `nestedSearch=false`
  - `sortfield=current.event.occurredAt`
  - `sortorder=desc`

Optional status filter:
- `fterms_current.event.status={CSV_STATUSES}`

Delivered-in-locker filter (recommended for loaded parcels):
- `fterms_trackingEvent.status=LIVCFP`
- `fterms_trackingEvent.isInDevice=true`

Reason:
- some records can have `current.event.status` already moved to administrative or lifecycle states
  (for example `PINSEE`, `EXPINI`, `PURGE`) while `trackingEvent` still reflects the locker-loaded state.
- filtering only with `fterms_current.event.status=LIVCFP` can return 0 even when loaded parcels exist.

Examples:
- Delivered/loaded in locker:
  - `fterms_events.locker.deviceCode=DEMO00002`
  - `fterms_current.event.status=LIVCFP`
- Awaiting delivery (announced):
  - `fterms_events.locker.deviceCode=DEMO00002`
  - `fterms_current.event.status=EXPINI`

## Response Shape (Observed)
Top-level:
- `code`
- `data` (array)
- `from`, `size`, `total`, `totalPages`

Each item in `data`:
- `_source.attributes` (parcel identity, contact, logistician, dates)
- `_source.current.event` (current operational state)
- `_source.device` (device metadata)
- `_source.events` (history)

Important fields used by COMBOT:
- Status:
  - `_source.current.event.status`
- Phase:
  - `_source.current.event.phase`
- Device code:
  - `_source.current.event.locker.deviceCode` (fallback `_source.device.deviceCode`)
- Box details:
  - `_source.current.event.locker.boxAlias`
  - `_source.current.event.locker.boxAllocated.size`
- Parcel number/barcode:
  - `_source.attributes.parcelNumber`
  - `_source.attributes.parcelBarcode`
- Recipient:
  - `_source.attributes.contact.firstName`
  - `_source.attributes.contact.lastName`
- Logistician:
  - `_source.attributes.logistician.name`
  - `_source.attributes.logistician.code`
- Dates:
  - `_source.attributes.deliveryDate`
  - `_source.attributes.expirationDate`

## Parsing Rules in COMBOT
1. Use `_source.current.event` as primary event state.
2. For locker parcel-state listing, prefer `_source.trackingEvent` when present.
3. Use `_source.current.event` as fallback when `_source.trackingEvent` is absent.
4. Use `_source.current.event.locker` and `_source.device` as fallback sources for `deviceCode` and locker path details.
5. Use `_source.attributes` for contact, logistician, parcel identity, and delivery/expiration dates.
6. If status-filtered query returns empty:
- return empty result for that filter.
- do not silently switch endpoint.
- do not fabricate parcel list from `get_locker_status`.

## Status Semantics
- `EXPINI`: announced/shipped, not yet loaded into locker.
- `LIVCFP`: loaded in locker, ready for pickup.
- `RETCFM`, `LIVEXP`, `LIVBLK`: pickup/problem-oriented statuses.

## Common Pitfalls
1. Using `.keyword` query suffixes when the API expects non-keyword fields.
2. Parsing status from wrong node (`trackingEvent` only) and missing `_source.current.event`.
3. Interpreting occupancy summary as parcel list source.

## Operational Guidance
- For question: "what are the parcels delivered in DEMO00002?"
  - call `search_parcels(device_ids="DEMO00002", statuses="LIVCFP")`
  - parse from `/api/tracking-parcel/parcels` response only.

- For question: "do I have parcels to deliver?"
  - call `search_parcels(statuses="EXPINI", logistician=...)`
  - optionally constrain by device IDs if user asks per locker.

## Last update
- 2026-07-02
