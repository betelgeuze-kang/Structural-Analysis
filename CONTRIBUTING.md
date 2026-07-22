# Contributing

Thank you for improving Structural Analysis. The project accepts focused,
reviewable changes that preserve numerical truth, reproducibility, and honest
capability boundaries.

## Before changing code

1. Read [AGENTS.md](AGENTS.md), the relevant architecture decision records,
   and the current gap ledger.
2. Open or reference an issue for behavior changes. State the user-visible
   outcome, affected package boundary, verification plan, and known
   limitations.
3. Keep research, proxy, fallback, benchmark-bridge, and externally blocked
   evidence explicitly labelled. A passing local test alone does not authorize
   a public or commercial capability claim.

## Development checks

Install the Python development dependencies and run focused tests first:

    python3 -m pip install -e '.[dev]'
    python3 -m pytest -q path/to/relevant_test.py
    python3 -m ruff check path/to/changed.py

For frontend changes:

    npm ci
    npm run build

Before requesting review, run the repository quality gate appropriate to the
changed surface and:

    python3 scripts/check_product_identity.py
    python3 -m compileall -q src
    git diff --check

Do not regenerate protected readiness evidence merely to make a check green.
Evidence producers must run against their declared inputs, preserve source
commit and checksums, and retain negative or blocked results.

## Pull requests

- Use a descriptive title and link the governing issue with an explicit
  closing keyword only when the PR actually completes the issue acceptance
  criteria.
- Describe package/API compatibility, tests, evidence effects, and rollback.
- Add focused tests for changed behavior.
- Never weaken tolerances, delete blockers, convert fallback output into
  authority, or edit receipts by hand to obtain PASS.
- Changes to numerical truth, contract schemas, V&V promotion, AI control, or
  protected release evidence require the owners listed in CODEOWNERS.

Submitting a contribution does not grant a separate license to this
repository. Contribution and redistribution terms require an explicit written
agreement with the applicable rights holders.
