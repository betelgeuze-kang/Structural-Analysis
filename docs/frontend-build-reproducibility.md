# Frontend Build Reproducibility

The frontend shell now uses a pinned `package.json` plus a committed `package-lock.json` so clean checkouts can verify the build path deterministically.

## Commands

- `npm run verify:frontend-contract`
  - Reads only repo files and checks the expected manifest, lockfile, scripts, and build entrypoints.
  - Works even when `node_modules/` is missing.
- `npm run verify:frontend-smoke`
  - Runs the contract check, executes `npm ci`, and then runs `npm run build`.
  - This is the clean-checkout smoke path for CI or local verification.

## Expected Contract

- `package.json` contains only the dependencies needed by the active workbench entry.
- Dependency versions are pinned exactly instead of using floating `^` or `~` ranges.
- `package-lock.json` is the source of truth for deterministic installs.
- `vite.config.ts` declares the React/Vite build entry explicitly.
