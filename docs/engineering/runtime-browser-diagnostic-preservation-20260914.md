# Preserve browser failure evidence before the HTTP suite

Published source `c1eaa5d81db6c4b092421bdff8e467044b896a65`, runtime CI
run `34784621141`, failed one of 706 guarded browser tests. Artifact
`10326641095` contains the detailed log: the priced design-comparison case
could not find `[data-design-comparison="verified"]` within 5 seconds.
The later actual HTTP suite passed 36 tests. This is a real incomplete CI
gate, not a demonstrated numerical or price-calculation error.

The workflow uploaded only the guarded E2E text log after running the HTTP
suite. Both Playwright invocations use `test-results`; the second invocation
can replace the earlier error-context files before the existing upload.
The guarded E2E step now enables `--trace retain-on-failure` and uploads its
failed traces and error contexts immediately before the HTTP step. These
diagnostics have seven-day retention. The original failure exit status and
the independently running HTTP step are preserved; no timeout is increased.

At local source `c27fea1e1`, the existing guarded runner rebuilt the frontend
and ran the priced and unpriced comparison browser cases three times each,
with one worker: six passed in 29.9 seconds. This does not reproduce the
hosted failure or establish its cause under the larger concurrent suite.
No UI or schema behavior was changed based on this isolated passing run.

The workflow contract suite passed 19 tests in 0.37 seconds, including a
regression requiring failure-only diagnostic preservation before HTTP output
replacement, trace retention, and propagation of the browser exit code.
Hosted validation and the original browser failure diagnosis remain open.
