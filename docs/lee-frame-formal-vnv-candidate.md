# Lee-frame formal V&V candidate wiring

## Purpose

The bounded Lee-frame solver reproduces the published snap-through,
negative-load, snap-back, and rehardening path. This change connects that result
to the repository's formal verification-hierarchy input contract without
fabricating publisher-source bytes, source-use approval, independent
reproduction, or operator approval.

It produces a candidate operator manifest, not the canonical production
`verification_hierarchy_evidence.json`.

## Generated candidate bundle

```bash
PYTHONPATH=src:. python -m scripts.build_lee_frame_verification_candidate \
  --json \
  --fail-credit
```

The command writes:

```text
implementation/phase1/release_evidence/productization/
  verification_candidates/lee_frame/
    source_receipt.json
    execution_receipt.json
    scientific_decision.json
  verification_hierarchy_evidence.candidate.json
```

Every generated artifact is strict canonical JSON and is bound by an exact
SHA-256 in the candidate operator manifest.

## Generated receipt versus publisher source

The formal evidence row identifies the locally generated source receipt with:

```text
source_url_or_doi = generated://structural_analysis/verification/lee-frame/source-receipt.v1
source_sha256     = SHA-256(source_receipt.json bytes)
```

The published DOI is retained separately inside source and benchmark metadata:

```text
publisher_source_uri = https://doi.org/10.12989/sem.2011.38.6.767
publisher_source_bytes_attached = false
publisher_source_sha256 = null
```

The generated receipt hash must never be presented as the hash of the publisher
paper, table, or NAFEMS source bytes. Attaching permitted publisher/table bytes
and recording their own approved source receipt is a separate promotion step.

## Scientific decision

The generator executes `build_lee_frame_snapthrough_benchmark()` and evaluates:

- first limit load factor;
- maximum displacement-path distance;
- maximum and RMS load-factor error;
- equilibrium residual;
- arc-length constraint residual;
- energy-gradient consistency;
- tangent-Hessian consistency;
- tangent symmetry.

The bounded numerical case must receive scientific `PASS`. That PASS proves
only the named fixed Lee-frame comparison.

## Why formal credit remains zero

The generated hierarchy row is:

```text
level       3
category    nonlinear_snap_through
truth basis published_benchmark
```

but it explicitly declares:

- `publisher_source_bytes_not_attached`;
- `source_use_license_approval_missing`;
- `independent_clean_runner_receipt_missing`;
- `formal_operator_approval_missing`.

The source-license receipt remains `pending`, with local execution, commercial
use, and redistribution approval all false. The bounded kernel is also recorded
as not independent from the product.

Consequently:

```text
scientific decision PASS         true
artifact integrity               true
ready_for_hierarchy_credit       false
Level 3 intrinsic slot           false
contiguous promotion             false
highest verified level           unchanged
```

This distinction prevents a published path comparison from silently becoming a
commercial verification claim.

## Existing analytic and Level 2 evidence

`build_verification_hierarchy_status()` always composes the repository's five
Level 1 analytic rows. The candidate manifest is passed through the existing
`operator_evidence_path` argument and is added to, not substituted for, those
rows.

Higher-level evidence cannot bypass missing Level 2 code-to-code evidence. Even
if all Lee-frame candidate blockers are later resolved, contiguous promotion
remains blocked until the required OpenSees and second independent solver slots
are formally attached.

## Promotion procedure

Promotion requires real external inputs, not a code edit that flips booleans.
The operator must attach:

1. permitted publisher/table source bytes or an approved extracted data artifact;
2. source-use/license approval tied to those bytes;
3. independently executed clean-runner artifacts and source commit;
4. formal scientific/operator decision with traceable approver identity;
5. exact artifact hashes at the canonical operator-manifest path;
6. completed Level 2 code-to-code slots.

After those artifacts exist, regenerate the canonical hierarchy status and
review the full contiguous chain. Do not copy the candidate manifest into the
canonical path unchanged.

## Focused validation

```bash
PYTHONPATH=src:. python3 -m pytest -q \
  tests/test_lee_frame_verification_candidate.py \
  tests/test_verification_hierarchy_contract.py \
  tests/test_build_verification_hierarchy_status.py
python3 -m ruff check \
  src/structural_analysis/benchmark/lee_frame_verification_candidate.py \
  scripts/build_lee_frame_verification_candidate.py \
  tests/test_lee_frame_verification_candidate.py
```
