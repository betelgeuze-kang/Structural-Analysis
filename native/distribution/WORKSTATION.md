# Structural Frame Alpha Workstation Distribution Candidate

This portable directory contains the bounded CPU-only `structural-cli`, a hash-bound production
Workbench static build configured for the same-origin `/api/v1/frame3d/jobs` endpoint, one
analysis-ready ModelIR v2 example, strict workstation/job/external-comparison schemas, and the
project license.

It is a development candidate, not an installer or a released engineering product. The packaged
static files and CLI can be served together on loopback, but the package has no code signature,
SBOM, auto-update, clean-machine receipt, browser-execution receipt, external validation, design
authority, commercial authority, or release authority.

## Start the packaged Workbench

Linux:

~~~bash
./bin/structural-cli workstation serve \
  --store jobs --workbench workbench --listen 127.0.0.1:8787 \
  --worker-timeout-seconds 300
~~~

Windows PowerShell:

~~~powershell
.\bin\structural-cli.exe workstation serve `
  --store jobs --workbench workbench --listen 127.0.0.1:8787 `
  --worker-timeout-seconds 300
~~~

Open `http://127.0.0.1:8787/` in a browser. The host rejects non-loopback binding and cross-origin
mutation. Runs execute in bounded child processes. Cancel can kill and reap only the registered
active child before append-only `Cancelled` finalization. This is not a privilege sandbox,
CPU/memory resource control, background queue, retry/resume, or durable crash recovery.

The extracted smoke receipt proves same-runner CLI validation/analysis plus loopback serving of the
exact packaged index, one referenced asset, and the v2 host capability document. It does not launch
a browser and does not establish clean-machine or cross-platform parity.
