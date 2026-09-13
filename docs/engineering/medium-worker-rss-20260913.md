# Linux medium-scale worker memory scope

The Linux medium-scale resource gate now reads `/proc/self/status` `VmHWM`
instead of `getrusage(RUSAGE_SELF).ru_maxrss`. The receipt explicitly identifies
the new measurement. Linux kernel documentation describes VmHWM as the process
peak resident set size: https://docs.kernel.org/filesystems/proc.html . This is
kernel RSS accounting, not exact allocation accounting or a process-tree total.
The 1 GiB limit and the enclosing worker wall-time gate are unchanged.

On this host, a minimal Python child inherited a much higher `ru_maxrss` after
its parent allocated memory, even though the child's current address-space peak
remained small. A further actual measurement through the new benchmark function
observed the following while the parent held 256 MiB:

| Observation | Current worker VmHWM | Legacy ru_maxrss |
| --- | ---: | ---: |
| Before parent allocation | 102,924,288 bytes | 102,924,288 bytes |
| Parent holds 268,435,456 bytes | 103,632,896 bytes | 283,901,952 bytes |

With that allocation still held, the real generated braced-truss tower worker
passed all gates and reported 121,503,744 bytes and 1.677 seconds for its execution
interval. These are observations on one host, not a speedup study or externally
attested resource qualification. This reproduces a mechanism that can explain
long-suite memory failures; the original failed full run did not retain its
individual resource payload, so exact attribution remains unproved.

Linux now requires one positive integer VmHWM entry in kB. Missing, duplicate,
malformed or unavailable observations fail rather than silently using a different
memory scope. Other Unix and Windows measurement implementations are unchanged.
The schema admits the explicit Linux label, the current-platform validator
requires it, and the attestation workflow pins the updated schema digest.
Prior Linux receipts with the legacy method are historical observations, not
new-source replay evidence. Old and new memory values must not be presented as
an implementation memory reduction.

Verification: 54 medium-scale execution tests passed. After updating the schema
pin, all six attestation workflow contract tests passed. Ruff and formatting
checks passed. An initial missing Path import was fixed before these results.
The full repository suite and new-head hosted workflows have not completed here.
Independent solver/operator verification and learned net benefit remain open.

The [observation summary](medium-worker-rss-20260913.summary.json) binds the raw
case and probe outputs and names the parent source plus uncommitted-patch scope.
