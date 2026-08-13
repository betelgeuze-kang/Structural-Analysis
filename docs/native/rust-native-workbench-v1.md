# Rust-native Workbench v1

This slice closes a bounded C5 product workflow in a native terminal application. It does not
claim that the existing React/TypeScript Workbench has been removed, nor does it close general
desktop GUI, general MGT coverage, live commercial-solver execution, ROCm packaging, or C6
decommission.

## Owned flow

`structural-workbench` calls the Rust product libraries directly. It does not spawn
`structural-cli`, Python, Node, a browser, or an external PDF renderer. The implemented profile is
the exact fixed-guided one-story frame3d global-X `ModelIR` NDTHA slice. It accepts either strict
ModelIR or the exact numeric frame MGT profile normalized by the Rust importer:

1. `Import` strictly parses and canonicalizes ModelIR, the analysis request, and a language-neutral
   external-result contract. For MGT, the original MGT bytes, import-health diagnostics, C++
   validation/snapshot and the MGT import receipt are retained alongside the normalized ModelIR.
   Original input bytes, external source bytes, and all hashes remain in an immutable import
   directory.
2. `Validate` crosses Rust -> C ABI -> C++ and publishes the semantic validation report and
   canonical snapshot only when the model is contract-valid and analysis-ready.
3. `Run` advances a real bounded native solve and must publish a nonterminal checkpoint.
4. `Resume` verifies the exact model/request/checkpoint identities and reaches a terminal ResultIR,
   ReportIR, and Markdown document source.
5. `Compare` verifies the external source/executable hashes and publishes passed or diverged
   evidence without erasing divergence.
6. `Report` re-verifies the terminal projections and renders the deterministic native PDF.
7. `Inspect` projects a self-hashed operator view from the verified stage chain. `Review` records
   one immutable explicit human `pass`/`review`/`fail` disposition that is hash-bound to the exact
   session, ResultIR, comparison IR, and PDF; it is never inferred from a successful run or
   comparison. `Export` emits a self-hashed handoff manifest for those exact relative artifacts.
8. `Catalog` browses the native-owned language-neutral benchmark catalog without executing its
   acquisition or runner strings. `Evidence` verifies and browses only a copied evidence bundle;
   it never reads protected source evidence or generates a readiness verdict.

Every stage is an atomically renamed directory with a self-hashed receipt and complete artifact
inventory. `workbench-session.json` contains no machine-specific paths. On open, the Workbench
verifies all prior inventories and reconciles a valid stage directory that was durably published
before a process died while replacing the session file. A stage gap, tampered artifact, symlink,
invalid transition, or future session without matching artifacts fails closed.

## Commands

```text
structural-workbench import MODEL.json MODEL-REQUEST.json \
  --external-result EXTERNAL.json --source-artifact SOURCE \
  --workspace SESSION
structural-workbench import-mgt SOURCE.mgt MGT-MODEL-REQUEST.json \
  --model-id MODEL-ID --external-result EXTERNAL.json \
  --source-artifact SOURCE --workspace SESSION
structural-workbench validate --workspace SESSION
structural-workbench run --workspace SESSION --step-budget 1
structural-workbench resume --workspace SESSION
structural-workbench compare --workspace SESSION --require-pass
structural-workbench report --workspace SESSION
structural-workbench status --workspace SESSION
structural-workbench inspect --workspace SESSION
structural-workbench review --workspace SESSION --decision review \
  --reviewer "Engineer A" --comment "Check connection assumptions."
structural-workbench review-show --workspace SESSION
structural-workbench export --workspace SESSION
structural-workbench catalog --truth geometry_only --size large
structural-workbench catalog-show --case peer_spd_rc_column_rectangular_seed_01
structural-workbench evidence --bundle EVIDENCE-DIR --as-of-unix 1786579200
structural-workbench evidence-show --bundle EVIDENCE-DIR \
  --artifact product_readiness --as-of-unix 1786579200
```

`interactive` advances the same durable state machine one action at a time. `workflow` is the
headless clean-machine form and performs the complete sequence; `workflow-mgt` does the same from
original MGT bytes. Run must stop before the terminal step so Resume is a real checkpoint
transition; the current fixtures use a budget of one.

The review is deliberately immutable. Revising a disposition requires a new Workbench session
instead of silently overwriting history. Reviewer and comment text are bounded and reject terminal
control characters. The export is a manifest, not a signature or archive; the listed PDF and JSON
files remain independently verifiable product artifacts.

Catalog outputs preserve the legacy lifecycle and comparability rules, reject duplicate IDs and
unknown fields, and are canonical self-hashed JSON. Evidence paths must be relative beneath a real
non-symlink bundle directory; every artifact is bounded and must match the manifest SHA-256. An
explicit `--as-of-unix` makes the 21-day freshness calculation reproducible. Without it,
timestamp-only freshness is `unknown`, while an explicit stale signal remains stale.

The separately packaged `structural-evidence` Rust binary now owns evidence-bundle `check` and
`build`. Its embedded language-neutral source map replaces the former Node source list. It requires
one lowercase source commit across all strict JSON inputs, rejects sensitive-data signals and
symlinks, preserves exact source bytes, refuses to replace an existing output, and emits a
self-hashed deterministic build receipt. The npm command is a compatibility wrapper only.

The separately packaged `structural-catalog` Rust binary likewise owns benchmark-catalog `check`
and `build`. Its language-neutral source map freezes the two input directories and ordered
first-target rules. It reads strict bounded metadata, reproduces the prior 26 case projections,
never fetches a URL or executes an acquisition/runner string, preserves every unverified field,
and emits a self-hashed deterministic build receipt. The legacy npm command is a wrapper only.

The integration test clears the child environment, executes each stage in a new process, restores
the pre-Run session after the atomic checkpoint publication to model a crash window, resumes, and
then compares all 29 ModelIR-flow files against a second one-shot workflow byte for byte. The MGT
variant performs the same proof over 34 files and re-runs deterministic import plus C++ validation
on every reopen; source or evidence tampering and blocked import health fail before a stage can
advance. The tests also freeze the terminal ResultIR and PDF hashes and prove invalid ordering and
imported-input tamper rejection. A separate clean-process test publishes the same explicit review
in two workspaces, proves byte-identical inspect/review/export JSON, verifies that a passed external
comparison does not infer the human decision, blocks review overwrite, and rejects a one-byte
review mutation on reopen. Catalog/evidence E2E repeats byte-identically in a cleared environment,
freezes conservative ready/blocked/unavailable projections, verifies self-hashes, and rejects
evidence checksum tampering.

## Claim boundary

This is a terminal-native operator surface for one bounded product profile. It now owns a
deterministic results summary, explicit human review and handoff export for that profile, but it is
not a general visual model editor and does not yet replace all React/TypeScript UI behavior. General
MGT grammar/encoding and user-directed analysis selection, arbitrary ModelIR topology,
modal/static/sparse Workbench profiles, live MIDAS/OpenSees/CalculiX execution, device selection,
accessibility/localization, broader language-neutral fixture/oracle ownership, protected HIP C2
receipts, and final Python/Node C6 removal remain open.
The exact ModelIR and MGT flows do run from the separately verified native install/update/rollback
packages.

The same terminal entrypoint now owns the active CPU-only on-prem container contract. React Pages
and the Python project-ops image are rollback-only archives, but React/TypeScript source and broader
GUI behavior remain open as stated above. See `docs/native/deployment-cutover-v1.md`.
