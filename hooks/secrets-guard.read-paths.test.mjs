#!/usr/bin/env node
// op-tripwire: detector-rule
// Read-route and shared-category tests for secrets-guard.js (R-774 review corrections F-1, F-2, F-3).
// Run: `node hooks/secrets-guard.read-paths.test.mjs`
//
// Everything runs against a disposable directory of synthetic, content-free files. The hook is
// only ever fed PreToolUse JSON; no test opens a target for content, and the unreadable-mode
// cases prove the hook itself does not either (it uses metadata only). POSIX behavior is covered
// here; Windows interpretation is a separate, unexecuted gate (see docs/windows-read-walkthrough.md).

import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import fs from 'node:fs';
import os from 'node:os';

const HOOK = join(dirname(fileURLToPath(import.meta.url)), 'secrets-guard.js');
const failures = [];
let checks = 0;

function run(toolName, toolInput, cwd) {
  const r = spawnSync('node', [HOOK], { input: JSON.stringify({ tool_name: toolName, tool_input: toolInput }), encoding: 'utf8', cwd });
  if (r.status !== 0 || (r.stderr || '').trim()) throw new Error(`hook crashed: ${r.status} ${r.stderr}`);
  return { decision: /"permissionDecision":"deny"/.test(r.stdout) ? 'deny' : 'allow', stdout: r.stdout };
}
const readOf = (file_path, cwd) => run('Read', { file_path }, cwd);
const shellOf = (command, tool = 'Bash') => run(tool, { command });
function check(label, ok, detail = '') {
  checks++;
  if (!ok) { failures.push(label); console.error(`FAIL ${label}${detail ? `\n  ${detail}` : ''}`); }
}
function expect(label, got, want) { check(label, got === want, `expected ${want}, got ${got}`); }

// ---- F-1: exact template exceptions on shell path arguments --------------------------------
const SHELL_CASES = [
  // restored legitimate reads
  ['head -n 5 .env.example', 'allow'], ['cat -n .env.example', 'allow'],
  ['cat README.md .env.example', 'allow'], ['cat .env.example .env.sample', 'allow'],
  ['cat -- .env.example', 'allow'], ['cat --number .env.example', 'allow'],
  ['tail -n 2 .env.sample .env.template .env.dist', 'allow'],
  ['cat ./.env.example', 'allow'], ['cat config/.env.example', 'allow'],
  ['cat "dir with space/.env.example"', 'allow'], ["cat 'dir with space/.env.template'", 'allow'],
  ['cat ".env.example"', 'allow'], ['cat < .env.example', 'allow'], ['cat <.env.sample', 'allow'],
  ['cat --foo=.env.example', 'allow'], ['cat .env.example | head -n 3', 'allow'],
  // misleading suffixes and mixed protected/template reads stay denied
  ['cat .env.example.local', 'deny'], ['cat .env.example2', 'deny'], ['cat .env.example .env', 'deny'],
  ['cat .env .env.example', 'deny'], ['head -n 5 .env.example .env.local', 'deny'],
  ['cat .env.example.bak', 'deny'], ['cat .env.exampl', 'deny'], ['cat prod.env.example', 'deny'],
  ['cat --foo=.env.example.local', 'deny'], ['cat "dir with space/.env"', 'deny'],
  ['cat "dir with space/.env.example" .env', 'deny'], ['cat < .env.example.local', 'deny'],
  ['cat .env.example/.env', 'deny'], ['head -n 5 x/.env.example.local', 'deny'],
];
for (const [command, want] of SHELL_CASES) expect(`F-1 shell: ${command}`, shellOf(command).decision, want);
for (const [command, want] of [
  ['Get-Content .env.example', 'allow'], ['Get-Content -Path .env.example', 'allow'],
  ['Get-Content .env.example .env.sample', 'allow'], ['Get-Content .env.example.local', 'deny'],
  ['Get-Content .env.example .env', 'deny'],
]) expect(`F-1 powershell: ${command}`, shellOf(command, 'PowerShell').decision, want);

