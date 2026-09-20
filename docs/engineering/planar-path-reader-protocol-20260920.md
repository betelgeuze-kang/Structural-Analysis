# Bounded indexed-path verification

`read_path_artifacts` consumes the research writer's final index, an externally expected index hash and the original full-result hash. It verifies the full file by chunked hashing, decodes metadata and one step at a time, validates the forty targets, accepted flags, parent checkpoint chain and final checkpoint, and hashes a streamed reconstruction of the original JSON. Compact extracted results are returned only after the reconstructed bytes match the original full-file length and digest.

File names are fixed by role and ordinal; escaped paths, invalid sizes/digests, noninteger counts and unsupported index fields are rejected. JSON decoding retains duplicate-key and nonfinite-value rejection. Limits are 128 KiB for the index, 256 MiB for metadata and 512 MiB per step. The full file is capped at 32 GiB but is never decoded as one JSON object. These are file limits, not guarantees that decoded objects occupy the same number of bytes.

The extraction callback must be pure and retain only compact results. It runs before final full-byte verification; callers must not publish partial callback output. The intended material-field extractor retains a subset of values, not entire accepted steps. Original solver checks and the exploratory comparison screen remain unchanged.

Focused validation passes 85 tests in 2.29 s. Tests include complete forty-step traversal, changed parents/targets/final checkpoints, failed steps/paths, missing steps, boolean counts, altered full files, paths outside the fixed layout, duplicate keys, and step content rehashed into a changed index that still fails binding to the original full JSON. A weak-reference check confirms the previous decoded step dictionary is released before the next step read. Ruff and diff checks pass.

The [actual artifact round trip](planar-path-storage-protocol-20260920.md) is still running. The bounded reader has not yet received a measured full-size execution receipt. No memory or runtime improvement is claimed from these fixtures alone, and no new numerical refinement has begun.
