# Licensing decision packet

## Purpose

The repository is publicly visible, but `LICENSE` currently grants no permission to use, copy, modify, publish, distribute, sublicense, sell, or create derivative works. This packet prepares an owner decision; it does not change that posture and is not legal advice or legal approval.

## Decisions the copyright holder must make

1. Which surfaces may be used and modified by external users?
2. May external users redistribute source, binaries, benchmark definitions, or generated receipts?
3. Must modifications to the numerical engine remain open?
4. May hosted/network use remain private?
5. Is a commercial license offered alongside a community license?
6. Which datasets and third-party materials may be redistributed or used for training?
7. Is a Contributor License Agreement required, or is Developer Certificate of Origin attestation sufficient?
8. Which entity can approve license exceptions, commercial terms, and future changes?

## Candidate software policies

| Candidate | Useful when | Main benefit | Main tradeoff |
|---|---|---|---|
| Apache-2.0 | Maximum adoption and commercial integration are primary | Permissive use plus an express patent grant | Downstream proprietary forks are allowed |
| MPL-2.0 | File-level improvements should remain available without forcing an entire application open | Narrow copyleft with commercial integration | File boundaries and combined-work interpretation require care |
| AGPL-3.0 plus commercial license | Hosted modifications should be shared or commercially licensed | Strong network copyleft and dual-license leverage | Some companies will not adopt AGPL components |
| Source-available research license plus commercial license | Evaluation and research access are desired before true open source | Tighter control over use and redistribution | It is not open source and may sharply limit community participation |
| Split policy | Schemas, benchmark SDK, and interoperability contracts should be open while the production engine remains commercial | Supports reproducibility without disclosing every commercial component | Requires clear repository/package boundaries and license notices |

No candidate is selected by this document.

## Recommended decision boundary for this repository

A practical split for owner review is:

```text
Open-policy candidates
  ModelIR / ResultIR schemas
  benchmark definitions and validators
  reproduction receipt formats
  interoperability templates
  community tooling and examples owned by the project

Separate owner decision
  C++/HIP production engine
  commercial Workbench features
  enterprise connectors, licensing, updater, and support tooling

Source-specific decision
  papers, external solver outputs, contest files, experimental datasets,
  third-party code, generated binaries, and screenshots
```

This split is a decision aid only. It does not grant permission for any path.

## Third-party material gate

Every material intended for external distribution, derivative use, or training must appear in `third-party-material-inventory.v1` with:

- repository path patterns;
- source identity and SHA-256;
- license identifier;
- explicit use, redistribution, derivative-work, and training flags;
- evidence reference when any permission is asserted;
- review status.

Validate an inventory with:

```bash
python scripts/validate_third_party_material_inventory.py \
  examples/third-party-material-inventory.sample.json
```

Repository scopes are restricted to an exact literal path or a literal directory
prefix followed by terminal `/**`. A recursive scope is walked with non-following
`lstat` semantics and fails closed if any file or directory below it is a symlink,
including internal and broken links. This is a point-in-time intake check, not a
continuous TOCTOU guarantee; consumers must validate again immediately before use.

An `approved` inventory row is still an internal record. It does not replace legal review, the original license text, attribution requirements, export controls, privacy obligations, or a signed owner decision.

## Contribution gate

Until the owner adopts a contribution policy:

- public visibility is not permission to fork, modify, redistribute, or submit derivative code;
- contribution instructions must preserve the no-license boundary;
- external patches should not be merged under ambiguous inbound terms;
- any future CLA or DCO policy must be approved by the copyright holder;
- security reports and factual bug reports can be received without treating attached derivative code as licensed.

## Required owner record

A final licensing decision should identify:

- policy name and exact license text/version;
- packages and path globs covered by each policy;
- effective date and approving copyright holder;
- inbound contribution terms;
- commercial exception authority;
- third-party inventory revision approved for distribution;
- migration steps for existing contributors, artifacts, and releases;
- rollback or supersession policy.

## Cryptographic decision gate

The release-area license gate does not treat CLI arguments, ticket references, URLs, or an
`{"approved": true}` file as owner authority. Its only eligible input is a local decision matching
`canonical/rights-holder-license-decision.v1.schema.json`, signed with RSA-SHA256 by a non-revoked
signer enrolled in `canonical/rights-holder-license-trust-root.v1.json`.

The verifier binds the signature to the exact:

