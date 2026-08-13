# Rust-native benchmark catalog v1

`structural-catalog` owns the bounded candidate-catalog build path formerly implemented by Node.
Its input inventory and ordered first-target selectors are the language-neutral
`native/catalog/benchmark-catalog-sources-v1.json` contract. The binary has two commands:

```bash
structural-catalog check --root SOURCE-ROOT --catalog CATALOG.json
structural-catalog build --root SOURCE-ROOT --out CATALOG.json \
  --generated-at 2026-08-13T00:00:00Z
```

`check` rebuilds the catalog in memory using the timestamp already recorded in the supplied file
and requires exact byte parity. `build` accepts an explicit RFC 3339 timestamp and atomically
replaces an absent or regular catalog file. Both commands read sorted bounded regular non-symlink
strict JSON only. Duplicate JSON keys, invalid checksums, duplicate case IDs, unsafe paths,
nonportable identifiers, oversized inputs, and output drift fail closed.

The current input is 21 collected open-data reports plus five PEER specimen snapshots. The Rust
projection preserves every prior case, order, first target, checksum, URL, truth boundary, and
verification field. License, truth, reference, and runner values remain unverified unless the
source explicitly supports them; no URL is fetched and no acquisition or runner command is
executed. The output remains a `benchmark-catalog.v2` candidate, not validation evidence.

Both commands emit canonical self-hashed
`structural-native-benchmark-catalog-build-receipt.v1` JSON. Receipts bind the source map, every
input byte, the output catalog, selected first targets, and explicit network/command counts of
zero. Cargo tests cover deterministic synthetic builds, strict negative cases, clean-environment
CLI output, and exact reproduction of the tracked 26-case catalog.

The repository compatibility wrapper accepts no arguments for a build or exactly `--check` for
the read-only parity gate. Unknown arguments fail closed. The installed static/shared distribution
E2E runs both modes under an empty `PATH` and binds the receipt/output hashes into the append-only
v6 distribution receipt.
