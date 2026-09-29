# Plan-derived 40/80 mm public RC portal paths

This is a bounded software observation at clean source `49457f0709a4fef6a58fcfc288f7c6004d53a5d9`. The [original two-base model](../../examples/research/rc_internal_portal_20mm/original-model.json) and [original 20 mm request](../../examples/research/rc_internal_portal_20mm/original-request.json) were not changed. The public two-fixed-endpoint v3 request retains its two −25 kN roof loads, +150 kN N4 reference load, solver settings, and explicit experimental opt-in. Following the [portal study plan](rc-portal-recovery-admission-20260921.md), only the target tuples were derived as `(-A/2, -A, +A/2)` for `A=40` and `80 mm`. Neither tuple is a preserved original request.

| Source boundary | SHA-256 |
| --- | --- |
| Original model bytes | `6f8eec155f5fcf2f9ae942c021a8692e79ae1efd0d1b98342f8aea0b642d0ed6` |
| Existing experimental 20 mm v3 request | `92e94d3580bdf76edabef458ac0f769e054087ab04f897178f3692b2098c0e45` |
| [Derived 40 mm v3 request](../../examples/research/rc_internal_portal_20mm/experimental-two-fixed-endpoints-derived-40mm-request.json) | `c8e4954ee7560ccd73b5e69ae364bd157f87b5a23cf230d168a62900d4ae395d` |
| [Derived 80 mm v3 request](../../examples/research/rc_internal_portal_20mm/experimental-two-fixed-endpoints-derived-80mm-request.json) | `abf8d1d84a6b05af107730494ae5440deb305ceae123b91ceb5c92eb5feea782` |

Each request was run through `rc_fiber_frame_direct_control_cli run` with the original model, separate result/report/checkpoint paths, and mandatory fresh complete-source artifact verification. For example, the 40 mm invocation was:

```sh
PYTHONPATH=src python3 -m structural_analysis.api.rc_fiber_frame_direct_control_cli run \
  --model examples/research/rc_internal_portal_20mm/original-model.json \
  --request examples/research/rc_internal_portal_20mm/experimental-two-fixed-endpoints-derived-40mm-request.json \
  --output /tmp/rc-public-portal-40mm-49457/result.json \
  --report /tmp/rc-public-portal-40mm-49457/report.json \
  --checkpoint-output /tmp/rc-public-portal-40mm-49457/checkpoint.json
```

The original executions used byte-identical request files in their `/tmp` packet directories. The 80 mm invocation substituted its derived request and `/tmp/rc-public-portal-80mm-49457` output directory. The CLI's reported API timings exclude input parsing, report formatting, and output writes; analysis and mandatory verification are separate executions.

Separate `verify` CLI processes then checked each stored result and checkpoint against the committed request bytes. Both returned `valid_artifact` with fresh source execution; the 40 mm report retained `contract_pass=true` and the 80 mm blocked-result report retained `contract_pass=false`. Their respective verification-report byte SHA-256 values are `4f9ec2e257f62a13815ffd24991e0e0dcdf1a979392fed04d94a69f90ce81a04` and `d368419084dc6d96eeac4cbf2153b507ea663bf563eb986eb536dfb6757ad042`.

| Derived history | Analysis result and accepted targets | Analysis work | Fresh verification | Function wall time, analysis / verification |
| --- | --- | --- | --- | --- |
| −20, −40, +20 mm | `ready`, 3/3 accepted | 4 attempted steps, 36 known Newton iterations and linear solves, 0 unknown attempts | `valid_artifact`, 4 steps / 36 solves, `contract_pass=true` | 2.183 / 2.337 s |
| −40, −80, +40 mm | `blocked`, 0/3 accepted; first −40 mm attempt rolled back exactly after `line_search_failed_to_reduce_residual`; later targets unattempted | 2 attempted steps, 7 known iterations and solves, 0 unknown attempts | `valid_artifact` of the **blocked result**, 2 steps / 7 solves, `contract_pass=false` | 0.876 / 0.890 s |

Both analyses include one accepted constant-load preload. For 40 mm, all accepted N4 horizontal displacements equal their requested targets, each response contains six support-reaction components, and the largest checked horizontal/vertical global force-balance residual is below `1e-9 N`. For 80 mm, the failed first lateral attempt retained its parent checkpoint; the published checkpoint does not imply any accepted lateral target. Validating the blocked artifact confirms reproducible failure records, not successful completion.

The 40 mm CLI result's canonical `result_hash` is `sha256:62f1227dda58c3d8bf17a84602af68038df17c9ec31353f302a238586c48b9a5` and its report hash is `sha256:3d5d8554e560aef0ec0e7639f1e84b253779b3e6d84c9983da7f51bea7679e54`. The 80 mm result hash is `sha256:9eab66e948eb24f5539ddfc4d76a30711dd41c481a5fc78d218a42626f023a4c`; its report hash is `sha256:6339a2864a0aad44251db065f54e4e69064e0ca80c03f4d550c38e2025ed58a7`. The full packets remain local `/tmp` observations, not GitHub-hosted data. An initial direct 40 mm probe also returned `ready` and wrote its result artifact, but its metadata writer failed afterward; it has no complete parent timing record and is excluded from this table.

The public fixed-chord 40 mm completion is not equivalent to the [separate internal corotational 40 mm recovery](rc-internal-portal-40mm-recovery-20260927.md). No public 80 mm recovery strategy, repeat-order comparison, learned proposal, external experimental match, or physical/design qualification is established. In particular, the 40 mm and blocked 80 mm times must not be used as a speed comparison. The direct public 80 mm failure is a concrete starting point for an explicitly recorded, fixed-parent recovery study that does not silently commit intermediate material states or erase failed work.
