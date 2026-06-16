import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const validator = path.join(repoRoot, 'scripts', 'validate-ai-worker-output.mjs');
const cursorWrapper = path.join(repoRoot, 'scripts', 'ai-worker-cursor.sh');
const opencodeWrapper = path.join(repoRoot, 'scripts', 'ai-worker-opencode.sh');

const validWorkerOutput = `Changed files

- scripts/example.py

Test results

- pytest tests/test_example.py -q: passed

Failed tests

- None

Core diff summary

- Added output validation around worker summaries.

Blockers

- None
`;

function tempFixture(contents) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-worker-output-'));
  const input = path.join(dir, 'worker.md');
  const summary = path.join(dir, 'summary.md');
  fs.writeFileSync(input, contents);
  return { input, summary };
}

function runValidator(args) {
  return spawnSync(process.execPath, [validator, ...args], {
    cwd: repoRoot,
    encoding: 'utf8',
  });
}

function makeMockCommand(binDir, name, output, exitCode = 0) {
  const commandPath = path.join(binDir, name);
  fs.writeFileSync(
    commandPath,
    `#!/usr/bin/env bash
cat >/dev/null || true
cat <<'WORKER_OUTPUT'
${output}
WORKER_OUTPUT
exit ${exitCode}
`,
    { mode: 0o755 },
  );
  return commandPath;
}

function wrapperFixture() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-worker-wrapper-'));
  const binDir = path.join(dir, 'bin');
  const outDir = path.join(dir, 'worker-output');
  fs.mkdirSync(binDir);
  fs.mkdirSync(outDir);
  const prompt = path.join(dir, 'prompt.md');
  fs.writeFileSync(prompt, 'Goal: keep output concise\n');
  return { dir, binDir, outDir, prompt };
}

function runWrapper(wrapper, fixture) {
  return spawnSync(wrapper, [fixture.prompt], {
    cwd: repoRoot,
    encoding: 'utf8',
    env: {
      ...process.env,
      PATH: `${fixture.binDir}:${process.env.PATH || ''}`,
      AI_WORKER_OUTPUT_DIR: fixture.outDir,
      CURSOR_AGENT_MODEL: 'mock',
      OPENCODE_MODEL: 'mock',
    },
  });
}

test('accepts concise worker output and writes canonical headings', () => {
  const { input, summary } = tempFixture(`# ${validWorkerOutput.replace('Test results', '## Test results').replace('Failed tests', 'Failed tests:')}`);

  const result = runValidator(['--sanitize-out', summary, input]);

  assert.equal(result.status, 0, result.stderr);
  assert.match(fs.readFileSync(summary, 'utf8'), /^## Changed files\n\n- scripts\/example.py/m);
});

test('rejects extra prose before the first section', () => {
  const { input } = tempFixture(`Here is the summary.

Changed files

- scripts/example.py

Test results

- passed

Failed tests

- None

Core diff summary

- Small change.

Blockers

- None
`);

  const result = runValidator([input]);

  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /non-empty content before the first allowed section/);
});

test('rejects full diffs', () => {
  const { input } = tempFixture(`Changed files

- scripts/example.py

Test results

- passed

Failed tests

- None

Core diff summary

diff --git a/scripts/example.py b/scripts/example.py
@@ -1 +1 @@

Blockers

- None
`);

  const result = runValidator([input]);

  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /must not include full unified diffs/);
});

test('cursor wrapper prints only validated summaries and removes valid raw output', () => {
  const fixture = wrapperFixture();
  makeMockCommand(fixture.binDir, 'cursor-agent', validWorkerOutput);

  const result = runWrapper(cursorWrapper, fixture);

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /^## Changed files\n\n- scripts\/example.py/m);
  assert.equal(fs.readdirSync(fixture.outDir).filter((name) => name.endsWith('.raw.md')).length, 0);
  assert.equal(fs.readdirSync(fixture.outDir).filter((name) => name.endsWith('.summary.md')).length, 1);
});

test('opencode wrapper prints only validated summaries and removes valid raw output', () => {
  const fixture = wrapperFixture();
  makeMockCommand(fixture.binDir, 'opencode', validWorkerOutput);

  const result = runWrapper(opencodeWrapper, fixture);

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /^## Changed files\n\n- scripts\/example.py/m);
  assert.equal(fs.readdirSync(fixture.outDir).filter((name) => name.endsWith('.raw.md')).length, 0);
  assert.equal(fs.readdirSync(fixture.outDir).filter((name) => name.endsWith('.summary.md')).length, 1);
});

test('wrapper rejects invalid worker output without printing raw output', () => {
  const fixture = wrapperFixture();
  makeMockCommand(fixture.binDir, 'cursor-agent', 'Here is a long unstructured answer.');

  const result = runWrapper(cursorWrapper, fixture);
  const rawFiles = fs.readdirSync(fixture.outDir).filter((name) => name.endsWith('.raw.md'));

  assert.equal(result.status, 3);
  assert.equal(result.stdout, '');
  assert.match(result.stderr, /failed format validation/);
  assert.equal(rawFiles.length, 1);
  assert.equal(fs.statSync(path.join(fixture.outDir, rawFiles[0])).mode & 0o777, 0o600);
});
