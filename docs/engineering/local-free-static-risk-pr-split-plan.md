# Local-free static risk and PR split plan

Purpose: define static review risks and reviewable PR slices that can be prepared without local PC, CI, GPU, Windows, or protected evidence refresh.

This packet is **non-promoting**. It does not prove tests pass and does not replace local or CI execution.

## Static risk areas

### Risk 1 — Dependency/import mismatch

Known pattern to check:

- runtime dependency list may be narrower than imported solver dependencies;
- solver modules that import optional heavy dependencies at module import time can break clean installs;
- package/CLI smoke should confirm import paths from a clean environment.

Local-free action:

- identify import paths and dependency declarations;
- prepare patch proposal if mismatch is found;
- do not claim clean install until local/CI smoke passes.

### Risk 2 — Protected evidence drift

Known pattern to check:

- generated evidence artifacts may be updated without rerunning producers;
- product readiness snapshot may be fresh while underlying closure evidence remains blocked;
- direct aggregator source tracking helps, but cannot replace leaf validation.

Local-free action:

- inspect source_commit_sha and input checksums;
- flag changed producer scripts that require artifact regeneration;
- keep generated-evidence commits separate from source-code commits.

### Risk 3 — Over-promoting release-surface PASS

Known pattern to check:

- material/contact/support release surfaces may PASS;
- top-level G1 full-load/full-mesh/material/HIP may still be blocked.

Local-free action:

- add claim-boundary checks in docs;
- keep surface PASS wording separate from product readiness wording.

### Risk 4 — Structural scope cleanup partial state

Known pattern to check:

- quarantine complete;
- owner decisions missing;
- release-surface delete/extract decisions missing.

Local-free action:

- create owner decision pack;
- avoid deleting without owner signoff;
- keep cleanup PR separate from evidence refresh.

### Risk 5 — Runner policy vs runner availability

Known pattern to check:

- workflow labels may reject GitHub-hosted fallback correctly;
- self-hosted runner may still be offline;
- CI streak evidence requires actual 30-run streaks.

Local-free action:

- review workflow labels statically;
- do not claim CI readiness without runner status and streak receipts.

### Risk 6 — G1 diagnostic evidence promotion

Known pattern to check:

- direct residual terminal slice ready;
- full-load/HIP/Newton lane still blocked;
- row-only correction and fixed-point residual must not be promoted.

Local-free action:

- maintain G1 closure contract;
- separate diagnostic and closing receipts.

## Recommended PR split

### PR 1 — Structural scope owner decision preparation

Scope:

- add or update owner decision guidance;
- release-surface first decision matrix;
- no deletion;
- no protected evidence refresh.

Reviewers:

- PM/release owner;
- repository owner;
- domain owner for molecular/science extraction.

Acceptance:

- owner-decision instructions are complete;
- no release readiness claim is promoted.

### PR 2 — UX/license/customer/EB evidence intake templates

Scope:

- templates and field guides only;
- no fake evidence;
- no generated gate promotion.

Reviewers:

- PM owner;
- UX owner;
- product/legal owner;
- customer evidence owner.

Acceptance:

- templates include required fields and forbidden substitutes.

### PR 3 — Developer Preview final-gate packet

Scope:

- medium model closure checklist;
- Windows replay checklist;
- human observation checklist;
- known limitations wording.

Reviewers:

- DP owner;
- benchmark owner;
- platform replay owner;
- UX owner.

Acceptance:

- DP remains not-ready unless final gates close.

### PR 4 — G1 closure contract/runbook

Scope:

- residual/Jacobian contract;
- G1 acceptance criteria;
- HIP proof checklist;
- material Newton breadth criteria.

Reviewers:

- solver numerics owner;
- GPU/HIP owner;
- PM claim-boundary owner.

Acceptance:

- diagnostic evidence and closure evidence remain distinct.

### PR 5 — Claim-boundary and documentation audit

Scope:

- README/current-state wording review;
- no readiness promotion;
- current blocker counts retained.

Reviewers:

- PM owner;
- technical owner;
- release owner.

Acceptance:

- public wording aligns with product readiness snapshot.

### PR 6 — Static hygiene patch proposal

Scope:

- dependency/import mismatch patch if found;
- workflow/static config review;
- no protected evidence refresh unless separately approved.

Reviewers:

- maintainer;
- CI owner.

Acceptance:

- local/CI test plan is documented, even if not run in PR.

### PR 7 — Evidence refresh PR

Scope:

- generated artifacts only;
- rerun producer commands locally/CI;
- no source-code changes mixed in.

Reviewers:

- release owner;
- evidence owner.

Acceptance:

- source_commit_sha and input checksums are current;
- snapshot is not promoted unless leaf gates pass.

## Recommended commit hygiene

- Keep docs-only packets separate from evidence refresh commits.
- Keep source-code/tooling changes separate from generated artifact updates.
- Avoid deleting quarantined paths until owner decisions are attached.
- Avoid writing protected readiness artifacts from local-free review.
- Use explicit non-promoting commit messages when adding handoff docs.

## Claim boundary

This plan helps reviewers split work safely. It does not prove tests pass, does not close release gates, and does not replace protected evidence regeneration.