// ---- F-2: resolution on POSIX ---------------------------------------------------------------
const root = fs.realpathSync(fs.mkdtempSync(join(os.tmpdir(), 'guard-read-paths-')));
const p = (...parts) => join(root, ...parts);
// Traversal spellings must reach the hook uncollapsed, so they are built with a plain join.
const raw = (...parts) => [root, ...parts].join('/');
const restore = [];
try {
  fs.mkdirSync(p('box', 'secrets', 'inner'), { recursive: true });
  fs.mkdirSync(p('ord'));
  fs.mkdirSync(p('plain'));
  fs.writeFileSync(p('ordinary.txt'), 'x\n');
  fs.writeFileSync(p('.env'), 'x\n');
  fs.writeFileSync(p('box', 'secrets', 'outer.txt'), 'x\n');
  fs.writeFileSync(p('box', 'secrets', 'inner', 'deep.txt'), 'x\n');
  fs.symlinkSync('.env', p('link-env'));
  fs.symlinkSync('ordinary.txt', p('link-ordinary'));
  fs.symlinkSync(p('box', 'secrets'), p('link-secrets-dir'));
  fs.symlinkSync(p('box', 'secrets', 'inner'), p('ord', 'lnk'));
  fs.symlinkSync('link-env', p('chain-a'));       // chain-a -> link-env -> .env
  fs.symlinkSync('loop-b', p('loop-a')); fs.symlinkSync('loop-a', p('loop-b'));
  fs.mkdirSync(p('tpl'));
  fs.symlinkSync(p('.env'), p('tpl', '.env.example')); // template-named link to a protected file

  // metadata-only: an unreadable ordinary file must still be classified (allowed) without error
  fs.writeFileSync(p('unreadable.txt'), 'x\n'); fs.chmodSync(p('unreadable.txt'), 0o000);
  restore.push([p('unreadable.txt'), 0o600]);

  const abs = p; // alias for readability
  expect('F-2 ordinary file allowed', readOf(abs('ordinary.txt')).decision, 'allow');
  expect('F-2 symlink to ordinary file allowed', readOf(abs('link-ordinary')).decision, 'allow');
  expect('F-2 unreadable ordinary file classified without being opened', readOf(abs('unreadable.txt')).decision, 'allow');
  expect('F-2 direct protected path denied', readOf(abs('.env')).decision, 'deny');
  expect('F-2 symlink to protected file denied', readOf(abs('link-env')).decision, 'deny');
  expect('F-2 chained symlink to protected file denied', readOf(abs('chain-a')).decision, 'deny');
  expect('F-2 template-named symlink to protected file denied', readOf(abs('tpl', '.env.example')).decision, 'deny');
  expect('F-2 symlinked parent directory (secrets) denied', readOf(abs('link-secrets-dir', 'outer.txt')).decision, 'deny');
  expect('F-2 missing file under symlinked secrets directory denied', readOf(abs('link-secrets-dir', 'missing.txt')).decision, 'deny');
  expect('F-2 missing protected name denied', readOf(abs('nope', '.env')).decision, 'deny');
  expect('F-2 missing ordinary name allowed', readOf(abs('nope', 'notes.txt')).decision, 'allow');
  // leading // and /// are ordinary POSIX spellings of the same absolute path
  for (const [lead, label] of [['/', '//'], ['//', '///']]) {
    expect(`F-2 ${label} symlink to protected file denied`, readOf(lead + abs('link-env')).decision, 'deny');
    expect(`F-2 ${label} chained symlink denied`, readOf(lead + abs('chain-a')).decision, 'deny');
    expect(`F-2 ${label} symlinked secrets parent denied`, readOf(lead + abs('link-secrets-dir', 'outer.txt')).decision, 'deny');
    expect(`F-2 ${label} direct protected denied`, readOf(lead + abs('.env')).decision, 'deny');
    expect(`F-2 ${label} ordinary file allowed`, readOf(lead + abs('ordinary.txt')).decision, 'allow');
  }
  // traversal whose kernel resolution differs from lexical collapse: ord/lnk -> box/secrets/inner,
  // so ord/lnk/../outer.txt is box/secrets/outer.txt although the lexical form is ord/outer.txt.
  expect('F-2 symlink traversal resolving into secrets denied', readOf(raw('ord', 'lnk', '..', 'outer.txt')).decision, 'deny');
  expect('F-2 // traversal denied', readOf('/' + raw('ord', 'lnk', '..', 'outer.txt')).decision, 'deny');
  expect('F-2 relative traversal denied (cwd)', readOf('lnk/../outer.txt', abs('ord')).decision, 'deny');
  expect('F-2 relative ordinary allowed (cwd)', readOf('ordinary.txt', root).decision, 'allow');
  expect('F-2 relative symlink to protected denied (cwd)', readOf('link-env', root).decision, 'deny');
  expect('F-2 lexical secrets spelling before traversal denied', readOf(raw('box', 'secrets', '..', 'ordinary.txt')).decision, 'deny');
  expect('F-2 plain dotdot to ordinary file allowed', readOf(raw('plain', '..', 'ordinary.txt')).decision, 'allow');
  expect('F-2 plain dotdot to protected file denied', readOf(raw('plain', '..', '.env')).decision, 'deny');
  // unresolvable or unsafe metadata results stop safely instead of allowing
  const loop = readOf(abs('loop-a'));
  expect('F-2 symlink loop stops safely', loop.decision, 'deny');
  expect('F-2 non-directory path component stops safely', readOf(abs('ordinary.txt', 'x')).decision, 'deny');
  fs.mkdirSync(p('locked')); fs.writeFileSync(p('locked', 'a.txt'), 'x\n'); fs.chmodSync(p('locked'), 0o000);
  restore.push([p('locked'), 0o700]);
  if (process.getuid && process.getuid() !== 0)
    expect('F-2 unsearchable directory stops safely', readOf(abs('locked', 'a.txt')).decision, 'deny');
  // fixed, path-free, body-free denial output
  for (const target of [abs('link-env'), '/' + abs('link-env'), abs('loop-a'), raw('ord', 'lnk', '..', 'outer.txt')]) {
    const out = readOf(target).stdout;
    check('F-2 denial is fixed and path-free', out.includes('[secrets-guard hook]') && !out.includes(root) && !out.includes('link-env')
      && !out.includes('outer.txt') && !out.includes('loop-a'), out);
  }
  const denyMessages = new Set([abs('link-env'), '/' + abs('link-env'), abs('.env'), abs('link-secrets-dir', 'outer.txt')]
    .map((target) => {
      const { stdout } = readOf(target);
      return stdout ? JSON.parse(stdout).hookSpecificOutput.permissionDecisionReason : '(allowed: no denial message)';
    }));
  expect('F-2 protected-path denials share one fixed message', denyMessages.size, 1);

  // ---- F-3: Read/shell category matrix -------------------------------------------------------
  // [name, read, shell, note]. Rows where the two routes intentionally differ are labeled.
  const MATRIX = [
    ['.env', 'deny', 'deny'], ['prod.env', 'deny', 'deny'], ['local.env', 'deny', 'deny'],
    ['.env.production', 'deny', 'deny'], ['.env.local', 'deny', 'deny'], ['.env.d/x', 'deny', 'deny'],
    ['.env.example.local', 'deny', 'deny'], ['.env.example2', 'deny', 'deny'], ['prod.env.example', 'deny', 'deny'],
    ['aws-credentials.csv', 'deny', 'deny'], ['credentials', 'deny', 'deny'], ['credentials.json', 'deny', 'deny'],
    ['.aws/credentials', 'deny', 'deny'],
    ['id_rsa', 'deny', 'deny'], ['id_rsa.bak', 'deny', 'deny'], ['id_ed25519', 'deny', 'deny'],
    ['id_ecdsa', 'deny', 'deny'], ['.ssh/id_rsa', 'deny', 'deny'],
    ['mykey.pem', 'deny', 'deny'], ['mykey.pem.bak', 'deny', 'deny'], ['a.p12', 'deny', 'deny'],
    ['a.pfx', 'deny', 'deny'], ['a.jks', 'deny', 'deny'], ['a.keystore', 'deny', 'deny'],
    ['.env.example', 'allow', 'allow'], ['.env.sample', 'allow', 'allow'], ['.env.template', 'allow', 'allow'],
    ['.env.dist', 'allow', 'allow'], ['sub/.env.example', 'allow', 'allow'],
    ['.envrc', 'allow', 'allow'], ['environment.ts', 'allow', 'allow'], ['src/environment/config.ts', 'allow', 'allow'],
    ['README.md', 'allow', 'allow'], ['notes.txt', 'allow', 'allow'], ['credentials_old', 'deny', 'allow', 'Read keeps the reviewed credentials* name rule; shell uses a word boundary'],
    ['id_ed25519_work', 'allow', 'allow'], ['mykey.pemx', 'allow', 'allow'],
    // documented asymmetries
    ['id_rsa.pub', 'allow', 'deny', 'public half; the shell scan has always over-matched it'],
    ['secrets/x.txt', 'deny', 'allow', 'directory rule exists for Read and native deny only'],
    ['credentials/provider.ts', 'allow', 'deny', 'Read classifies the file name, not a source directory'],
  ];
  for (const [name, read, shell, note] of MATRIX) {
    const suffix = note ? ` (${note})` : '';
    expect(`F-3 Read ${name}${suffix}`, readOf(abs(...name.split('/'))).decision, read);
    expect(`F-3 shell cat ${name}${suffix}`, shellOf(`cat ${name}`).decision, shell);
  }
} finally {
  for (const [target, mode] of restore) { try { fs.chmodSync(target, mode); } catch { /* best effort */ } }
  fs.rmSync(root, { recursive: true, force: true });
}

console.log(`${checks - failures.length}/${checks} read-path checks passed`);
process.exit(failures.length ? 1 : 0);
