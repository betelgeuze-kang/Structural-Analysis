# Frozen pin/roller candidate-search browser packet

`rc-pin-roller-search-v4.tar.gz` preserves the original JSON bytes of the
`search/` directory produced on source commit
`94df8579168f973494b8f7612259a6e4545372a2` for the six-model synthetic
pin/roller budget study. The archive SHA-256 is
`639131b23eef4bd9f2f3b921eabadfa154bb4567783cc011cac725fb119d9eab`;
the original search report hash is
`sha256:8bc487770f2ee052e2e6e709f51ac9a901acc4ae9e9202ac4e89e07dc7b5ca01`.
The frozen candidate plan is `plan.json` in the archive. The source packet's
reproduction and independent inventory/arithmetic audits are
`scripts/run_rc_pin_roller_budget_study.py` and
`scripts/audit_rc_pin_roller_budget_study.py`.
The full source-packet audit recorded a passing 173-file inventory digest of
`sha256:6073233df4e6d9c414a5539b608e1fee1a13f33d10b18bdcf265f0718f3f7065`;
this archive contains only its `search/` subtree.
The inputs and price table are repository-authored synthetic examples; this
fixture imports no third-party experimental or drawing dataset.

The HTTP browser test expands this archive into disposable test output, serves
its 109 referenced artifacts through the existing tenant-scoped immutable
artifact API, checks original download bytes, and forbids new solver calls and
fits. It tests the Workbench display of the verified `w46` cheaper miss and
recorded false negative. The price table and limits are synthetic. This
same-engine replay does not establish independent physical validity, monetary
savings, or general learned-search benefit.
