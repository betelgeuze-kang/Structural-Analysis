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
```

`interactive` advances the same durable state machine one action at a time. `workflow` is the
headless clean-machine form and performs the complete sequence; `workflow-mgt` does the same from
original MGT bytes. Run must stop before the terminal step so Resume is a real checkpoint
transition; the current fixtures use a budget of one.

The integration test clears the child environment, executes each stage in a new process, restores
the pre-Run session after the atomic checkpoint publication to model a crash window, resumes, and
then compares all 29 ModelIR-flow files against a second one-shot workflow byte for byte. The MGT
variant performs the same proof over 34 files and re-runs deterministic import plus C++ validation
on every reopen; source or evidence tampering and blocked import health fail before a stage can
advance. The tests also freeze the terminal ResultIR and PDF hashes and prove invalid ordering and
imported-input tamper rejection.

## Claim boundary

This is a terminal-native operator surface for one bounded product profile. It is not a general
visual model editor or results viewer and does not yet replace all React/TypeScript UI behavior.
General MGT grammar/encoding and user-directed analysis selection, arbitrary ModelIR topology,
modal/static/sparse Workbench profiles, live MIDAS/OpenSees/CalculiX execution, device selection,
accessibility/localization, protected HIP C2 receipts, and final Python/Node C6 removal remain open.
The exact ModelIR and MGT flows do run from the separately verified native install/update/rollback
packages.
