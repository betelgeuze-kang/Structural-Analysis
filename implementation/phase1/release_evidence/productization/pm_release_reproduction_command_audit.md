# PM Release Reproduction Command Audit

- `summary_line`: `PM reproduction command audit: BLOCKED | artifacts=0/1 | commands=1 | violations=1`
- `contract_pass`: `False`

## Artifacts

| Artifact | Pass | Commands | Violations |
|---|---:|---:|---:|
| `blocked` | `False` | `1` | `1` |

## Commands

| Artifact | Field | Pass | Class | Blockers | Command |
|---|---|---:|---|---|---|
| `blocked` | `validation_commands` | `False` | `local_static_or_report` | `command_script_missing` | `python3 scripts/missing.py` |

## Blockers

- `command_script_missing`
