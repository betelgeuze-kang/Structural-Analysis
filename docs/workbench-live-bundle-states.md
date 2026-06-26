# Workbench live bundle states

Workbench v2 has five live bundle states:

- `loading`: fetch in progress.
- `missing`: bundle or artifact unavailable; infer no result.
- `available`: bundle and artifact copies load from one snapshot.
- `mixed_commit`: source commits differ; do not combine values.
- `blocked`: source loads but reports blockers.

Display requirements:

- source id and label
- source path
- bundle copy path
- checksum
- source commit
- generated timestamp when available
- gate state
- blocker count

Demo cases and live bundle data stay separate. Missing live data must never become demo data automatically.
