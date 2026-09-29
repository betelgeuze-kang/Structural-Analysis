# Bounded diagnostic for the remaining 1024/2048 tensile-damage difference

The [completed comparison](planar-2048-refinement-20260920.md) leaves one failing group at 74 mm, E3:gauss-2, coarse cell 269. Its 1.0850199% relative tensile-damage difference exceeds the unchanged 1% screen.

`scripts/probe_planar_2048_witness.py` prepares a post-hoc common-coordinate diagnostic. It pins both original full JSON digests and their indexed representations. The existing bounded reader checks all forty accepted steps, checkpoint continuity, each payload and reconstruction of the original complete JSON. A pure extractor retains only the selected section strains and one coarse/two fine fiber states per target. It does not retain the full path in memory.

The diagnostic replays the original frozen concrete law at the 1,024-layer cell midpoint using each accepted section history. All forty coarse replays must exactly match accepted state and stress. Eighty local material integrations and zero structural solves/fits then decompose each field as:

`coarse - projected fine = (coarse - fine-history midpoint) + (fine-history midpoint - projected fine)`.

The derived fine-history midpoint is not an accepted solver fiber. The decomposition is algebraic and post-hoc; it is not causal attribution, independent physical validation, a replacement of the original projection screen, or authority to change tolerances or the public layer range.

## Execution state

Implementation only: the original large packets have **not** been scanned or replayed with this new driver. Wait for the running inner-label timing campaign to finish before the large diagnostic read. Freeze a committed source snapshot and record separate extraction/replay, enclosing-process and inventory costs, source pins and terminal status. Preserve failed attempts without rerunning numerical solves.

Focused extraction/coordinate and previous witness regression checks: **15 passed in 1.70 seconds**; Ruff and diff checks passed. The added tests use small fabricated records and a mock material for the new coordinate check; the pre-existing tests retain their tiny material-law checks. These tests ran while label generation was live, so that campaign must not be described as a completely idle-host measurement. No additional structural benchmark, policy fit or large packet audit ran concurrently.

## Admitted execution and preserved environment failure

After label generation, evaluation and their audits completed, the frozen observer source `42815feb1adc26694e7e4d51181fbbac09ab75f3` was invoked. The first observer process exited 1 in 1.684963227 seconds because its frozen source folder is not a Git checkout and the original material-source provenance helper invokes `git show`. This occurred before path extraction or material replay. No structural solve or fit occurred. The failed packet is preserved at `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-2048-witness-ru5230u2`, inventory `21cef042b4528dd972af936ef47cfed948101d0479ad954c40bcb4546d458cd5`.

A new direct-process launcher sets `GIT_DIR` to the repository's verified absolute Git directory while retaining the same frozen Python source, path digests, witness and tolerances. This corrects the provenance lookup environment without replacing material code. The new observer was admitted and confirmed live at `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-2048-witness-fixed-lx2g8vau` (controller PID 414876). Its final result remains pending at this entry. No numerical path was regenerated.
