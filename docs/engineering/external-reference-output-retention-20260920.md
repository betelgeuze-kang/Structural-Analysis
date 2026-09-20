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
