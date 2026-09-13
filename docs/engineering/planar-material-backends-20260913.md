# Public planar backends with observed concrete damage

Numerical source: `acd586e54aef44cd39cfa82fbc181fcfa6cf7ee2`.
This observation extends the earlier elastic-state backend comparisons into
concrete tensile damage. It does not establish steel yielding, cyclic behavior,
independent physical validation, larger-topology scaling or learned benefit.

## Frozen experiment

The existing `planar_frame_backend_process` v2 coordinator ran the public planar
load-control API on two generated variants of `examples/planar_frame_rc_portal.json`.
Every nodal load component was multiplied by 10 or 20; geometry, material laws and
sections were unchanged. These are related synthetic cases, not independent
projects or measured specimens. Model provenance records the generation recipe.

Each case used four monotonically increasing load factors (0.25, 0.5, 0.75, 1),
three CPU backends and three fresh-process repetitions: 18 declared slots, no
warmups. Backend order rotated across repetitions. Residual tolerance `1e-10`,
increment tolerance `1e-12 m`, maximum iterations 40 and the existing absolute
plus relative history comparison tolerances `1e-9` were unchanged. Each worker
had a 300-second timeout. The protocol was written before inspecting outcomes.
This six-free-equation portal is not a test of the extended backend's equation cap.

## Observed results

All 18 slots launched, entered the API, converged and passed source-bound artifact
validation, for 72 committed load steps. All 12 dense/sparse terminal and full
history comparisons passed. Twelve same-backend repeat pairs had byte-identical
result, checkpoint, history and validation artifacts. Across different backends,
checkpoint hashes were not equal; numerical agreement uses the declared
absolute-plus-relative tolerances.

The dense first-repetition histories had maximum concrete tensile damage
0.2538286015510176 (10x) and 0.9524655488340084 (20x). Every slot had nonzero
tensile damage. Steel accumulated plastic strain and concrete compressive damage
remained zero. This is internal constitutive state, not measured damage or proof
that these synthetic loads describe a usable design.

| Case | Dense median (s) | spsolve median (s) | Extended splu median (s) | spsolve/dense | Extended/dense |
| --- | ---: | ---: | ---: | ---: | ---: |
| 10x | 2.656878 | 2.696474 | 6.645493 | 1.014903 | 2.501241 |
| 20x | 3.169439 | 3.264495 | 7.252924 | 1.029991 | 2.288394 |

These are workload medians over three repetitions and ratios of medians. The
workload includes the public API and history production; interpreter startup,
parent detached validation and input generation have separate scopes. Coordinator
wall time was 128.048227797 seconds including its preflight, launches, waits and
detached validation/comparison, before report encoding. The sparse implementations
were slower on this small model; no generalized speedup is claimed.

## Retained-byte audit and limits

A separate audit checked 458 copied source files against both the frozen manifest
and current source, both input identities and 180 retained artifact identities.
It recomputed the 12 comparisons and directly checked the 12 repeat pairs. This
audit did not run another Newton solve. Worker and parent history validation
reassemble checkpoint transitions; neither is independent external validation.

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-planar-material-backends-cz0xf0xl`.
Its `inventory.json` SHA-256 is
`0f4bb9589dc58ef293ee158432477c4985b7685eb2dae41816949a57f911da4e`, covering
672 files / 17,054,280 bytes excluding the inventory itself. The packet retains
the protocol, generated inputs, source snapshot, all slots, audit script and
output. The adjacent JSON summary preserves per-slot material maxima and
unrounded timing values. These local originals are not embedded in Git.

No product code, solver tolerance, policy or release gate changed. Current-head
full CI, external reference comparison and AI net benefit are not established by
this experiment. Remaining planar coverage should distinguish steel yielding,
larger topologies and independent reference cases. The public load-control API
still generates a monotone path; cyclic validation must not be inferred from the
separate RC displacement-control work.
