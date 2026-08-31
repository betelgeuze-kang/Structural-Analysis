# ADR-010: Retire the source-quarry retained-device FGMRES architecture

- Status: accepted
- Decision ID: `frame-alpha-retire-source-quarry-retained-device-fgmres.v1`
- Product profile: `structural-workbench.frame-alpha.v1`
- Disposition: `owner_scope_retirement`
- Scope status: `retired_not_planned_for_current_product`
- Semantic-equivalence claim: `false`

## Context

Closed, unmerged PRs #77 and #78 contain an earlier retained-device/`FINAL_GUARD`
architecture. The product owner has frozen HIP expansion for the current Frame Alpha
product. Importing selected old files would create an ambiguous partial architecture.
This decision disposes of the complete PR-level scope; it does not claim that current
code implements or is semantically equivalent to that architecture.

Current product policy remains the CPU FGMRES reference path plus the lean HIP probe
described by `README.md` and `artifacts/manifests/capabilities.yaml`.

## Decision

Every changed-file row in PR #77 and PR #78 is dispositioned as follows:

- an exact identical blob already at the same path on current source is `present`;
- every other blob is `superseded` with reason `owner_scope_retirement`;
- the old branches must not be merged or imported wholesale;
- future reintroduction requires a new accepted ADR and a new one-purpose PR.

The following five #143 targets are retired and not planned for the current product:

1. `issue143_active_final_guard_at_exact_full_cycle_checkpoint_completion`
2. `issue143_fail_closed_malformed_handoff_prestate_before_publication`
3. `issue143_sealed_checkpoint_transaction_and_global_recurrence_handoff_invariants`
4. `issue143_cpu_oracle_hip_handoff_state_semantic_identity`
5. `issue143_exact_capability_matrix_wording_without_authority_promotion`

The following six #144 capability families are retired and not planned for the current
product:

1. `issue144_retained_device_checkpoint_history_context`
2. `issue144_launch_fence_and_host_transfer_audit_semantics`
3. `issue144_exact_current_source_hip_completion_terminal_observations`
4. `issue144_fixed_rank_coarse_and_checkpoint_history_kernel_contracts`
5. `issue144_retained_device_result_diagnostic_and_registry_disposition`
6. `issue144_device_provenance_signed_runner_replay_trust_authority_attack_contracts`

The old external signer/registry contract families are also retired and not planned:

1. `external_release_identity_contract`
2. `external_replay_ledger_contract`
3. `external_signed_evidence_contract`
4. `external_key_enrollment_and_runner_keys_contract`
5. `external_trust_anchor_registries_contract`
6. `external_reviewer_root_and_bootstrap_contract`
7. `external_signed_release_identity_binding_contract`

## Authority boundary

This decision grants no numerical, hardware, operator, signature, release, readiness,
or commercial authority. Actual gfx hardware execution, independent operator evidence,
and signed evidence authority remain false. External hardware and release blockers,
including #257 and any successor blockers, remain separate and open until their own
authoritative evidence exists.

The canonical inventory is a scope-disposition record, not evidence of implementation,
semantic equivalence, external V&V, hardware execution, or release eligibility.
