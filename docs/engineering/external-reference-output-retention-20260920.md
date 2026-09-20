# Opt-in original external-output retention

Fresh `run_external_code_to_code_technical_receipt.py` execution now accepts
`--raw-output-dir /absolute/new-directory`. The builder reserves a new directory
before either external call and routes engine outputs into separate `opensees`
and `calculix` subdirectories. Existing directories are rejected, so attempts
cannot silently overwrite or combine evidence. Check and product-replay modes
reject the option because they do not execute a fresh external reference.

After the pinned OpenSees executor returns, the capture stores the exact driver,
decoded stdout/stderr text, exit code and runtime binding before JSON/version/exit
validation. Invalid output and nonzero exits therefore keep diagnostic text.
The UTF-8 text hashes match the receipt's existing decoded-output hashes. These
are not a claim to retain undecoded subprocess bytes. If runtime authentication
raises before returning the completed process, this layer has no completed
output to retain; it leaves the reserved directory and propagates the failure.

CalculiX uses its existing capture implementation: version stdout/stderr, job
stdout/stderr, input decks and any generated DAT/FRD files are preserved before
job validation. A later CalculiX failure leaves earlier OpenSees evidence intact.
The receipt schema, numerical comparisons, fixed tolerances, return-code policy
and runtime authentication remain unchanged. Capture is diagnostic material and
cannot turn a failed reference comparison into a pass.

Eight focused tests pass using controlled executor outputs: successful hashes,
nonzero exit, malformed JSON, invalid version, existing-directory rejection,
nonexecution-mode rejection, builder routing/failure preservation and CLI routing.
These tests are not fresh OpenSees/CalculiX numerical executions. Pinned-runtime
regressions are checked separately. Ruff and diff checks pass.

This change does not alter protected receipts or add capture files to signed
clean-runner artifacts. Their inventory/schema/attestation integration requires a
separate reviewed change; the option can be used now for local fresh-reference
diagnostics. Full Python CI and the two original reaction comparisons remain
open. No independent, legal, hardware or release qualification is asserted.

## Actual frozen-source OpenSees observation

At committed source `740122e0a262f81a00fc199cbb189870e077ad5f`, the full original driver ran
once using the authenticated pinned OpenSeesPy/OpenSeesPyLinux 3.7.1.2 wheels.
Decoded stdout/stderr and driver file hashes match the returned execution record.
Removing attempt telemetry gives a numerical payload exactly equal to the earlier
pinned original. All twelve recorded planar attempts return zero. This is not an
independently counted total Newton workload.

The enclosing `_run_opensees` call took 1.534014564 seconds, including runtime
verification/staging/capture; the observer process took 3.263375660 seconds.
These nested single observations are not acceleration measurements. All 793
packet files were reread and hash/length verified. The inventory is
`b5d8d2556823953d77047ac8f1b9191747f97a20227a799425bdbb0b143f1b20`.
Exact source and packet location are in [the summary](external-reference-output-retention-20260920.summary.json).

The 27 pinned-runtime regressions also passed, in addition to the eight new
capture checks. No product reanalysis, CalculiX rerun, full technical receipt,
protected artifact refresh or signed acceptance occurred. The same reference
numbers preserve the two unresolved reaction comparisons; no acceptance credit
is added by this observation.

## Subsequent actual CalculiX capture observation

A separate observation then ran the unchanged axial and spatial-truss jobs with
CalculiX 2.17, using the same frozen implementation source as the OpenSees check.
All three Debian asset hashes matched the repository pins before extraction;
BLAS/LAPACK dependencies matched the retained source-reference profile. Runtime
extraction was private and temporary. The two returned numerical payloads equal
the prior local source-reference CalculiX result exactly.

All twelve retained output/input hashes match: version stdout/stderr plus each
job's stdout, stderr, INP, DAT and FRD. All 19 observation packet files were
reread and verified. The wrapper took 21244115 ns; the enclosing
extraction/execution/check interval took 169720115 ns. These nested
single-run costs do not establish speedup. Inventory:
`d08b39e754c15fc6babeb3406c31e258bf8320e95e0dac7a0e62d935dab8b5fc`.

[The CalculiX summary](external-reference-output-retention-calculix-20260920.summary.json)
binds the runtime binary, source and original packet. This follows the earlier
OpenSees-only observation; its recorded zero CalculiX executions remains correct
for that earlier packet. No current-product reanalysis or complete technical
receipt was generated, and the existing OpenSees comparison failures remain.

## Development CI registration

The eight capture tests initially lived in the full external-receipt test module,
which the development lane did not select. They now live in
`tests/test_external_reference_output_capture.py`, with no stored-receipt reads,
and are explicitly registered in that lane. All original full receipt tests
remain in their original module and the full gate is unchanged. The selection
contract requires the new module (70 development modules). Capture, pinned-runtime
and selection checks pass together: 36 tests in 5.20 seconds. This closes a test
execution omission, not external numerical or independent acceptance.
