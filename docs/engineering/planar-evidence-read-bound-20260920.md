# Bound evidence reads before allocating their payload

The shared planar concrete comparison reader previously called `read_bytes()` before enforcing the JSON byte limit. A file exceeding the declared limit could therefore consume memory before being rejected.

The reader now validates the limit, obtains the size from the opened file descriptor, rejects empty or oversized files before reading their payload, and reads at most that size plus one byte. A changed read length is rejected. SHA-256 and strict JSON checks still apply to the bytes read, including duplicate-key rejection. This is a payload-size bound, not a bound on memory consumed by decoded Python objects.

Focused validation: 65 tests pass in 2.01 s; Ruff and `git diff --check` pass. The new checks cover an oversized file whose reader must never execute, invalid limits before opening a file, an exact-size boundary, and stale size metadata in both directions.

The active 1,024-layer numerical run and its comparison use their frozen `4d47f89ee670c7a3153fa3129218cd237b6f365d` driver snapshot. This local repair does not alter that snapshot, restart the solver, or qualify its still-pending numerical result. No solver tolerance, comparison screen, or public API changes.
