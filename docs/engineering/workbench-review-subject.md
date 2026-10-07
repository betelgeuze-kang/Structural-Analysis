# Workbench reviewer draft subject

Workbench v2 reviewer drafts apply to the complete normalized case loaded by its case provider. The subject is SHA-256 of canonical JSON: sorted object keys, preserved array order, and the loaded provenance, model, analysis, residual history, product profile and retained extension fields. Changes to that content create a separate draft even when the source commit is unchanged.

The browser stores case-bound notes in a separate namespace under the existing review-draft prefix. Existing commit-only notes are preserved but never automatically attached to a loaded case. Returning to exactly the same case restores its note. Editing a note cannot change its subject or source commit. Invalid stored bindings are rejected; storage failures retain the existing explicit local/session persistence behavior.

Export recomputes the case digest and requires it to match the draft and source commit. The review envelope contains `review_subject.loaded_case`, `review_subject.case_sha256` and the draft's `caseSha256`, allowing a recipient to recompute the association. When hashing is unavailable, review editing and export remain unavailable.

This is an editable local reviewer note, not an authenticated signature, server audit log, automated verdict, engineering approval or release authorization. The subject does not include separately loaded RC jobs, native-frame results, candidate comparisons or remote evidence unless they are part of the loaded case itself. Those surfaces need their own explicit result-bound review contracts before these notes can be used as their decisions.
