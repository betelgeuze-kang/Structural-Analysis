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

## Claim boundary

This packet provides engineering options and inventory controls only. It creates no software-use permission, data-use permission, legal approval, open-source status, external V&V credit, product support, commercial readiness, or release authority.
