# Installed wheel layout CLI and original-record admission — 2026-09-13

A wheel built from clean source `15e7901d0d1ccae058359e2b4234eea88bc3554d` executed
price-order staged layout search outside the checkout. The imported package path
was inside its temporary virtual environment, with `PYTHONPATH` removed and user-site
packages disabled. This demonstrates the new module's packaged execution; it is
not an independent clean-machine or all-platform qualification.

## Artifact and environment

Wheel: `structural_analysis-0.3.0-py3-none-any.whl`, 1954538 bytes, SHA-256
`fa9fbc5f7c375d55f66e3590d266b8335ad337f783702d8f53530d4b86cd1ff9`.
All 463 hashed RECORD entries matched their sizes and hashes; all 320 packaged
Python source files matched the clean source tree. The observed package version is
unchanged; this artifact was built locally and was not published as a release.

The environment allowed system-site packages, so it is not fully isolated. Two
pre-execution import probes failed with missing `jsonschema`: the initial setup
used `--no-deps`; a subsequent dependency install saw user-site packages that the
execution environment deliberately hid. Wheel metadata already declared jsonschema
correctly. Installing its declared dependencies with the same `PYTHONNOUSERSITE=1`
setting resolved the mismatch. These harness failures are preserved; no numerical
path ran before their resolution. No product dependency declaration was altered.
The installed package/version list and installation logs are retained.

## Actual installed execution

Inputs were copied with SHA-256/length checks from the preserved `o0-staged` HTTP
export. Its complete five-model pool, six-target request, common synthetic prices
and limits were preserved. The CLI experiment maps candidate IDs to relative model
files and uses a two-target prefix with a five-model consideration budget.

The installed CLI returned success, selected `middle`, ran two full paths and two
prefix paths with separate verification, and recorded 32 attempted steps and 64
Newton/linear solves in eight API invocations. Standard output matched the persisted
runtime sidecar and its report identity. The enclosing process observation was
9.712619685 seconds, including interpreter startup/imports and CLI execution through
exit. Environment creation, installation, input preparation and subsequent admission
are excluded; this single observation is not a speed comparison.

The same installed wheel's HTTP artifact-bundle validator admitted all 52 original
records. Its solver entrypoints were replaced with failing stubs for admission,
confirming that this check performed no new solve. Bundle bytes equalled the saved
originals. The two full and two prefix response histories and terminal responses
matched the earlier preserved numerical observation exactly. This remains same-solver
comparison, not independent structural-physics validation. No HTTP server or browser
was exercised in this specific observation.

## Retention and remaining scope

Immutable evidence directory:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-layout-cli-wheel-sqm5jtac/evidence`.
86 files, 6761292 bytes; inventory SHA-256:
`d87792a7948f48f851676fb473576b197617050711cd375aba11427f2eb4d973`.
The mutable virtual environment is excluded; wheel, package list, commands, inputs,
outputs, probe failures and audit records are retained. The summary distinguishes
package integrity, numerical execution, admission and qualification flags.

Learned net benefit, independent physical evidence, complete repository CI and
release approval remain open. This is a price-order installed execution; the six
local CLI tests recorded separately cover both strategies and all execution modes.

## Exact-head repository CI observation

[Repository Python Tests run 34723974528](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34723974528)
collected tests successfully at the preceding published source
`dea625b1a023954a3c2f7a39168f9f55cddcdc6a`. All four full shards then failed evidence
materialization. Each terminal log independently reports
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. Their actual full test steps
were skipped; the aggregate failed. The separate development-contract job was still
running at capture. Its completion is not inferred. The accompanying summary records
job/step state and hashes of all four downloaded failure logs. No external receipt,
license gate or tolerance was changed to make this observation pass.
