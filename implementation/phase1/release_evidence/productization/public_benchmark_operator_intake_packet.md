# Public Benchmark Operator Intake Packet

- `contract_pass`: `True`
- `status`: `ready_for_operator_input`
- `public_benchmark_ready`: `False`
- `claim_boundary`: This packet is an owner-facing intake contract for public benchmark evidence. It does not attach CASF/PDBBind, DUD-E, or LIT-PCBA source files, does not redistribute benchmark data, does not infer ligand chemistry, and does not close Tier beta without materialized real benchmark rows.

| Slot | Status | Intake Artifact |
|---|---|---|
| `casf_pdbbind_subset_intake` | `operator_input_required` | `<operator-casf-pdbbind-intake.json>` |
| `pose_coordinate_intake` | `operator_input_required` | `<operator-pose-coordinate-intake.json>` |
| `dud_e_lit_pcba_enrichment_intake` | `operator_input_required` | `<operator-dud-e-lit-pcba-enrichment-intake.json>` |
