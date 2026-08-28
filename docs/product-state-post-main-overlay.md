# Product State post-main overlay

`Nightly Full Quality` is the sole producer of the post-main generated-evidence
overlay. `Product State Current` consumes the attested artifact after the
Nightly run completes. The dependency direction is therefore:

```text
Nightly Full Quality -> Product State Current -> Current Main Evidence Index
```

Nightly must not consume Product State or the Evidence Index. This keeps the
workflow graph acyclic and avoids blessing tracked historical snapshots as
current-source evidence.

The overlay contains fresh runtime packaging, frontend dependency audit, PM
gate, action register, closure board, readiness snapshot, and roadmap leaves.
Its seal binds the exact source commit/tree, Nightly workflow blob, run and
attempt, every generated file, and the current technical handoff contract for
the medium, IFC, MGT 9/10, and Native lanes. The handoff lanes remain
`technical_only` and non-promoting. The carried external V&V receipts likewise
retain false legal, independent-operator, formal Level 2, commercial,
release-readiness, and release-authority claims.

The Product State workflow has three privilege domains:

1. `build-current-state` checks out and executes repository code without OIDC.
2. `attest-current-state` has OIDC but performs no checkout, dependency install,
   or repository-code execution. It validates the immutable artifact ID/digest,
   strict JSON, bounded ZIP profile, exact source/workflow identities, and
   non-promotion claims, then independently reverifies the nested Nightly
   overlay attestation before attesting the two Product State subjects.
3. `verify-current-state` uses a fresh exact-source checkout without OIDC to
   verify all three attestations and replay the overlay, full DAG, and
   provenance.

External receipt materialization is an exact allowlist, not a manifest-chosen
destination: each source receipt is bound to one overlay member and one fixed
`.ci/product-state-inputs/` target. Traversal, alternate safe-looking targets,
symlink ancestry, duplicate JSON keys, non-finite numbers, and unsafe archive
members fail closed.

## License metadata extension point

The overlay does not decide or infer software rights. License-policy changes
must continue to flow through
`artifacts/manifests/internal_license_due_diligence.current.v1.json` and the
Product State license contract. If the license work adds a new source-owned
schema or manifest that affects runtime/redistribution metadata, add its exact
Git blob identity to the overlay seal and provenance bundle, then update the
focused schema and privileged-handoff tests. Do not change
`external_vv_nonpromotion.promotion_eligible`, legal approval, redistribution
approval, or release authority to true without the separate rights-holder or
legal receipt.
