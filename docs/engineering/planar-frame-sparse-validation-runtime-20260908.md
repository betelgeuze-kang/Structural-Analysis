# Sparse validation reuse and measured cost

Commit `2e114922dd5adbac7ea19e62c81352c44ae53b68` removes repeated work within
one synchronous CSR export or engineering-result construction. Every public
engineering-result validation still checks the current source, all accepted
epochs and an independent terminal recovery. The same 258-equation request took 85.453348168
seconds including validation, compared with the previously captured
140.417774206 seconds at `e3059804889d7f1af928c1f8bd6fef326e39c91d`.
Its complete result, validation, checkpoint and accepted-state inventory files
are byte-identical. This is one local observation per source, without repeated
or independently qualified performance evidence.

## Validation boundaries

Sparse-state validation still checks the problem and parent checkpoint, exact
immutable CSR arrays and hashes, vectors, every member response and material
state, prescribed coordinates and independent member scatter for all four global
matrices. It now returns its detached payload for the caller to hash or export.
The rescatter comparison uses exact canonical CSR arrays without constructing,
hashing and serializing a second receipt. Each later public call repeats source
validation; a successful earlier call supplies no cached authority.

Engineering recovery validates and serializes its source through the exact
portal/general class method before recovery, then repeats that whole-source
validation after recovery. Calling the class method directly preserves the
module validator even if an instance shadows `to_manifest`. Construction checks
its result against the immutable replay it just produced instead of performing
the same recovery twice. Public result validation and manifest export always
obtain a fresh replay. Adapter and compiler object identity, exact descriptors,
immutable arrays, metadata, hashes and schema checks remain required.

The general and portal adapter creators retain their second all-epoch stage
build. The solver's accepted-state binding retains both surrounding source
checks. Mutable early epochs can therefore still be rejected after terminal
work, including when an instance returns a forged manifest. No tolerance,
condition/pivot/backward-error policy, fallback, storage schema, result schema or
checkpoint format changed.

## Instrumented diagnosis

Separate cProfile runs execute the small two-step public portal request, including
analysis, public validation, dictionary conversion and checkpoint retrieval.
The final run uses the committed archive; it is not the earlier intermediate
candidate run. These invocation counts are diagnostic, not ordinary timings.

| Function scope | Before | Final source |
| --- | ---: | ---: |
| Complete stage-receipt builds | 11 | 6 |
| Accepted sparse assembly binding | 22 | 12 |
| Full sparse assembly validation | 99 | 56 |
| Individual CSR validation | 2,288 | 288 |
| Sparse accepted-state assembly | 27 | 16 |
| Native trial assembly | 39 | 28 |
| Terminal engineering recovery | 3 | 2 |
| General adapter validation | 10 | 5 |
| Public engineering-result validation | 2 | 1 |

The independent terminal replay remains in both construction and later public
validation. All four raw input/result/validation/checkpoint files from the final
profile equal the pre-change profile. A separate three-backend capture confirms
that the complete result, validation and checkpoint files for dense, existing
sparse and extended sparse are all byte-identical to their sealed `e30598048`
counterparts: nine output files from three new requests.

## Ordinary 258-equation observation

The unchanged model has 88 nodes, 87 members, 258 free and 264 global DOFs, with
load factors 0.5 and 1.0. Input SHA-256 is
`d6b1b6d449cbaa6c70f20ab263b672dd15e3f1a2db0e86543554a8f0732d0164`.
Both ordinary observations use the same 20,750-byte driver, SHA-256
`476568272c17e2578cc22af81e4a0d21b8fb8dad16a0098c9281578a67691923`,
configuration, Python, NumPy and SciPy versions. The baseline is the earlier
sealed ordinary run; it was not executed again for this follow-up.

| Observed quantity | Prior CSR source | Validation reuse |
| --- | ---: | ---: |
| Validation-inclusive wall time, seconds | 140.417774206 | 85.453348168 |
| CPU time in that interval, seconds | 140.409315266 | 85.447572110 |
| Process lifetime peak RSS, bytes | 164,720,640 | 163,520,512 |
| Selected global-matrix bytes per accepted step | 137,520 | 137,520 |
| Selected global-matrix bytes across both steps | 275,040 | 275,040 |

Wall time is about 39.14% lower in these two observations. It remains about
2.78 times the earlier 30.766834941-second extended-backend run that retained
dense accepted states. Removing this duplicate validation has not eliminated
the full CSR source-verification cost. See the
[preceding storage observation](planar-frame-sparse-state-runtime-20260908.md)
for that earlier implementation comparison and its different result bindings.

The wall/CPU interval covers analysis, public validation, result/report dictionary
conversion and checkpoint retrieval. Imports, source hashing, model parsing,
JSON encoding/persistence and retained-array accounting are excluded. The driver
retains the original producer path in both versions. Linux `ru_maxrss` instead
covers the whole process through post-run accounting, including imports and JSON
work. It is not a phase peak or the sum of selected arrays. Other owned solver
and browser tests had finished; lightweight artifact inspection also occurred.
There are no randomized repetitions, hardware controls, warmup distribution or
independent solver/operator receipts.

