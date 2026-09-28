# Two-fixed portal span layout originals

`rc-portal-layout-span-artifacts.json.gz` preserves all **79 original JSON files** from the local geometry-varying portal layout runs: 42 under `staged/` and 37 under `full/`. It is a gzip-compressed, lexically sorted JSON map from `run/relative-path.json` to base64-encoded original file bytes. Compression used `gzip.GzipFile` with `filename=''`, `mtime=0`, and level 9. Decompression and base64 decoding were checked byte-for-byte against the producer packet. This fixture does not include the predeclared input files, source archive, or observer audit script.

| Scope | Value |
| --- | --- |
| Original JSON bytes, summed without packaging | 10,871,903 |
| SHA-256 of original byte tree | `9f4cd695244378eb7da37571a8de9be93f7727b0ba3165430b1f0ea9f3f855e4` |
| Uncompressed sorted base64-map bytes / SHA-256 | 14,500,346 / `f4d366c7fbb24b155eae0de14439c4bc38bcc8e94f7d25a97cb47a7222c9800e` |
| Gzip bytes / SHA-256 | 2,596,579 / `fc9c3ac52bf3cc233e8f07333b27b1f34f6fab414892097b5be6a2a395e16174` |
| Per-original manifest bytes / SHA-256 | 15,354 / `a7a152d37c7a8500b0b786215f5972f02f217e7b8ea405caa9771521837dd1de` |

The original byte-tree digest hashes the sorted entries concatenated as UTF-8 path, zero byte, unsigned 8-byte big-endian file length, and exact original bytes. The adjacent [per-original manifest](rc-portal-layout-span-manifest.json) retains all 79 relative paths, byte lengths, individual SHA-256 digests, new-input digests, and the aggregate checks without local absolute paths.

The producer used **exact code from source revision `e0146cd9b33fa7c02d2fd8a81ec31c177fb64dba`** plus four separately predeclared, byte-copied new input files. Those new inputs were not part of that revision. The staged run completed first (report hash `sha256:801f93241948deae1231421696b17377d74d6de04864e0cc0a10c66eceb23318`); a separate full run followed (report hash `sha256:2ab6c2bc13ae99e41b6d73830bf39e0020ee4f85c9a158afb62988c26af3a77d`). The staged plan left the longer-span candidate physically unknown after cost pruning; the later full run separately verified it. Workbench review of this fixture checks stored model, request, quantity, price, result, verification, work, and decision bindings without running a solver. The synthetic price table and broad development limits do not prove design suitability, quoted savings, independent physical validity, or runtime speedup.
