# Evidence bundle (Workbench v2)

The Workbench reads release evidence from a published, **read-only** bundle under
`public/evidence/` rather than fetching repository internals at runtime. This
keeps the deployed app honest: it only ever displays what a verified bundle
contains, and it marks everything else as *unavailable* instead of inferring a
verdict.

## What the bundle is

```
public/evidence/
  manifest.json                 # schema_version, source_commit_sha, artifacts[]
  readiness/
    product-readiness.json      # copy of the protected source
    benchmark-breadth.json
    fresh-validation.json
    evidence-console-scope.json
    real-project-corpus.json
```

Each `manifest.artifacts[]` entry records:

- `id`, `label` — stable identifiers used by the UI;
- `path` — the copy inside the bundle;
- `source_path` — the original, read-only repository path;
- `sha256` — checksum of the exact source bytes;
- `read_only: true`.

## Protected source vs. public copy

- **Protected sources** live under `implementation/phase1/.../release_evidence/`.
  They are the system of record and are **never** edited by the bundle build.
- **Public copies** are byte-for-byte duplicates written to `public/evidence/`
  by the builder, with a checksum and the originating `source_path` preserved in
  the manifest. The copy is what ships to GitHub Pages.

The builder reads, hashes, and copies; it does not transform values. This is why
the UI can attribute every number to a `source_path` + `sha256` + commit.

## Single-commit rule (why builds fail)

A bundle must be **one consistent snapshot**. If the sources do not all share the
same `source_commit_sha`, the build fails:

```
evidence-bundle: FAIL — source commit mismatch — bundle must be a single
snapshot. Found 3 commits: c2b1b70d, b883c03e, 380df40d. ...
```

This is the current state of the repository: evidence was generated at different
commits, so a bundle cannot honestly be produced yet. The correct fix is to
**regenerate all evidence at one commit**, not to relax the gate.

Other hard gates:

- a source missing `source_commit_sha` fails the build;
- a source that is not valid JSON fails the build;
- a sensitive-data signal (email, credit-card-like number, or a secret-like key
  such as `password` / `api_key` / `private_key`) fails the build.

## Regenerating a single-commit bundle

1. Regenerate every protected source listed in the builder's `SOURCES` at the
   **same** commit (run the upstream validation/readiness jobs from one tree).
2. Commit those sources together so they share one `source_commit_sha`.
3. Dry-run the consistency check (writes nothing):

   ```bash
   npm run build:evidence-bundle -- --check
   ```

   Expect: `evidence-bundle: OK (check) — N sources at commit <sha>`.
4. Build the bundle:

   ```bash
   npm run build:evidence-bundle
   ```

   This writes `public/evidence/manifest.json` and the `readiness/*.json` copies.

## Contract test (offline, no network)

`scripts/verify-evidence-bundle-contract.mjs` proves the gates hold without
touching the repository. It runs the builder with `--check --root <fixture>`
against synthetic trees:

| fixture                | expectation |
| ---------------------- | ----------- |
| single-commit          | PASS        |
| mixed-commit           | BLOCKED     |
| sensitive-data         | BLOCKED     |
| missing source commit  | BLOCKED     |
| real repository sources| reported as-is (currently BLOCKED) |

```bash
npm run verify:evidence-bundle-contract
```

The `--root <dir>` builder option exists for this test only; production builds
always default to the repository root.

## BASE_URL / GitHub Pages

The app may be served from a subpath (e.g.
`https://<user>.github.io/Structural-Analysis/`). Evidence URLs are resolved
against `import.meta.env.BASE_URL` in
`src/workbench-v2/model/evidence/evidenceSources.ts`
(`evidenceManifestUrl` / `evidenceArtifactUrl`), so the manifest and artifacts
load correctly under the Pages base path as well as at the root during local
preview.

## When the bundle is absent

If `manifest.json` cannot be fetched, the Evidence Reader renders a single
`data-bundle-missing` / `data-wb2-unavailable` notice and **does not** infer any
readiness. No source cards and no positive release-ready verdict are shown. This
behaviour is asserted by the Workbench v2 E2E spec.
