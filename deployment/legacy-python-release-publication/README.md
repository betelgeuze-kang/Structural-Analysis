# Legacy Python/Node Release Publication

This directory is a rollback-only archive of the former branch-writing evidence resync and
GitHub Release publication automation. Files below this directory are outside
`.github/workflows` and `scripts`, so GitHub cannot dispatch them and normal product tooling does
not expose a live Python publisher.

The archive deliberately retains the original `contents: write`, publication, and `git push`
steps as deprecation evidence. They are not authority. A rollback requires an explicit human review
and an approved commit that restores the workflow and both helper scripts to their former
active paths; copying or executing archive files in place is unsupported.

Removal remains disallowed until the final C6 audit records the replacement publication process,
the rollback/deprecation window, and externally authorized image/package signing and import
receipts. The active native distribution and deployment paths neither import nor execute this
archive.
