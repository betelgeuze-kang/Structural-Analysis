import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { validate } from '../scripts/validate-ai-worker-output.mjs';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const cursorWrapper = path.join(repoRoot, 'scripts', 'ai-worker-cursor.sh');
const opencodeWrapper = path.join(repoRoot, 'scripts', 'ai-worker-opencode.sh');
const childSpawnProbe = spawnSync('bash', ['-lc', 'exit 0'], { encoding: 'utf8' });
const spawnBackedTest =
  !childSpawnProbe.error && childSpawnProbe.status === 0 ? test : test.skip;

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

function makeMockCommand(binDir, name, output, exitCode = 0) {
  const commandPath = path.join(binDir, name);
  fs.writeFileSync(
    commandPath,
    `#!/usr/bin/env bash
cat <<'WORKER_OUTPUT'
${output}
WORKER_OUTPUT
exit ${exitCode}
`,
    { mode: 0o755 },
  );
  return commandPath;
}

function makeModelCheckingMockOpencode(binDir, expectedModel) {
  const commandPath = path.join(binDir, 'opencode');
  fs.writeFileSync(
    commandPath,
    `#!/usr/bin/env bash
case "\${1:-}" in
  models)
    printf '%s\\n' '${expectedModel}'
    ;;
  run)
    seen=''
    while [ "$#" -gt 0 ]; do
      if [ "$1" = '--model' ]; then
        seen="\${2:-}"
        break
      fi
      shift
    done
    if [ "$seen" != '${expectedModel}' ]; then
      echo 'unexpected model' >&2
      exit 9
    fi
    cat <<'WORKER_OUTPUT'
${validWorkerOutput}
WORKER_OUTPUT
    ;;
  *)
    echo 'unexpected opencode args' >&2
    exit 2
    ;;
esac
`,
    { mode: 0o755 },
  );
  return commandPath;
}

function makeQuotaExhaustedMockOpencode(binDir, expectedModel) {
  const commandPath = path.join(binDir, 'opencode');
  fs.writeFileSync(
    commandPath,
    `#!/usr/bin/env bash
case "\${1:-}" in
  models)
    printf '%s\\n' '${expectedModel}'
    ;;
  run)
    echo 'usage limit exhausted for this billing period' >&2
    exit 42
    ;;
  *)
    echo 'unexpected opencode args' >&2
    exit 2
    ;;
esac
`,
    { mode: 0o755 },
  );
  return commandPath;
}

function makeModelCheckingMockCursor(binDir, expectedModel) {
  const commandPath = path.join(binDir, 'cursor-agent');
  fs.writeFileSync(
    commandPath,
    `#!/usr/bin/env bash
seen=''
while [ "$#" -gt 0 ]; do
  if [ "$1" = '--model' ]; then
    seen="\${2:-}"
    break
  fi
  shift
done
if [ "$seen" != '${expectedModel}' ]; then
  echo 'unexpected cursor model' >&2
  exit 9
fi
cat <<'WORKER_OUTPUT'
${validWorkerOutput}
WORKER_OUTPUT
`,
    { mode: 0o755 },
  );
  return commandPath;
}