The complete model, result, validation, checkpoint and accepted-state inventory
files match the previous CSR run. This includes all public SI row groups,
convergence history and embedded engineering/result identities, plus CSR
pattern/numeric hashes and storage inventories for all four matrices in both
retained epochs. The inventory does not export their raw array bytes. There is
also no direct raw large-run J4 stage-receipt export, so a separate raw J4 hash
comparison is not claimed.
All six factorization diagnostics pass with no fallback or regularization, and
the source and input bytes remain unchanged across execution.

A separate final-source request forbids known global dense assembler aliases,
CSR/CSC/COO `toarray`/`todense`, and square `numpy.zeros/empty/ones` allocations
larger than 6 by 6. It converged with no blocked call. All five model/result/
validation/checkpoint/accepted-state files equal the ordinary final-source run.
Its 84.628556167 seconds wall, 84.620938852 seconds CPU and 169,324,544 bytes
process peak RSS are diagnostic only; they are not substituted for the ordinary
observation. The guard does not inspect native SuperLU allocations or establish
a sparse fill-in bound.

This follow-up performed eight new public requests outside tests: one pre-change,
one intermediate and one final-source profile; three final-source small-backend
captures; and one ordinary plus one guarded large request. Each has two authored
steps, for 16 total. Internal source/recovery replays are included in the request
cost and are not counted as new public requests. Copying the earlier ordinary
baseline or existing diagnostic files runs no additional analysis.

## Focused verification

Separate groups passed; they are not a repository-wide suite result:

- Sparse state/native assembly: 98 passed in 9.46 seconds, including canonical
  pre-change manifest hashes, repeated public-call mutation and detached export.
- New and existing engineering recovery: 33 passed in 84.91 seconds. The 22 new
  cases cover both source profiles, before/after replay, later and in-recovery
  early-epoch mutation, a forged instance manifest, source substitution and a
  fully rehashed one-ULP result change.
- Public sparse and durable integration: 40 passed in 23.63 seconds, including
  restart, rollback, source binding and durable service reconstruction.
- CI ownership and quality-gate registration: 40 passed in 0.44 seconds.

Ruff checks and final formatting/diff checks passed. One sparse-test formatting
drift was corrected after the initial combined format check; it changed no test
behavior. Separate local code review found no concrete source-boundary regression.
The existing Workbench 307-test result belongs to the preceding implementation;
no browser source changed or browser suite was rerun in this follow-up.

## Source and artifact record

The final archive contains the same 392 tracked Python/schema/model paths as the
prior sealed source, exported from `2e114922dd5adbac7ea19e62c81352c44ae53b68`.
Archive SHA-256 is
`ab020601f1a465210c849a1b92b81e69a6e1b7c7affbc9e227e8a9d5e6b0bf4f`.
The source-file inventory SHA-256 is
`07cc4d341cf79e7d9afe185df9acdaec92127e569735d29ea9f8fdca486612ea`.
The two production modules are the only archive-source differences from the
prior CSR implementation. Measurement receipts hash all 391 Python/schema files
before and after; the separate small model is also preserved.

Local artifacts are under
`/tmp/structural-sparse-validation-final.6f2qeqfy/`: `provenance.json`,
`source-files.json`, `small-compatibility.json`, `profile-comparison.json`,
`plain-comparison.json`, `guarded-comparison.json`, raw backend outputs, and
ordinary/guarded process receipts.
The original pre-change and intermediate candidate profiles are copied under
`diagnostics/` with their original protocols. The intermediate profile predates
the final adapter-identity guard and is not final-source evidence.

The separate local source audit passes 27 checks: all 392 files match their
Git blobs, archive and extracted bytes; only the two stated modules differ; the
prior sealed 448-file, 22,135,458-byte inventory remains intact. The copied
`source-git-audit.json` SHA-256 is
`af975f092a1c1944d1aa8672ee89df3b9c003cf0a0f6c01797547589ef6888d0`.

The final `sealed-inventory.json` covers 476 files and 23,000,742 bytes, excluding
itself. Its 98,981 bytes have SHA-256
`3d9a1e7c119a94f52c91b449bd535ec3b326f6ee3bd7e17c85ab514a905c5fe2`.
The complete file set, byte lengths and hashes were rechecked after sealing.
These are local artifact inventory sizes, not runtime memory or physical disk
traffic measurements. No files in the earlier sealed source/observation roots
were modified.

A second-agent [artifact audit](/tmp/structural-sparse-validation-independent-audit.json)
passes 62 checks, including 33 manifest-bound files, the 23 raw output/input
comparisons, 21 prior-profile copies, all nine profile counts and the request
accounting. Its 15,200 bytes have SHA-256
`f16f013c3bc39782d7f51d97a98ac0493891531f8d43452c985772e899867d54`.
This audit remains outside the sealed directory and performs no new analysis.

Broader repeated scale/memory verification, independent structural validation,
licensed corpora, hardware/operator acceptance and exact-head hosted integration
remain open. These local hashes and tests establish consistency within the
recorded scope; they do not grant independent provenance or release authority.
