#!/usr/bin/env node
// op-tripwire: detector-rule

import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const HOOK = join(HERE, 'secrets-tripwire.js');
const TEST_HOME = mkdtempSync(join(tmpdir(), 'secrets-tripwire-test-'));

function run(payload) {
  return spawnSync(process.execPath, [HOOK], {
    input: typeof payload === 'string' ? payload : JSON.stringify(payload),
    encoding: 'utf8',
    env: { ...process.env, HOME: TEST_HOME },
  });
}

const dummy = {
  onePassword: `ops_${'0'.repeat(44)}`,
  anthropic: `sk-ant-${'A'.repeat(24)}`,
  openai: `sk-proj-${'B'.repeat(24)}`,
  langfuse: `sk-lf-${'C'.repeat(20)}`,
  github: `github_pat_${'D'.repeat(24)}`,
  githubClassic: `ghp_${'G'.repeat(36)}`,
  slack: `xapp-${'E'.repeat(24)}`,
  slackClassic: `xoxb-${'H'.repeat(24)}`,
  supabase: `sb_secret_${'F'.repeat(20)}`,
  aws: `AKIA${'J'.repeat(16)}`,
  apify: `apify_api_${'K'.repeat(24)}`,
  firecrawl: `fc-${'L'.repeat(24)}`,
  google: `AIza${'M'.repeat(35)}`,
  database: `postgresql://user:${'N'.repeat(24)}@`,
  bearer: `Bearer ${'P'.repeat(24)}`,
  jwt: `eyJ${'Q'.repeat(20)}.${'R'.repeat(20)}.${'S'.repeat(20)}`,
};

let passed = 0;
function check(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`PASS ${name}`);
  } catch (error) {
    console.error(`FAIL ${name}: ${error.message}`);
    process.exitCode = 1;
  }
}

check('clean output is silent', () => {
  const result = run({
    hook_event_name: 'PostToolUse',
    tool_response: { stdout: 'build ok', stderr: '', interrupted: false, isImage: false },
  });
  assert.equal(result.status, 0);
  assert.equal(result.stdout, '');
});

check('malformed input is silent', () => {
  const result = run('{not-json');
  assert.equal(result.status, 0);
  assert.equal(result.stdout, '');
});

check('successful shell output is redacted without changing its shape', () => {
  const original = {
    stdout: `keys: ${Object.values(dummy).join(' ')}`,
    stderr: `nested ${dummy.openai}`,
    interrupted: false,
    isImage: false,
    metadata: { note: dummy.github },
  };
  const result = run({ hook_event_name: 'PostToolUse', tool_response: original });
  assert.equal(result.status, 0);
  const parsed = JSON.parse(result.stdout);
  const specific = parsed.hookSpecificOutput;
  assert.equal(specific.hookEventName, 'PostToolUse');
  assert.deepEqual(Object.keys(specific.updatedToolOutput), Object.keys(original));
  const serialized = JSON.stringify(parsed);
  for (const value of Object.values(dummy)) assert.ok(!serialized.includes(value));
  for (const name of [
    '1Password service token', 'Anthropic API key', 'OpenAI-style key',
    'Langfuse secret key', 'GitHub token', 'Slack token', 'Supabase secret',
    'AWS access key id', 'Apify token', 'Firecrawl key', 'Google API key',
    'DB URL with password', 'Bearer token', 'JWT',
  ]) assert.match(serialized, new RegExp(name));
  assert.equal((serialized.match(/OpenAI-style key/g) || []).length, 3);
});

check('private key contents are removed as a full block', () => {
  const privateKey = `-----BEGIN PRIVATE KEY-----\n${'Z'.repeat(64)}\n-----END PRIVATE KEY-----`;
  const result = run({
    hook_event_name: 'PostToolUse',
    tool_response: { stdout: privateKey, stderr: '', interrupted: false, isImage: false },
  });
  const parsed = JSON.parse(result.stdout);
  const serialized = JSON.stringify(parsed);
  assert.ok(!serialized.includes('Z'.repeat(64)));
  assert.equal(parsed.hookSpecificOutput.updatedToolOutput.stdout, '[REDACTED: private key block]');
});

check('failed shell errors emit names-only context and never repeat the value', () => {
  const result = run({
    hook_event_name: 'PostToolUseFailure',
    error: `command failed with ${dummy.anthropic}`,
  });
  assert.equal(result.status, 0);
  const parsed = JSON.parse(result.stdout);
  const specific = parsed.hookSpecificOutput;
  assert.equal(specific.hookEventName, 'PostToolUseFailure');
  assert.ok(!Object.prototype.hasOwnProperty.call(specific, 'updatedToolOutput'));
  assert.ok(!result.stdout.includes(dummy.anthropic));
  assert.match(specific.additionalContext, /Anthropic API key/);
});

// A script that BUILDS a DSN prints a template slot, not a password. Each slot below must pass
// through untouched, while a real password in the same position is still redacted.
const DSN_TEMPLATE_SLOTS = ['%s', '%(pw)s', '$PGPASSWORD', '${PGPASSWORD}', '$DB_PASSWORD', '${DB_PASSWORD}', '{password}', '<password>', '****'];
const dsn = (password) => ['postgresql://svc', password].join(':') + '@127.0.0.1:5432/app';

check('DSN template slots are not reported as leaked passwords', () => {
  for (const slot of DSN_TEMPLATE_SLOTS) {
    const result = run({
      hook_event_name: 'PostToolUse',
      tool_response: { stdout: `connect ${dsn(slot)}`, stderr: '', interrupted: false, isImage: false },
    });
    assert.equal(result.status, 0);
    assert.equal(result.stdout, '', `slot ${slot} was redacted`);
  }
});

check('a real DSN password is still redacted next to a template slot', () => {
  const realPassword = 'N0t' + 'A' + 'Slot' + '9'.repeat(8);
  for (const password of [realPassword, `${realPassword}%s`, `$${realPassword}!`, '$ecretPw9']) {
    const result = run({
      hook_event_name: 'PostToolUse',
      tool_response: { stdout: `${dsn('%s')} ${dsn(password)}`, stderr: '', interrupted: false, isImage: false },
    });
    assert.equal(result.status, 0);
    const serialized = result.stdout;
    assert.ok(!serialized.includes(password));
    assert.match(serialized, /DB URL with password/);
    assert.ok(serialized.includes(dsn('%s')), 'template slot next to a real password was altered');
  }
});

check('non-tool events are silent', () => {
  const result = run({
    hook_event_name: 'SessionStart',
    tool_response: { stdout: dummy.openai },
  });
  assert.equal(result.status, 0);
  assert.equal(result.stdout, '');
});

rmSync(TEST_HOME, { recursive: true, force: true });
if (!process.exitCode) console.log(`${passed}/${passed} tripwire tests passed`);