function makeFlakyNetworkMockCursor(binDir, failCount) {
  const commandPath = path.join(binDir, 'cursor-agent');
  const statePath = path.join(binDir, 'cursor-agent-attempts');
  fs.writeFileSync(
    commandPath,
    `#!/usr/bin/env bash
state='${statePath}'
attempt=0
if [ -f "$state" ]; then
  attempt="$(cat "$state")"
fi
attempt=$((attempt + 1))
printf '%s\\n' "$attempt" > "$state"
if [ "$attempt" -le ${failCount} ]; then
  echo 'Error: [unavailable] getaddrinfo EAI_AGAIN api2.cursor.sh' >&2
  exit 1
fi
cat <<'WORKER_OUTPUT'
${validWorkerOutput}
WORKER_OUTPUT
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

function wrapperEnv(fixture) {
  return {
    ...process.env,
    PATH: `${fixture.binDir}:${process.env.PATH || ''}`,
    AI_WORKER_OUTPUT_DIR: fixture.outDir,
    CURSOR_AGENT_MODEL: 'mock',
    OPENCODE_MODEL: 'mock',
    AI_WORKER_OPENCODE_MODEL_CHECK: '0',
  };
}

function runWrapper(wrapper, fixture, env = wrapperEnv(fixture)) {
  return spawnSync(wrapper, [fixture.prompt], {
    cwd: repoRoot,
    encoding: 'utf8',
    env,
  });
}

test('accepts concise worker output and writes canonical headings', () => {
  const raw = `# ${validWorkerOutput.replace('Test results', '## Test results').replace('Failed tests', 'Failed tests:')}`;

  const sanitized = validate(raw, 16000);

  assert.match(sanitized, /^## Changed files\n\n- scripts\/example.py/m);
});

test('rejects extra prose before the first section', () => {
  const raw = `Here is the summary.

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
`;

  assert.throws(() => validate(raw, 16000), /non-empty content before the first allowed section/);
});

test('rejects full diffs', () => {
  const raw = `Changed files

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
`;

  assert.throws(() => validate(raw, 16000), /must not include full unified diffs/);
});

spawnBackedTest('cursor wrapper prints only validated summaries and removes valid raw output', () => {
  const fixture = wrapperFixture();
  makeMockCommand(fixture.binDir, 'cursor-agent', validWorkerOutput);

  const result = runWrapper(cursorWrapper, fixture);

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /^## Changed files\n\n- scripts\/example.py/m);
  assert.equal(fs.readdirSync(fixture.outDir).filter((name) => name.endsWith('.raw.md')).length, 0);
  assert.equal(fs.readdirSync(fixture.outDir).filter((name) => name.endsWith('.summary.md')).length, 1);
});

spawnBackedTest('cursor wrapper retries transient Cursor API DNS failures', () => {
  const fixture = wrapperFixture();
  makeFlakyNetworkMockCursor(fixture.binDir, 1);
  const env = wrapperEnv(fixture);
  env.AI_WORKER_CURSOR_RETRIES = '2';
  env.AI_WORKER_CURSOR_RETRY_DELAY_SECONDS = '0';

  const result = runWrapper(cursorWrapper, fixture, env);

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stderr, /transient network\/DNS failure on attempt 1/);
  assert.match(result.stdout, /^## Changed files\n\n- scripts\/example.py/m);
});

spawnBackedTest('cursor wrapper explains persistent Cursor API DNS failures', () => {
  const fixture = wrapperFixture();
  makeFlakyNetworkMockCursor(fixture.binDir, 5);
  const env = wrapperEnv(fixture);
  env.AI_WORKER_CURSOR_RETRIES = '1';
  env.AI_WORKER_CURSOR_RETRY_DELAY_SECONDS = '0';
  env.AI_WORKER_CURSOR_HOST_BRIDGE = 'disabled';

  const result = runWrapper(cursorWrapper, fixture, env);

  assert.equal(result.status, 1);
  assert.match(result.stderr, /failed after 2 attempt\(s\) due to network\/DNS access/);
  assert.match(result.stderr, /api2\.cursor\.sh/);
  assert.equal(result.stdout, '');
});

spawnBackedTest('cursor wrapper routes persistent DNS failures through host bridge when ready', () => {
  const fixture = wrapperFixture();
  makeFlakyNetworkMockCursor(fixture.binDir, 5);
  const bridgeDir = path.join(fixture.dir, 'bridge');
  const jobsDir = path.join(bridgeDir, 'jobs');
  const doneDir = path.join(bridgeDir, 'done');
  const outputFixture = path.join(fixture.dir, 'host-output.md');
  fs.mkdirSync(jobsDir, { recursive: true });
  fs.mkdirSync(doneDir);
  fs.writeFileSync(path.join(bridgeDir, 'host-bridge.ready'), '12345\n');
  fs.writeFileSync(outputFixture, validWorkerOutput);

  const bridgeHelper = spawn(
    'bash',
    [
      '-lc',
      `set -euo pipefail
for _ in $(seq 1 100); do
  set -- "$JOBS_DIR"/*.job
  if [ -d "$1" ]; then
    job_dir="$1"
    job_name="$(basename "$job_dir")"
    raw_output="$(cat "$job_dir/raw_output")"
    mkdir -p "$(dirname "$raw_output")" "$DONE_DIR/$job_name"
    cp "$OUTPUT_FIXTURE" "$raw_output"
    printf '0\\n' > "$DONE_DIR/$job_name/exit_code"
    exit 0
  fi
  sleep 0.05
done
exit 124
`,
    ],
    {
      env: {
        ...process.env,
        JOBS_DIR: jobsDir,
        DONE_DIR: doneDir,
        OUTPUT_FIXTURE: outputFixture,
      },
      stdio: 'ignore',
    },
  );

  const env = wrapperEnv(fixture);
  env.AI_WORKER_CURSOR_RETRIES = '1';
  env.AI_WORKER_CURSOR_RETRY_DELAY_SECONDS = '0';
  env.AI_WORKER_CURSOR_HOST_BRIDGE_DIR = bridgeDir;
  env.AI_WORKER_CURSOR_HOST_BRIDGE_TIMEOUT_SECONDS = '5';
  env.AI_WORKER_CURSOR_HOST_BRIDGE_POLL_SECONDS = '1';

  try {
    const result = runWrapper(cursorWrapper, fixture, env);

    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stderr, /routed to host bridge job/);
    assert.match(result.stdout, /^## Changed files\n\n- scripts\/example.py/m);
  } finally {
    bridgeHelper.kill();
  }
});

spawnBackedTest('opencode wrapper prints only validated summaries and removes valid raw output', () => {
  const fixture = wrapperFixture();
  makeMockCommand(fixture.binDir, 'cursor-agent', validWorkerOutput);

  const result = runWrapper(opencodeWrapper, fixture);

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /^## Changed files\n\n- scripts\/example.py/m);
  assert.equal(fs.readdirSync(fixture.outDir).filter((name) => name.endsWith('.raw.md')).length, 0);
  assert.equal(fs.readdirSync(fixture.outDir).filter((name) => name.endsWith('.summary.md')).length, 1);
});

spawnBackedTest('opencode wrapper routes assignment to Cursor composer-2.5', () => {
  const fixture = wrapperFixture();
  makeModelCheckingMockCursor(fixture.binDir, 'composer-2.5');
  const env = wrapperEnv(fixture);
  delete env.OPENCODE_MODEL;
  delete env.AI_WORKER_OPENCODE_MODEL;
  delete env.CURSOR_AGENT_MODEL;
  delete env.AI_WORKER_OPENCODE_ASSIGNMENT_CURSOR_MODEL;
  env.AI_WORKER_OPENCODE_MODEL_CHECK = '1';
  env.AI_WORKER_OPENCODE_NETWORK_PREFLIGHT = '0';
  env.AI_WORKER_OPENCODE_XDG_DATA_HOME = path.join(fixture.dir, 'xdg');

  const result = runWrapper(opencodeWrapper, fixture, env);

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stderr, /OpenCode worker assignment is routed to Cursor model composer-2\.5/);
  assert.match(result.stdout, /^## Changed files\n\n- scripts\/example.py/m);
});

spawnBackedTest('opencode assignment routing ignores exhausted opencode and uses Cursor composer-2.5', () => {
  const fixture = wrapperFixture();
  makeQuotaExhaustedMockOpencode(fixture.binDir, 'opencode-go/deepseek-v4-pro');
  makeModelCheckingMockCursor(fixture.binDir, 'composer-2.5');
  const env = wrapperEnv(fixture);
  delete env.OPENCODE_MODEL;
  delete env.AI_WORKER_OPENCODE_MODEL;
  delete env.CURSOR_AGENT_MODEL;
  delete env.AI_WORKER_OPENCODE_ASSIGNMENT_CURSOR_MODEL;
  env.AI_WORKER_OPENCODE_MODEL_CHECK = '1';
  env.AI_WORKER_OPENCODE_NETWORK_PREFLIGHT = '0';
  env.AI_WORKER_OPENCODE_XDG_DATA_HOME = path.join(fixture.dir, 'xdg');

  const result = runWrapper(opencodeWrapper, fixture, env);

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stderr, /OpenCode worker assignment is routed to Cursor model composer-2\.5/);
  assert.match(result.stdout, /^## Changed files\n\n- scripts\/example.py/m);
});

spawnBackedTest('wrapper rejects invalid worker output without printing raw output', () => {
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
