# H-Bond BackMap Operator Intake Packet

- `contract_pass`: `True`
- `status`: `ready_for_operator_input`
- `claim_locked`: `True`
- `current_surface_status`: `locked`
- `claim_boundary`: This packet is an owner-facing intake contract for H-bond BackMap receipts. It does not generate molecular evidence, infer missing receipt values, or unlock the H-bond BackMap evidence surface without authoritative rows and reviewer reproduction evidence.

| Slot | Status | Required Fields |
|---|---|---|
| `operator_attached_h_bond_backmap_cases` | `operator_input_required` | `case_id, receptor_id, ligand_id, source_system_ref, donor_acceptor_map_ref, contact_persistence_rate, backmap_accuracy_rate, h_bond_distance_error_angstrom_median, h_bond_angle_error_degree_median, reviewer_reproduction_command, provenance_ref, source_checksum` |
| `contact_persistence_or_backmap_accuracy_rows` | `operator_input_required` | `case_id, contact_persistence_rate, backmap_accuracy_rate, h_bond_distance_error_angstrom_median, h_bond_angle_error_degree_median, source_checksum` |
| `reviewer_reproduction_command` | `operator_input_required` | `command, expected_outputs, environment_ref, source_checksum` |

## Handoff Sequence

- `attach_h_bond_backmap_operator_receipts`: `attach authoritative H-bond BackMap receipt bundle`
- `materialize_h_bond_backmap_evidence_rows`: `materialize receipt-backed H-bond BackMap rows into implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json`
- `refresh_product_capabilities_surface`: `python3 scripts/build_product_capabilities_surface.py --out implementation/phase1/release_evidence/surface/product_capabilities_surface.json`
- `refresh_goal_bottleneck_roadmap_surface`: `python3 scripts/build_goal_bottleneck_roadmap_surface.py --out implementation/phase1/release_evidence/productization/goal_bottleneck_roadmap_surface.json`
- `refresh_pm_release_gate_report`: `python3 scripts/report_pm_release_gate.py --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json`

## Acceptance Criteria

- `h_bond_backmap_evidence_surface.required_receipts are all attached`
- `h_bond_backmap_evidence_surface.blockers == []`
- `h_bond_backmap_evidence_surface.contract_pass == true`
- `h_bond_backmap_evidence_surface.locked == false`
- `h_bond_backmap_evidence_surface.claim_locked == false`
