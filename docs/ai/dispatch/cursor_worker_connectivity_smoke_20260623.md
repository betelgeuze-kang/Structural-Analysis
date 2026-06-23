Goal: Verify Cursor worker connectivity and output formatting only.

Scope:
- Do not edit files.
- Inspect the repository root enough to confirm the worker can start.
- Return a concise summary with:
  - changed files: none
  - test results: not run
  - blocker: none, unless the worker environment itself cannot run

Verification criteria:
- The wrapper should capture a normal worker final summary in raw output.
- No source, evidence, or documentation file should be modified.
