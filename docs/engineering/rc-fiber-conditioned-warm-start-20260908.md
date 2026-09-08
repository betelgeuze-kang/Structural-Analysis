# Model-conditioned RC fiber warm starts: local observation

Observed 2026-09-08 at committed source
`50987f7f02fdfc6dc700943915c8503f8ff123fb`.
This is a synthetic-family correctness and local runtime observation, not
independent physical validation or a production-promotion receipt.

## Result and representation change

All 12 measured strategy runs passed full-history response comparison and J1–J5
recovery, and all four separate reference episode checks passed. The conditioned
learned arm was slower than both reference Newton and deterministic secant in
both cases. No positive amortization projection is available, and this observation
does not justify changing the default strategy.

The legacy displacement/load-factor features alias different physical models at
the all-zero first step. Their fixed numeric coordinate-scale contract also prevents
training across different member lengths. The explicit `model_conditioning=True`
path now includes pre-analysis node geometry, actual reference nodal loads and
fiber positions/areas, with a separate versioned policy. Context fixes topology,
oriented connectivity, free DOFs, integration/fiber-kind layout and material laws.
The original v1 path and artifacts remain available unchanged by default.

Physical translations and rotations are solver coordinates multiplied by each
input's scale; rotation scale is the reciprocal of its declared model rotation
length. Training uses physical m/rad increments and inference divides by the
current scale. A review found that initially the duplicated model length and runtime
scale were not cross-checked. The committed implementation rejects that mismatch
before fitting and returns the parent fallback during inference, including at
zero-history genesis. Different valid scales for lengths 3 m and 4 m remain allowed.

## Frozen protocol and source

Original files are in `/tmp/structural-conditioned-observation.W0ZIyN/`.
`protocol.md`, `prepared-inputs.json`, six model files and the request were prepared
before execution. Source edits, tests and other owned solvers were stopped for the
measurement. The driver made one learning-process API call with a 900-second
limit; it completed successfully without retry or input/hyperparameter changes.

Both Git HEAD and clean tracked/untracked status were checked before and after.
Raw hashes of 2,025 tracked files under the source/test/script/example roots and
`pyproject.toml` matched; environment files and protected evidence state were excluded. All prepared
input bytes also matched. These checks and local coordination are not an external
attestation or proof of exclusive hardware use.

The base is `tests/fixtures/fiber_frame_candidate_process/base.json`: one serial RC
cantilever, two integration points and two concrete layers. Only length, width and
N2 FY reference load changed:

| Split | Length (m) | Width (m) | FY (kN) |
| --- | ---: | ---: | ---: |
| Train | 3 | .400 | -.8 |
| Train | 3 | .460 | -1.2 |
| Train | 4 | .400 | -1.2 |
| Train | 4 | .460 | -.8 |
| Validation interior | 3.25 | .415 | -1 |
| Holdout load OOD | 3.75 | .440 | -2 |

Group IDs are artificial labels within this one family. They do not prove independent
project/geometry/load-history provenance. Each case has two load steps, residual
tolerance `1e-10`, increment tolerance `1e-12`, and 40 maximum iterations. Ridge
`1e-6`, OOD margin `.1`, two repetitions and zero warmups were fixed in the v2
request. Guard/damping and response tolerances retain the existing defaults.

## Correctness and behavior

Six complete public collection cases produced 12 accepted samples; only the eight
train samples determine preprocessing, target scaling, weights and feature ranges.
The frozen policy was reused across both evaluation cases and repetitions. Each
case has three strategies and two repetitions, with two committed load steps per
run. Evaluation-label generation is charged even though its targets are not fitted.

The validation model was in range at both steps. All four learned step proposals
passed the physical residual guard with damping 1 and were executed as initial
guesses; their accepted relative residual was about .153053 versus the parent's
.5. The load-OOD model was detected at its first step and at all four evaluated
steps across repetitions. Its learned arm used reference starts, with no seeded
attempt. No failed seeded attempt or post-failure recovery was exercised in this
observation. Injected metadata/failure regression evidence remains separate.

