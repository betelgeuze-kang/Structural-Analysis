# Structural Frame Alpha CLI Distribution Candidate

This portable directory contains the bounded CPU-only `structural-cli`, one analysis-ready
ModelIR v2 example, the distribution/smoke, bounded external-comparison and loopback job-submission
schemas, the repository no-grant `LICENSE`, and `SBOM.native-license.json`.

It is a development candidate, not an installer or a released engineering product. It has no
code signature, vulnerability-clearance receipt, clean-machine receipt, operator-attached external
comparison receipt, PDF output, design authority, commercial authority, or release authority.

The root `LICENSE` is all-rights-reserved and grants no use, modification, distribution, or
commercial permission without a separate written agreement. The packaged SBOM proves only that
first-party Cargo metadata points to that exact notice and that locked dependency declarations meet
the repository's technical SPDX allowlist. Product-license approval, commercial redistribution,
and third-party redistribution clearance remain explicitly blocked; the SBOM is not legal advice.

The binary exposes `workstation serve` and this archive includes
`schemas/native_linear_frame3d_job_submission_v1.schema.json`, but the archive does not contain a
Workbench static build. A separately built source-tree `dist/` may be served on loopback for the
bounded same-origin submission/run flow; that is not a packaged Workbench or clean-machine receipt.

## Inspect and run the example

Linux:

~~~bash
./bin/structural-cli --version
./bin/structural-cli model validate examples/frame-alpha-cantilever.model-ir.json \
  --require-analysis-ready
./bin/structural-cli model analyze-frame3d \
  examples/frame-alpha-cantilever.model-ir.json \
  --load-pattern LC_WEAK \
  --result-id example.LC_WEAK \
  --report-id example.LC_WEAK.report \
  --output workbench-bundle \
  --output-dir output/example.LC_WEAK
~~~

Windows PowerShell:

~~~powershell
.\bin\structural-cli.exe --version
.\bin\structural-cli.exe model validate .\examples\frame-alpha-cantilever.model-ir.json --require-analysis-ready
.\bin\structural-cli.exe model analyze-frame3d .\examples\frame-alpha-cantilever.model-ir.json --load-pattern LC_WEAK --result-id example.LC_WEAK --report-id example.LC_WEAK.report --output workbench-bundle --output-dir .\output\example.LC_WEAK
~~~

The result directory is complete only after `manifest.json` is present. The command fails rather
than overwriting an existing output directory.

## Compare an operator-attached external result

Create a strict external reference using
`schemas/external_linear_frame3d_reference_v1.schema.json`, preserving the exact model/load
binding, declared global/member-local axes, units and original export SHA-256. Then compare it with
the canonical `result-ir.json`:

~~~bash
./bin/structural-cli result compare-frame3d \
  output/example.LC_WEAK/result-ir.json external-reference.json \
  --comparison-id example.LC_WEAK.external --output html > comparison.html
~~~

An evaluated tolerance failure returns a nonzero status while still emitting the auditable
ComparisonIR or HTML. A malformed, partially mapped or transplanted reference emits no comparison
artifact. The reference mapping and export hash remain operator declarations; a PASS is not
independent validation or release authority.
