# Structural Frame Alpha CLI Distribution Candidate

This portable directory contains the bounded CPU-only `structural-cli`, one analysis-ready
ModelIR v2 example, the distribution/smoke receipt schemas, and the project license.

It is a development candidate, not an installer or a released engineering product. It has no
code signature, SBOM, clean-machine receipt, external comparison, PDF output, design authority,
commercial authority, or release authority.

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
