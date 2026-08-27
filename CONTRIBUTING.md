# Contributing

Thank you for improving Structural Analysis. The project accepts focused,
reviewable changes that preserve numerical truth, reproducibility, and honest
capability boundaries.

## Current legal boundary

This repository is publicly visible but is **not currently open source**. The
default `LICENSE` grants no permission to use, copy, modify, publish,
distribute, sublicense, sell, or create derivative works without a separate
written agreement from the applicable copyright holder.

Do not submit code, generated binaries, third-party datasets, or derivative
benchmark packages unless the repository owner has first confirmed the
applicable contribution and redistribution terms in writing. Opening an issue
does not grant a software or data license.

Bug descriptions, public-source citations, analytical benchmark proposals,
and documentation corrections may be discussed through issues when they do
not reproduce restricted material or imply product or verification authority.
Community reproduction receipts require an independently applicable execution
permission and follow `docs/community-validation-readiness.md`.

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
- Keep product code, generated evidence, and externally licensed data in
  separate review surfaces.
- Changes to numerical truth, contract schemas, V&V promotion, AI control, or
  protected release evidence require the owners listed in CODEOWNERS.

Submitting a contribution does not grant a separate license to this
repository. Contribution and redistribution terms require an explicit written
agreement with the applicable rights holders until a different policy is
formally approved.

## Security reports

Do not disclose suspected vulnerabilities in a public issue. Follow
[SECURITY.md](SECURITY.md).