Full-history comparison uses the predetermined response tolerances; J1–J5 recovery
and reported checkpoint identities do not by themselves establish separately saved
checkpoint byte parity. The producer's `checkpoint_bytes_exact` was true for the
four reference runs and two learned OOD runs, and false for four secant runs and
two in-range learned runs. All 12 passed elementwise response/history tolerances;
exact-byte equality is not substituted for that reported comparison. Original
checkpoint bytes/snapshots were not exported, so the later audit cannot independently
replay their full runtime chains. Hashes bind artifacts and declared sources, not
independent provenance, licensing or engineering authority.

## Runtime and cost

Verified end-to-end wall time includes the executed strategy and its full-path
verification. Attempted solver time is a nested, much smaller scope. Seconds below
show both repetitions' range and median; the last column is milliseconds.

| Case | Strategy | Minimum (s) | Median (s) | Maximum (s) | Attempted solver median (ms) |
| --- | --- | ---: | ---: | ---: | ---: |
| validation-interior | Reference Newton | 9.549763 | 9.556869 | 9.563975 | 27.322042 |
| validation-interior | Deterministic secant | 9.418372 | 9.423234 | 9.428095 | 22.360049 |
| validation-interior | Conditioned learned | 9.600136 | 9.631931 | 9.663725 | 27.448698 |
| holdout-load-ood | Reference Newton | 9.505214 | 9.510684 | 9.516155 | 27.122044 |
| holdout-load-ood | Deterministic secant | 9.370454 | 9.393098 | 9.415743 | 22.308961 |
| holdout-load-ood | Conditioned learned | 9.548036 | 9.549904 | 9.551772 | 27.482947 |

Learned-minus-secant median overhead is **0.208697 s** for validation and
**0.156806 s** for the load-OOD case. All four reference/secant amortization rows
have no positive observed saving and a null projected reuse count. The two-repeat
sample is small, and these are local observations of the frozen inputs.

Paired learned-minus-secant differences for repetitions 0/1 were
**+245.352543/+172.041868 ms** for validation and
**+181.318210/+132.292807 ms** for holdout. Learned-minus-reference differences
were **+99.749934/+50.373804 ms** and **+35.617634/+42.821763 ms**, respectively.
All paired differences were positive in this observation.

Data generation was **57.531225849 s**, including **0.007689770 s** of physical
split/compiled-feature preflight. The entire training call was **0.003670406 s**
(internal fitter measurement **0.003663395 s**). Thus the one-time generation plus
training charge is **57.534896255 s**. Evaluation was **116.042859501 s** and the
study interval **173.583443837 s**. Feature preflight is already inside generation;
internal fit time is already inside the training call.

The separate phase recorder includes report conversion and frozen-policy checks,
so its scopes are slightly larger than those internal intervals:

| Whole phase | Wall (s) | Current-process CPU (s) |
| --- | ---: | ---: |
| data_collection | 57.531788707 | 57.528506164 |
| evaluation | 116.047140357 | 116.039985693 |
| training_attempt | 0.004422119 | 0.004422492 |

The worker used **174.840395941 s CPU** through study
persistence, excluding resource-sidecar emission. The driver's API-call wall was
**175.033111775 s** and parent-only CPU
**0.039677407 s**, including worker launch/wait
and manifest persistence but excluding driver imports and source/input snapshots.
These nested wall/phase scopes must not be added together.

Worker peak RSS was **114,020,352 bytes
(108.738281 MiB)**, including imports and report
encoding. All phases and strategies shared that address space: per-phase and
per-strategy peaks remain unavailable. Bounded input reads totaled
**15,664 bytes** and the persisted study was
**676,554 bytes**. These are file-API scopes, not physical
disk traffic; resource-sidecar I/O is excluded. GPU time is unavailable for this
CPU-only path.

Total learned inference, including current-model feature preparation, was
0.002924472 s for validation and 0.002761908 s for holdout across four steps each.
Their AI guard times were 0.020026361 s (eight assemblies) and 0.000006440 s
(no assemblies). There is no separately measured OOD-only timer; it is included
in inference. The per-case guard total also includes deterministic secant guards.
Full-path verification across all strategies/repetitions occupied 56.989393010 s
and 56.694268877 s respectively; this field includes recovery verification and
response comparison. The solver intervals do not establish net savings
when that required validation work and inference/guard costs are included.

Environment recorded CPython 3.10.12, NumPy 1.26.4, SciPy 1.12.0 and Linux x86_64.
Thread runtime configuration and package version were not captured. The result
establishes no hardware/operator independence or general acceleration claim.

