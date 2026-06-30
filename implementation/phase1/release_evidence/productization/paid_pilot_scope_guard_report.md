# Paid Pilot Scope Guard Report

- `summary_line`: `Paid pilot scope guard: PASS | scope_terms=5/5 | commercial_v1_supported_scope=12/12 | commercial_v1_separate_validation_exclusions=5/5 | artifacts=9/9`
- `contract_pass`: `True`

| Scope Check | Pass |
|---|---|
| `review_assist_boundary` | `True` |
| `specified_structure_families` | `True` |
| `specified_workflow` | `True` |
| `engine_reviewer_evidence_package` | `True` |
| `unsupported_or_missing_evidence_blocker` | `True` |

| Commercial v1 Supported Scope | Pass |
|---|---|
| `frame_families` | `True` |
| `wall_frame_families` | `True` |
| `outrigger_families` | `True` |
| `truss_families` | `True` |
| `midas_interop` | `True` |
| `opensees_interop` | `True` |
| `kds_interop` | `True` |
| `nonlinear_static` | `True` |
| `bounded_ndtha` | `True` |
| `residual_audit` | `True` |
| `reference_comparison` | `True` |
| `reviewer_package` | `True` |

| Commercial v1 Separate-Validation Exclusion | Pass |
|---|---|
| `rail_tunnel` | `True` |
| `special_ssi` | `True` |
| `nonstandard_contact` | `True` |
| `legal_authority_approval_automation` | `True` |
| `special_construction_stages` | `True` |

| Forbidden Claim Check | Pass |
|---|---|
| `limited_commercial_ready_true` | `True` |
| `limited_commercial_release_ready_true` | `True` |
| `ga_enterprise_ready_true` | `True` |
| `full_commercial_replacement_ready_true` | `True` |
| `engineer_of_record_replacement` | `True` |
| `autonomous_approval` | `True` |

| Evidence Artifact | Present | Required Pass | Contract Pass |
|---|---|---|---|
| `pm_release_gate_report` | `True` | `False` | `False` |
| `support_bundle_manifest` | `True` | `True` | `True` |
| `pm_owner_evidence_request_packet` | `True` | `True` | `True` |
| `pm_release_gate_reviewer_handoff` | `True` | `True` | `True` |
| `pm_release_reproduction_command_audit` | `True` | `True` | `True` |
| `pm_release_blocker_action_register` | `True` | `False` | `False` |
| `ci_streak_intake_packet` | `True` | `False` | `False` |
| `license_status_intake_packet` | `True` | `False` | `False` |
| `ga_enterprise_readiness_report` | `True` | `False` | `False` |

| Support Bundle Section | Present | Redacted Bundle Path |
|---|---|---|
| `pm_owner_evidence_request_packet` | `True` | `implementation/phase1/release/support_bundle/redacted/pm_owner_evidence_request_packet.json` |
| `pm_release_gate_reviewer_handoff` | `True` | `implementation/phase1/release/support_bundle/redacted/pm_release_gate_reviewer_handoff.json` |
| `pm_release_reproduction_command_audit` | `True` | `implementation/phase1/release/support_bundle/redacted/pm_release_reproduction_command_audit.json` |
