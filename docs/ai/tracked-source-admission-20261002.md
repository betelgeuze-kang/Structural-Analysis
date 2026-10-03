# Complete tracked source admission

The Nightly overlay producer now checks the complete committed source checkout
before generated-leaf collection and again immediately before writing its seal.
Nightly and Product State also check their pristine checkout at admission;
Product State checks its consumer checkout after applying the authenticated
overlay. These checks complement the existing source/workflow/run identity,
raw artifact digest, semantic leaf replay, and exact DAG/provenance replay.

`scripts/verify_tracked_source_tree.py` requires HEAD and the full index to match
the declared commit tree, including index modes and stage zero. It rejects
assume-unchanged/skip-worktree flags, missing files, symlinks/submodules, mode
changes, staged changes, and visible untracked paths outside named receipts.
Every tracked file is explicitly hashed; the guard does not infer content
identity from Git's stat cache. It preserves the caller's index and flags.
Protected environment/credential names are rejected from metadata before any
content operation. Ignored runtime/cache files are outside this tracked-source
contract and do not become authenticated inputs through this check.

The checkout representation is canonical Git text content under the committed
attributes and controlled local checkout configuration. LF/CRLF equivalents,
including a full CRLF checkout of `.gitattributes`, are accepted; changed
attribute directives are rejected before hashing. Ignored or untracked root/
ancestor `.gitattributes` and Git `info/attributes` files are rejected from
metadata before hashing, so they cannot add `ident`, text, or filter rules
absent from the source tree. `core.attributesfile` is fixed to the null device.
Arbitrary clean filters are
rejected. External diff and textconv tools are never invoked. LFS clean/process
commands are disabled throughout. An authored canonical LFS v1 pointer may
remain a pointer or contain hydrated bytes only when their size and SHA-256
exactly match that committed pointer. Corrupted hydrated data is rejected
without requiring an installed LFS executable.

The producer permits content changes in exactly 22 existing generated paths:
the overlay's 14 sealed release files, its two regenerated external source
receipts, and six CLI-generated Markdown derivatives of developer-preview
readiness/RC status, release freshness, PM gate, action register, and closure
board. The consumer permits only the 14 sealed release-file modifications and
one named untracked canonical verification receipt. These exemptions grant no
permission to stage, delete, change modes, or replace a file with a symlink.
They do not authenticate the six unsealed Markdown derivatives. The existing
leaf/artifact validators retain raw digest and semantic authority for outputs.

This guard does not authenticate a hostile local Git installation/configuration,
prove independent physical correctness, or grant release authority. The
existing cross-environment diagnostic normalization, fail-closed cyclic PM
provenance, exact numerical assertions and solver tolerances are unchanged.
The full source inventory contains about 989 MB of tracked Git blobs at base
253d; explicit hashing therefore adds source I/O to each admission checkpoint.

Verification is confined to a new miniature-Git suite in
`tests/test_tracked_source_tree_guard.py` and a new read-only admission check of
the preserved base 253d checkout. Previously completed native/teacher/protected
fixtures and solver campaigns are not replayed. Local verification belongs to
these exact source bytes; final committed HEAD Nightly/CI and downstream live
run/artifact receipts remain required. Earlier c594 or base253d receipts do not
qualify this uncommitted implementation.