## Verification and retained artifacts

The earlier correctness fixture executed one worker and passed two real tests in
121.09 s: six collection cases, six evaluated strategy paths and two reference
episode checks. Its source revision field was a test fixture, so its timing is not
performance evidence. Its original temporary path was
`/tmp/pytest-of-betelgeuze/pytest-215/conditioned-study-inputs0/worker`.
That path was no longer present at the final retention audit; its disappearance
cause was not established. The earlier tests ran while it was available, but its
original bytes are not now retained. `correctness-retention.json` records this
limit. Saved final-regression/default-collector logs remain in `verification-logs/`;
the separate committed-source observation retains its complete original artifacts.
Final combined regressions passed **268 tests in 7.31 s** using those saved actual
artifacts, with one older real-process test deselected. A separate unchanged-default
collector regression passed **18 tests in 30.45 s**. Changed Python files (15)
passed Ruff and format checks, and the diff passed whitespace checks. These groups
have different scopes and are not summed as independent physical cases.

The observation's policy identity is
`sha256:616830e731867868bdb0a49a2a287eb3a1f8fa50d7e6ea0fedcd8120f0c1aeb0`;
study logical identity is `sha256:44d5ac8e0d839c34acd36303e1978b35e23e2670415ac0d27a2287e81f5b9f0b`.
Selected raw SHA-256 bindings are below. The committed-source observation's
original files are retained; logical identities and byte hashes have different
scopes. `artifact-manifest.json` seals **26 files / 1,776,013 bytes**, excluding
itself. The manifest is 4,791 bytes with raw SHA-256
`d2c4f653b1446e32adf547b8579bffffa6ef372a6ff9bf4269d010514dd959ff`.
Every listed size and byte hash was reread and verified after creation.

Local read-only audits passed 134 retained-byte/metadata consistency checks and
221 cost/scope checks, recorded in `integrity-audit.json` and `cost-audit.json`.
They checked policy/train membership, sample parents, runtime attempt/selection
bindings, coverage, OOD/seed counts and nested resource arithmetic, using the saved
reports. These audits executed no additional solver, training or worker and do not
provide independent physical replay or provenance attestation.

| Relative observation path | Bytes | Raw SHA-256 |
| --- | ---: | --- |
| `measurement/study.json` | 676554 | `fc506bc7cc3b5fb272530da8a081521e07021fe0d950b59208a1f1e918a83548` |
| `measurement/resources.json` | 4996 | `264c0118fdf3fb3faebdd3f192b1214655c907c968ba279145d36016950cc6e1` |
| `measurement/manifest.json` | 1010 | `507033782eebb8c16e3c4ca8a0c9417e858ebf3484afe1d1646ce50b7fbfb921` |
| `receipt.json` | 97922 | `9d83a31607c5c05599ad8b7decbeb48a3e5aafacfa53f60bf47eae79d28b761e` |
| `inputs/request.json` | 3417 | `3798bc11c7e4a89818184235282ba0cb2f8702e6d429b214c1ef0844e4b4ffc4` |
| `run.py` | 13200 | `4ec6188f79f71158866bb6edf533660ac968659747a083916d7f430a6ee017e4` |
| `source-before.json` | 408759 | `9c705aa425e6c156fc115beaca43d2b0abc697d6999c4af0dbe29cc8779e1ec0` |
| `source-after.json` | 408759 | `9c705aa425e6c156fc115beaca43d2b0abc697d6999c4af0dbe29cc8779e1ec0` |
| `integrity-audit.json` | 97954 | `cd638d2ed17e3c0739bde94df01fa6684fe282c2c9320f940e7c0996b23739c5` |
| `cost-audit.json` | 40899 | `8a83e2457269726e71452529df31d7278202fcfe93f572bfd3da788ba24efa81` |
| `correctness-retention.json` | 531 | `16e41df1309719f3f90575a6da3bed4eca57223275ffc7629190d28f2cd434aa` |

Independent corpora/provenance/licensing, generalization, net performance,
per-strategy resource observations, hosted exact-head checks and review remain
open. The bounded M4 process suite still needs a Workbench view of the whole
experiment's shared costs, oracle and per-arm resources; parsing its individual
comparison bundles does not provide that connection. The broader roadmap and
external validation/release gates remain open.
