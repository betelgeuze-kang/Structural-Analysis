# Customer Shadow Evidence Intake Packet

- `contract_pass`: `True`
- `reason_code`: `PASS`
- `current_completed_shadow_case_count`: `0`
- `current_status_contract_pass`: `False`
- `target_completed_shadow_cases`: `5`
- `claim_boundary`: This packet creates owner-input slots and validation commands only. It does not create customer shadow evidence, ingest customer raw data, or close the 3/5 completed-project target. Each slot must be filled with real customer-retained derived metadata and pass the validator.

| Slot | Status | Evidence Path |
|---|---|---|
| `customer-shadow-case-001` | `owner_input_required` | `implementation/phase1/customer_shadow_evidence/customer-shadow-case-001.json` |
| `customer-shadow-case-002` | `owner_input_required` | `implementation/phase1/customer_shadow_evidence/customer-shadow-case-002.json` |
| `customer-shadow-case-003` | `owner_input_required` | `implementation/phase1/customer_shadow_evidence/customer-shadow-case-003.json` |
| `customer-shadow-case-004` | `owner_input_required` | `implementation/phase1/customer_shadow_evidence/customer-shadow-case-004.json` |
| `customer-shadow-case-005` | `owner_input_required` | `implementation/phase1/customer_shadow_evidence/customer-shadow-case-005.json` |

## Commands

- `validate_one_evidence_file`: `python3 implementation/phase1/validate_customer_shadow_evidence.py --evidence <filled-customer-shadow-evidence.json> --json --fail-blocked`
- `refresh_status`: `python3 scripts/check_customer_shadow_evidence_status.py --out implementation/phase1/customer_shadow_evidence_status.json --json`
- `refresh_evidence_console_scope`: `python3 scripts/build_evidence_console_scope_status.py --out implementation/phase1/release_evidence/productization/evidence_console_scope_status.json --out-md implementation/phase1/release_evidence/productization/evidence_console_scope_status.md --json`