- repository ID and Git source commit;
- root `LICENSE` SHA-256 and tracked blob at that commit;
- decision ID, license ID, tier, approver role, and bounded product scope;
- a tracked `canonical/license-policies/` document by exact path, version, SHA-256,
  and covered first-party paths;
- issue time, explicit future expiry, revocation state, nonce, and replay policy.

The trust root and public verification key must also be regular, non-symlink files tracked with the
same bytes at that source commit. The approved signer row independently constrains the root-license
hash, license IDs, policy artifact, covered paths, tiers, approver roles, and exact bounded scope.
Only the canonical trust-root path is accepted. Signed decisions must be local JSON files under
`implementation/phase1/release/license_decisions/`. The source worktree must cryptographically
match every tracked Git blob in the decision commit, use a plain non-sparse index, and contain no
extra file apart from the signed decision and canonical license-status authority record. Strict
Git-LFS pointers are checked against expanded-object SHA-256 and size. RSA keys smaller than 2048
bits and validity windows longer than 90 days are rejected, and the verifier uses the process's
current UTC clock rather than a caller-selected time.
A signed decision may close only the bounded first-party
repository-use, commercial-use, and redistribution license gate. It cannot approve redistribution
of third-party material and cannot grant aggregate product release authority.

The checked-in trust root intentionally has no approved signers. Accordingly, current/default
commercial-use and redistribution status remains `false` and blocked. A rights holder must first
choose the actual policy and scope, authorize a public verification key through reviewed repository
governance, retain the private key outside the repository, and issue the signed exact-source
decision. Engineering must not create those legal rights by populating metadata or running the
helper CLI.

Legacy `project_package.zip` output follows the same boundary. Every generated archive contains
the exact root `LICENSE`, a machine-readable `LEGAL_AND_THIRD_PARTY_STATUS.json`, and a package
manifest that hashes both files. Project approvals and the tool-generated project/release Ed25519
keys can make only the technical package-integrity contract pass. The embedded rights status keeps
product-license, commercial-use, redistribution, third-party-clearance, and release authority
false; a future rights-holder integration must consume the cryptographically verified gate and
preserve complete third-party notices before changing any bounded first-party authority field.
The release-publication candidate's `ok` field likewise means asset-copy and manifest integrity
only, never permission to upload, publish, redistribute, commercialize, or release.
The publication workflow never receives a technical-producer private key and never signs after
checkout. It accepts only pre-signed registry/package bytes already bound to the exact protected
source, an approved public-key fingerprint in the immutable producer policy, and the subsequent
legal/revocation gates. The checked-in empty signer allowlist therefore blocks publication until a
separate protected signing ceremony and rights-holder review have occurred.
The operator must dispatch publication with the exact GitHub artifact ID and archive SHA-256 from
that ceremony. The workflow downloads that repository artifact after the nightly gate, requires its
producer run to match the current protected `main` SHA, extracts only the fixed registry/package
member set into a fresh private work directory, and then verifies the pinned registry signatures.
Nightly-generated temporary registry keys and files are never used as publication inputs.
The release-publish workflow separately invokes the isolated closure verifier with
`--require-release-authority` before any publication work. That gate requires the verified
rights-holder decision plus explicit first-party commercial/redistribution, third-party-material
redistribution, and overall release authority. The current contract intentionally leaves the last
two fields false, so a technical registry, package, candidate, or general approval cannot publish a
release.

Release dispatch is confined to the current `release-publish-current.yml` workflow on the protected
`main` head and the `release` environment. That environment must pin the SHA-256 of an independently
held RSA revocation public key, the SHA-256 of the latest signed revocation epoch, and its minimum
monotonic epoch number. The workflow downloads those exact files from the live default-branch head,
verifies their signature and a realizable signed ancestor commit/tree binding against the checked-out
current head, and rejects a decision or signer revoked after an older source commit. It repeats the
revocation check against the final closure decision digest after the release-authority evaluation.
Renaming the workflow makes historical refs that contain only the retired workflow
path ineligible for dispatch. The current repository intentionally provides neither an approved
signer nor an active revocation epoch/key; the corresponding environment values must remain unset
until the rights holder establishes that external trust anchor, so release authority remains false.

## Claim boundary

This packet provides engineering options and inventory controls only. It creates no software-use permission, data-use permission, legal approval, open-source status, external V&V credit, product support, commercial readiness, or release authority.
