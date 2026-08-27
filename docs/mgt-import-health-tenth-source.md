# MGT Import Health Tenth-Source Supplement

This supplemental lane closes the **technical** MGT import-health breadth target
at 10/10 without changing the conservative 9/10 tracked-corpus statement in
`mgt-import-health-current-source.md`.

The tenth case is
`dc8r207/Designs_All@7aa8fa09c00028cbba495b59bafa4c5b7755c034`,
`Xen Jakaria/Midas Practice/Staad Pro Models/With Meshing/Chadnimukha_2vent_mks_mm_unit.mgt`.
The workflow acquires it from the commit-pinned `raw.githubusercontent.com` URL
at runtime. It rejects redirects, a changed host/path/commit, and mismatched
SHA-256, byte length, or Git blob ID. The raw bytes exist only in a temporary
directory and are deleted before the JSON-only evidence artifact is assembled.

The same hosted run executes the nine-case core corpus and the supplemental
case, then requires uniqueness across case ID, lineage, source SHA-256,
comment-insensitive record fingerprint, and normalized model identity. The
tenth case is a clean parser pass with 5,184 independently scanned data rows,
zero unsupported or omitted rows, normalized node/element ID equality, and two
negative silent-loss checks. The combined technical summary is:

- 10/10 executed case contracts;
- 10/10 record-accounting checks;
- 10/10 silent-loss negative checks;
- 3 clean and 7 dirty cases; and
- 0/10 reviewed rights records.

## Local exact-source replay

From a clean checkout with network access:

```bash
source_sha="$(git rev-parse HEAD)"
python scripts/build_mgt_import_health_tenth_source_receipt.py \
  --source-commit-sha "$source_sha" \
  --fail-technical-blocked
python scripts/build_mgt_import_health_tenth_source_receipt.py \
  --source-commit-sha "$source_sha" \
  --check-bundle-only
python scripts/build_mgt_import_health_tenth_source_receipt.py \
  --source-commit-sha "$source_sha" \
  --check
```

The bundle-only check validates the copied core-nine reports, tenth report, and
their hash manifest without consulting the old core `.ci` output or the network;
it is explicitly nonfresh. The full check reruns the tracked core nine and
reacquires and reparses the tenth source. It compares complete parser-report
semantics after removing only timestamps and runtime paths, so coherently
rewriting a report and its receipt hashes is rejected. Cached verification JSON
is not accepted as a substitute for the fresh check. The GitHub-hosted workflow additionally
attests the combined receipt to the exact `main` source digest, main ref, and
immutable signer workflow while denying self-hosted runners.

## Authority boundary

The public source repository has no recorded license. Public readability is not
a redistribution or commercial-use grant. Therefore raw redistribution,
commercial use, product legal approval, independent reproduction, solver/design
authority, and release authority remain false even when the technical 10/10
receipt passes. Closing those claims requires an explicit rights basis and the
separate independent-operator and release gates; this technical supplement does
not infer them.
