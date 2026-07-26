# P2 engineering-review package

The P2 roadmap requires a signed engineering-review package. The repository
now has a deterministic handoff and verification contract for that package;
the current artifact remains deliberately unsigned and blocked.

## Bound review material

`artifacts/review/engineering_review_package.candidate.json` binds the exact
bytes of the roadmap, capability and quality manifests, repository-hygiene
inventory, verification hierarchy, OpenSees/CalculiX receipts, isolated clean
runner, fracture-energy benchmark, Lee-frame candidate, bounded global elastic
3D implementation, the bounded larger native-sparse graph and exact-condition
diagnostic, axial steel/concrete/fracture-energy/perfect-bond-composite stateful
3D implementation, their public exports and boundary documents, and durable
job-service implementation. Each row records its repository path, SHA-256, and
byte length. The canonical row set has a separate evidence-set hash, and the
complete review material has its own hash.

The package exposes seven mandatory decisions:

- numerical results;
- ResultIR/evidence authority boundaries;
- independent Level 2 V&V;
- published Level 3 benchmarks;
- the 3D external comparison;
- checkpoint/resume job-service integrity; and
- all known limitations and blockers.

Every prerequisite is evaluated from the machine-readable roadmap and
verification-hierarchy status. Missing prerequisites remain visible and cannot
be overridden by merely attaching a signature.

## Reviewer authority

`artifacts/manifests/engineering_reviewers.json` is intentionally empty. An
authorized owner must add a real independent licensed structural engineer with
jurisdiction, license identifier, organization, approved P2 scope, and an
Ed25519 public-key fingerprint. That registry change requires normal human
review. Invented identities or locally generated reviewer entries are not
authoritative.

Private keys must never enter the repository. Only the public key and its
fingerprint belong in the registry.

## Detached signature contract

The external reviewer prepares a
`structural-analysis-engineering-review-assertion.v1` JSON object bound to the
package's `review_material_hash`. It contains the reviewer ID, timestamp,
disposition, seven decisions, notes, and an explicit independence attestation.
The exact bytes to sign are canonical UTF-8 JSON with sorted keys and no
trailing newline. The repository tool can emit those bytes without handling a
private key:

```bash
python3 scripts/build_engineering_review_package.py \
  --canonicalize-assertion review-assertion.json \
  --canonical-out review-assertion.canonical.json
```

The reviewer signs that canonical file externally with the private Ed25519
key. After the signature, assertion, and public key are returned, the package
can be attached and verified with:

```bash
python3 scripts/build_engineering_review_package.py \
  --out artifacts/review/engineering_review_package.candidate.json \
  --attach-assertion review-assertion.json \
  --signature review-assertion.sig \
  --public-key reviewer-ed25519-public.pem \
  --write
```

Attachment verifies the Ed25519 signature, public-key fingerprint, reviewer
registry authorization, assertion-to-material binding, and every required
decision. It does not sign anything and never reads a private key.

## Fail-closed promotion rules

`signed_engineering_review=true` requires all of the following at once:

- a clean source tree whose HEAD equals the recorded remote default-branch
  HEAD;
- an authoritative current-HEAD release snapshot;
- every named P0-P2 external prerequisite and hierarchy Level 3 promotion;
- a reviewer authorized by the checked-in registry;
- a valid Ed25519 signature over the exact assertion; and
- `approved_for_p2_closure` with all seven decisions true.

The present candidate satisfies none of the missing external-authority items,
so `status=blocked`, `signed_engineering_review=false`, and
`release_authority=false` are the only valid outcomes. A valid signature over a
partial or rejected assertion still cannot promote the roadmap.

## Verification

```bash
python3 scripts/build_engineering_review_package.py --check
PYTHONPATH=src python3 -m pytest -q tests/test_engineering_review_package.py
```

The tests cover current evidence-byte binding, stale/tampered inventory
rejection, unauthorized reviewer rejection, a complete ephemeral Ed25519
verification path, signed-assertion tampering, and the stored candidate's
non-promoting claims. Test keys are ephemeral and never establish reviewer
authority.
