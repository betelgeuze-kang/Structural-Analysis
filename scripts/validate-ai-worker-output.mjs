#!/usr/bin/env node
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

const allowedSections = [
  'Changed files',
  'Test results',
  'Failed tests',
  'Core diff summary',
  'Blockers',
];

const sectionLookup = new Map(
  allowedSections.map((section) => [section.toLowerCase(), section]),
);

function usage() {
  return [
    'usage: validate-ai-worker-output.mjs [--sanitize-out <path>] [--max-bytes <n>] <output-file|->',
    '',
    'Validates concise worker output. Allowed sections, in order:',
    ...allowedSections.map((section) => `- ${section}`),
  ].join('\n');
}

function parseArgs(argv) {
  const parsed = {
    file: undefined,
    sanitizeOut: undefined,
    maxBytes: Number.parseInt(process.env.AI_WORKER_OUTPUT_MAX_BYTES || '16000', 10),
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--sanitize-out') {
      parsed.sanitizeOut = argv[i + 1];
      i += 1;
    } else if (arg === '--max-bytes') {
      parsed.maxBytes = Number.parseInt(argv[i + 1] || '', 10);
      i += 1;
    } else if (arg === '--help' || arg === '-h') {
      console.log(usage());
      process.exit(0);
    } else if (!parsed.file) {
      parsed.file = arg;
    } else {
      throw new Error(`unexpected argument: ${arg}`);
    }
  }

  if (!parsed.file || !Number.isFinite(parsed.maxBytes) || parsed.maxBytes <= 0) {
    throw new Error(usage());
  }
  return parsed;
}

function fail(message) {
  const err = new Error(message);
  err.isValidationError = true;
  throw err;
}

function canonicalHeading(line) {
  const match = line.match(/^\s*(?:#{1,6}\s*)?(.+?)\s*:?\s*$/);
  if (!match) return undefined;
  return sectionLookup.get(match[1].trim().toLowerCase());
}

function stripAnsi(value) {
  return value.replace(/\x1B\[[0-?]*[ -/]*[@-~]/g, '');
}

export function validate(raw, maxBytes) {
  const byteLength = Buffer.byteLength(raw, 'utf8');
  if (byteLength > maxBytes) {
    fail(`worker output is ${byteLength} bytes; limit is ${maxBytes}`);
  }

  if (/```/.test(raw)) {
    fail('worker output must not contain fenced blocks');
  }
  if (/^diff --git /m.test(raw) || /^@@ .*@@/m.test(raw) || /^--- a\//m.test(raw) || /^\+\+\+ b\//m.test(raw)) {
    fail('worker output must not include full unified diffs');
  }

  const normalized = stripAnsi(raw).replace(/\r\n?/g, '\n').trimEnd();
  const lines = normalized.split('\n');
  const sections = [];
  let current = undefined;

  lines.forEach((line, index) => {
    if (line.length > 500) {
      fail(`line ${index + 1} is too long; concise summaries only`);
    }

    const heading = canonicalHeading(line);
    if (heading) {
      const expected = allowedSections[sections.length];
      if (heading !== expected) {
        fail(`section ${sections.length + 1} must be "${expected}", got "${heading}"`);
      }
      current = { heading, lines: [] };
      sections.push(current);
      return;
    }

    if (!current) {
      if (line.trim() !== '') {
        fail('non-empty content before the first allowed section');
      }
      return;
    }

    if (/^\s*#{1,6}\s+\S/.test(line)) {
      fail(`unexpected heading in section "${current.heading}"`);
    }
    current.lines.push(line);
  });

  if (sections.length !== allowedSections.length) {
    fail(`expected ${allowedSections.length} sections, found ${sections.length}`);
  }

  sections.forEach((section) => {
    const nonBlank = section.lines.filter((line) => line.trim() !== '');
    if (nonBlank.length === 0) {
      fail(`section "${section.heading}" must contain a concise value such as "None"`);
    }
    if (section.lines.length > 80) {
      fail(`section "${section.heading}" has ${section.lines.length} lines; concise summaries only`);
    }
  });

  return sections
    .map((section) => {
      const body = section.lines.join('\n').trim() || 'None';
      return `## ${section.heading}\n\n${body}`;
    })
    .join('\n\n')
    .concat('\n');
}

function main() {
  try {
    const args = parseArgs(process.argv.slice(2));
    const raw = args.file === '-' ? fs.readFileSync(0, 'utf8') : fs.readFileSync(args.file, 'utf8');
    const sanitized = validate(raw, args.maxBytes);
    if (args.sanitizeOut) {
      fs.writeFileSync(args.sanitizeOut, sanitized, { mode: 0o600 });
    }
  } catch (error) {
    const prefix = error.isValidationError ? 'Invalid worker output' : 'Worker output validator error';
    console.error(`${prefix}: ${error.message}`);
    process.exit(1);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}
