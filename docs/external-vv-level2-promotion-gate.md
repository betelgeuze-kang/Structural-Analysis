# External V&V Level 2 promotion gate

The independent-operator intake receipt is necessary but intentionally not
sufficient for Verification Level 2. The promotion gate consumes the original
signed attestation and bundle, not a copied boolean from its validation receipt.

## Required authority chain

All of the following must be present in one project-signed
`external-vv-level2-promotion.v1` decision:

1. the exact independently signed operator attestation and its fresh
   OpenSees/CalculiX clean-runner bundle;
2. project-side operator identity authentication and conflict review, with a
   checksum-bound credential-review artifact;
3. separate OpenSees and CalculiX legal reviews approving local execution and
   commercial use for evidence generation;
4. separate PASS scientific decisions for the OpenSees and second-solver
   hierarchy slots;
5. exact binding to both code-to-code and modal/buckling child receipts;
6. an authorized project reviewer RSA-SHA256 signature; and
7. a checksum-bound 25/25 bounded-planar verification matrix with every exact
   case ID backed by a fresh, operator-signed receipt binding; and
8. exact candidate source commit parity.

The validator revalidates the operator signature, full receipt schemas, fresh
external execution, child receipt self-hashes, external runtime package hashes
and versions, legal evidence file hashes, scientific decisions, and the project
signature. Missing or stale input produces no hierarchy manifest.
The gate revalidates the matrix schema, source commit, summary, claims, core
and supplemental receipt file/self hashes, signed-bundle membership, and exact
case inventory. The current matrix is technically 25/25, but it remains
same-operator evidence and is still structurally incapable of promotion until
the complete core and five supplemental receipt families are present in the
independently signed bundle and every external authority check passes.

## Solo-developer boundary

This promotion gate is intentionally external to the solo-developer technical
completion path. A developer may complete source-bound execution packages,
clean-runner replay, deterministic comparison, license inventory, notices, and
source-use declarations without pretending to be an independent operator or
legal reviewer. Those outputs support only bounded technical/Developer Preview
claims.

If independent identity authentication or counsel review is unavailable, record
the evidence as `unavailable` and leave this gate unpassed. That state blocks
only independent Verification Level 2 and downstream promotion claims; it does
not invalidate repository integrity or passing same-operator technical gates.
An internal license inventory is useful due diligence but is not a substitute
for the legal-review artifacts required here.

## Signing and promotion

Populate `docs/templates/external_vv_level2_promotion.template.json`. Keep both
private keys outside the repository and submission bundle. Emit the project
review signing payload, sign it, fill the signature hashes, then run the gate:

```bash
python scripts/promote_external_vv_level2.py \
  --promotion submission/external-vv-level2-promotion.json \
  --expected-source-commit <40-hex-candidate-commit> \
  --emit-signing-payload /tmp/external-vv-level2-promotion.payload.json

openssl dgst -sha256 \
  -sign /project-private/project-reviewer-private-key.pem \
  -out submission/project-review.sig \
  /tmp/external-vv-level2-promotion.payload.json

python scripts/promote_external_vv_level2.py \
  --promotion submission/external-vv-level2-promotion.json \
  --bundle-root submission \
  --expected-source-commit <40-hex-candidate-commit> \
  --manifest-out implementation/phase1/release_evidence/productization/verification_hierarchy_evidence.json \
  --receipt-out submission/external-vv-level2-promotion.receipt.json
```

The output manifest contains the checksum-bound complete matrix binding plus
the `opensees_code_to_code` and `second_solver_code_to_code` Level 2 hierarchy
rows. The generic hierarchy builder still enforces contiguous Level 1 → Level
2 promotion.

## Authority boundary

Passing this gate grants only the two named Level 2 evidence slots for the exact
source commit and signed bundle. It does not grant Level 3 or higher,
commercial-solver equivalence, design authority, release readiness, or external
runtime redistribution permission. Legal approval for local commercial evidence
use is recorded separately from redistribution permission.
