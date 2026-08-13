# Rust-native Workbench evidence bundle v1

`structural-evidence` owns the bounded evidence-bundle build path formerly implemented by Node. Its
source inventory is the language-neutral
`native/evidence/workbench-evidence-sources-v1.json` contract. The binary has two commands:

```bash
structural-evidence check --root SOURCE-ROOT
structural-evidence build --root SOURCE-ROOT --out OUTPUT-DIR \
  --generated-at 2026-08-13T00:00:00Z
```

`check` performs no writes. `build` accepts the same verified inputs, copies their exact bytes into
a new staging directory, writes `workbench-evidence-manifest.v1`, fsyncs the files and directories,
and publishes by one rename. Existing output is never deleted or replaced. The explicit RFC 3339
timestamp makes repeated builds byte-identical.

The repository compatibility wrapper accepts either no arguments for a build or exactly `--check`
for a read-only consistency check. Unknown arguments fail closed, and a build refuses an existing
`public/evidence` destination rather than deleting or replacing previously published bytes.

Both commands require strict UTF-8 JSON, one exact lowercase 40- or 64-digit source commit, bounded
regular non-symlink files, unique safe source and bundle paths, and a passing conservative
sensitive-data scan. Email-like values, credit-card-like digit sequences and secret-bearing key
names fail closed. Outputs are self-hashed
`structural-native-evidence-bundle-build-receipt.v1` JSON and never infer readiness or approval.

The distribution E2E runs the installed binary with an empty PATH against synthetic
language-neutral sources, builds a bundle, browses it with `structural-workbench evidence`, and
binds all three builder receipt/manifest identities into the append-only v5 distribution receipt.
Actual protected productization evidence is not read by unit or hosted distribution tests.
