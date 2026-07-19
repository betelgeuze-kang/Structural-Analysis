# Viewer runtime-ingest payload storage

> Status: local stacked implementation candidate. This document does not mark
> PR #102 ready, merged, or closed.

## Scope

`viewer-runtime-ingest-payload-storage.js` owns the browser-session copy of a
validated renderable evidence-ingest payload. It replaces direct
`JSON.parse`/`JSON.stringify` calls against the runtime-ingest `sessionStorage`
key while leaving unrelated viewer preference keys on their existing helper.

The controller retains a detached, deeply frozen in-memory copy. A storage
failure therefore cannot discard a payload that already passed the runtime
contract. It also never includes the raw payload, browser exception text, or
storage value in a receipt.

## Validation boundary

Every write and every stored read checks, in order:

1. the exact outer schema version and payload object shape;
2. the declared payload kind against the detected renderable shape;
3. non-negative integer node, element, and segment counts;
4. declared counts against counts derived from the payload;
5. the existing evidence-ingest node, element, segment, and UTF-8 byte limits;
6. a JSON serialize/parse round trip before the in-memory copy becomes current.

Malformed, invalid, or non-text stored entries are rejected and removed on a
best-effort basis. Removal failure is reported separately from the primary
validation failure.

## User-visible persistence states

| Display status | Meaning |
|---|---|
| `Saved locally` | The current payload is validated in memory and written to browser session storage. |
| `Session-only` | The current payload is validated and retained in memory, but the storage write failed. |
| `Storage unavailable` | No usable in-memory payload exists and storage cannot be read or repaired. |
| `Previous state retained` | A replacement payload failed validation or serialization; the prior validated in-memory payload remains current. |

The report panel exposes the display status plus stable `status`,
`persistence`, `error_code`, and `error_path` data attributes. The latest
sanitized receipt is also available as
`window.__STRUCTURE_VIEWER_RUNTIME_INGEST_STORAGE_STATUS__` for browser probes.

## Stable failure receipts

The storage adapter classifies quota, security, and generic get/set/remove
failures without preserving raw exception messages. Payload validation uses
stable contract paths under `/payload`; stored-value failures use
`/storage/value`; adapter failures use `/storage/<operation>`.

Receipts follow `structure_viewer_runtime_ingest_payload_storage_v1` and include
separate cleanup error fields so a failed corrupted-entry removal cannot mask
the original reason the entry was rejected.

## Verification and PR #102 boundary

`tests/test_structure_viewer_runtime_ingest_payload_storage.py` exercises direct
and interactive payloads, byte/count validation, detached immutable memory,
reload, quota/security failures, malformed and invalid stored JSON, cleanup
failure, stable public metadata, secret non-disclosure, viewer wiring, and all
four report-panel states.

`runtime-input-viewer-ci.yml` owns the Python contract and JavaScript syntax
check, while the frontend build contract requires the storage module to exist.

PR #102 still requires its own exact-head CI, human review, and removal of its
temporary diagnostic workflow before its draft state or closure can change.
This local stacked implementation provides no remote receipt for those gates.
