#!/usr/bin/env node
// hooks/refresh-guard.mjs
// Keep the USER-LEVEL secrets guard current, safely. This installs the canonical hooks into
// ~/.claude/hooks and ~/.codex/hooks, then wires both user-level settings surfaces so the guard
// protects every Claude Code and Codex project loaded by this OS account.
//
// Ported 09-11-2026 from aibuild-lab/agent-native-os scripts/refresh-guard.mjs (PR #62 review,
// 8Dvibes). This repository is now the canonical home of the guard, so:
//   - LOCAL SOURCE, HASH-VERIFIED. The hook bytes are read from this hooks/ directory and each
//     file must match the sha256 in hooks/secrets-guard.manifest.json, or nothing is installed.
//     The manifest is the trust anchor; it changes only in the same reviewed change as the file.
//   - COHERENT + ATOMIC. Every file is fetched and hash/syntax-checked BEFORE any write; then each
//     changed file is staged and swapped in with a backup and rollback. A partial/failed download
//     can never leave a half-updated guard.
//   - ALWAYS REPAIRS SETTINGS. The installer runs on every invocation, even when no hook file
//     changed, so a missing/stale PreToolUse wiring is fixed instead of silently left inactive.
//
// Pure Node (built-in crypto); runs unchanged on macOS and Windows.
// GUARD_SOURCE_DIR (optional): read the canonical hook bytes from another directory. Still
// hash-verified against the manifest, so it can only ever install the exact pinned bytes; it is a
// self-test seam, not a way to sideload a different guard.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const FILES = ["secrets-guard.js", "secrets-tripwire.js", "install.mjs"];
const LOCAL_GUARD_FILES = [
  "aws-credential-patterns.mjs",
  "aws-credential-guard.mjs",
  "aws-credential-tripwire.mjs",
  "codex-secrets-guard.mjs",
  "codex-secrets-tripwire.mjs",
];
const CLAUDE_SUPPLEMENTAL_FILES = ["aws-credential-patterns.mjs", "aws-credential-guard.mjs", "aws-credential-tripwire.mjs"];
const CODEX_LOCAL_FILES = ["aws-credential-patterns.mjs", "codex-secrets-guard.mjs", "codex-secrets-tripwire.mjs"];
const claudeHooksDir = path.join(os.homedir(), ".claude", "hooks");
const claudeSettingsPath = path.join(os.homedir(), ".claude", "settings.json");
const codexDir = path.join(os.homedir(), ".codex");
const codexHooksDir = path.join(codexDir, "hooks");
const codexHooksPath = path.join(codexDir, "hooks.json");
const codexConfigPath = path.join(codexDir, "config.toml");
const codexRequirementsPath = path.join(codexDir, "requirements.toml");
const hooksSourceDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(hooksSourceDir, "..");
const manifestPath = path.join(hooksSourceDir, "secrets-guard.manifest.json");
const ownershipReceiptPath = path.join(claudeHooksDir, "aibl-installer-guard-receipt.json");
const GUARD_MATCHER = "Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit";
const SHELL_MATCHER = "Bash|PowerShell";
const SUPPLEMENT_PRE_MATCHER = "*";
const CODEX_POST_MATCHER = "*";
const SUPPLEMENT_POST_MATCHER = "*";
const REQUIRED_DENY = [
  "Read(.env)", "Read(**/.env)", "Read(**/.env.local)", "Read(**/.env.*.local)",
  "Read(**/*.pem)", "Read(**/id_rsa)", "Read(**/id_ed25519)", "Read(**/credentials*)",
  "Read(**/.env.*)", "Read(**/secrets/**)",
];
const args = new Set(process.argv.slice(2));
const diagnosticMode = args.has("--diagnostic-json");
const stageIds = ["INPUT_SCOPE", "OWNER_DISCOVERY", "OWNER_BINDING", "INSTALLED_INSPECTION", "APPROVAL",
  "SOURCE_VERIFY", "STAGE_WRITES", "COMMIT_FILES", "REGISTER_HOOKS", "POST_VERIFY", "RECEIPT_COMMIT", "FINAL_REPORT"];
let activeStage = null;
let passedStages = [];
let rollbackState = "NOT_NEEDED";
let writesAttempted = false;
let writesCommitted = false;
let diagnosticSourceIdentity = null;
let diagnosticProtection = null;
let diagnosticClients = [];
function enterStage(id) {
  if (!diagnosticMode) return;
  if (activeStage) passedStages.push(activeStage);
  activeStage = id;
  const requested = process.env.AIBL_GUARD_TEST_FAIL_STAGE;
  const home = path.resolve(os.homedir());
  if (requested === id && process.env.AIBL_GUARD_TEST_HOME === home
    && (home === path.resolve(os.tmpdir()) || home.startsWith(`${path.resolve(os.tmpdir())}${path.sep}`))) {
    throw new Error("Synthetic stage failure in disposable home");
  }
}
function diagnosticReport(failed) {
  const completed = failed ? passedStages : [...passedStages, activeStage].filter(Boolean);
  const firstFailedStage = failed ? activeStage || "INPUT_SCOPE" : null;
  const failedIndex = firstFailedStage ? stageIds.indexOf(firstFailedStage) : -1;
  const stages = stageIds.map((id) => ({ id, status: firstFailedStage && id === firstFailedStage ? "FAIL"
    : completed.includes(id) ? id === "APPROVAL" ? "NOT_APPLICABLE" : "PASS" : "NOT_RUN",
    ...(id === "APPROVAL" && completed.includes(id) ? { reason: "Caller authorization is outside this script." } : {}) }));
  const failureClass = !failed ? "NONE" : ({ INPUT_SCOPE: "INPUT_INVALID", OWNER_DISCOVERY: "OWNER_AMBIGUOUS",
    OWNER_BINDING: "OWNERSHIP_INVALID", INSTALLED_INSPECTION: "INSTALLED_BYTES", APPROVAL: "APPROVAL_REQUIRED",
    SOURCE_VERIFY: "SOURCE_INTEGRITY", STAGE_WRITES: "CONCURRENT_CHANGE", COMMIT_FILES: "WRITE_FAILED",
    REGISTER_HOOKS: "REGISTRATION_INVALID", POST_VERIFY: "POSTCHECK_FAILED", RECEIPT_COMMIT: "RECEIPT_WRITE_FAILED",
    FINAL_REPORT: "INTERNAL_ERROR" })[firstFailedStage] || "INTERNAL_ERROR";
  return {
    schemaVersion: 1, operation: "install", scope: "user-global",
    requiredClients: Object.entries(APPS).filter(([, enabled]) => enabled).map(([client]) => client),
    approvedClients: [],
    perClient: Object.fromEntries(["claude", "codex"].map((client) => [client, {
      owner: writesCommitted && diagnosticClients.includes(client) ? "aibl-installer" : "unverified",
      protection: writesCommitted && diagnosticClients.includes(client)
        ? diagnosticProtection?.[client]?.healthy ? "healthy" : "incomplete"
        : APPS[client] ? "unverified" : "not selected",
      ownership: writesCommitted && diagnosticClients.includes(client) ? "installer-managed" : "unverified",
    }])),
    stages,
    lastGoodStage: completed.filter((id) => id !== "APPROVAL").at(-1) || null,
    firstFailedStage,
    failureClass,
    nextSafeAction: failed ? { action: rollbackState === "FAILED" ? "manual-recovery" : "review-and-retry", owner: "aibl-installer", targetClass: "user-global-guard", approvalRequired: true } : null,
    approvalState: "EXTERNAL_AUTHORIZATION_UNVERIFIED",
    writesAttempted, writesCommitted, rollback: rollbackState,
    sourceIdentity: diagnosticSourceIdentity,
    testIdentity: process.env.AIBL_GUARD_TEST_FAIL_STAGE ? "disposable-fault-fixture" : null,
  };
}
// Which app to protect. A student who chose one app should not have the other app's
// configuration written for them; the installer prompt passes the chosen flag and offers the
// other. With neither flag, both (the original Camp behavior, where everyone had both).
const APPS = { claude: args.has("--claude") || !args.has("--codex"), codex: args.has("--codex") || !args.has("--claude") };
const appsLabel = APPS.claude && APPS.codex ? "Claude Code and Codex" : APPS.claude ? "Claude Code" : "Codex";

// The hook command records an ABSOLUTE path to Node (install.mjs explains why: the shell Claude Code
// spawns hooks in has not read ~/.zshrc, so a bare `node` can be "command not found" there, and a
// hook that cannot launch is a non-blocking error that lets the tool run UNGUARDED). But
// process.execPath is the fully RESOLVED path. Through Homebrew's symlink it reads
// /opt/homebrew/Cellar/node/25.6.1/bin/node, and `brew upgrade node` deletes that folder, so the
// guard would switch off in silence the next time Node moved (seen on a real install, 09-19-2026;
// `--check` reports it, but no student runs `--check`). Prefer the launcher the package manager keeps
// pointing at the current version, and only when it resolves to the very same binary running now;
// otherwise keep execPath (nvm, a custom build). CLAUDE_HOOK_NODE, which install.mjs already
// honors, still wins when set.
const STABLE_NODE_LAUNCHERS = process.platform === "win32"
  ? [path.join(process.env.ProgramFiles || "C:\\Program Files", "nodejs", "node.exe")]
  : ["/opt/homebrew/bin/node", "/usr/local/bin/node"];

export function pickStableNode(execPath, launchers = STABLE_NODE_LAUNCHERS, realpath = realpathOrNull) {
  const running = realpath(execPath);
  if (running === null) return execPath;
  for (const launcher of launchers) {
    const target = realpath(launcher);
    if (target !== null && samePath(target, running)) return launcher;
  }
  return execPath;
}

function realpathOrNull(file) {
  try { return fs.realpathSync.native(file); } catch { return null; }
}

function samePath(a, b) {
  const [x, y] = [normalizePath(a), normalizePath(b)];
  return process.platform === "win32" ? x.toLowerCase() === y.toLowerCase() : x === y;
}

function hookNodePath() {
  const requested = process.env.CLAUDE_HOOK_NODE;
  if (requested) {
    if (!path.isAbsolute(requested) || !fs.existsSync(requested)) {
      fail("CLAUDE_HOOK_NODE must point to an existing absolute Node executable.");
    }
    return requested;
  }
  return pickStableNode(process.execPath);
}

// Run only when invoked as a script. Importing the module (the test suite does, for pickStableNode)
// must not install anything. When the comparison itself cannot be made, run: this file's job is to
// install a guard, and a guard that quietly does nothing is the failure mode everything here avoids.
if (isMainModule()) {
  if (diagnosticMode) console.log = (...parts) => process.stderr.write(`${parts.join(" ")}\n`);
  main().then(() => { if (diagnosticMode) process.stdout.write(`${JSON.stringify(diagnosticReport(false))}\n`); }).catch((error) => {
  if (diagnosticMode) {
    process.stdout.write(`${JSON.stringify(diagnosticReport(true))}\n`);
    process.exitCode = 1;
    return;
  }
  if (args.has("--check") && args.has("--json")) {
    const ids = ["INPUT_SCOPE", "OWNER_DISCOVERY", "OWNER_BINDING", "INSTALLED_INSPECTION", "APPROVAL",
      "SOURCE_VERIFY", "STAGE_WRITES", "COMMIT_FILES", "REGISTER_HOOKS", "POST_VERIFY", "RECEIPT_COMMIT", "FINAL_REPORT"];
    process.stdout.write(`${JSON.stringify({
      schemaVersion: 1, operation: "check", scope: "user-global",
      requiredClients: Object.entries(APPS).filter(([, enabled]) => enabled).map(([client]) => client), approvedClients: [],
      onDisk: { status: "incomplete", claude: { status: APPS.claude ? "incomplete" : "not selected", issues: [] }, codex: { status: APPS.codex ? "incomplete" : "not selected", issues: [] } },
      ownership: { status: "unknown" },
      stages: ids.map((id) => ({ id, status: id === "SOURCE_VERIFY" ? "FAIL" : id === "INPUT_SCOPE" ? "PASS" : "NOT_RUN" })),
      lastGoodStage: "INPUT_SCOPE", firstFailedStage: "SOURCE_VERIFY",
      failureClass: /manifest|pinned|hash/i.test(error.message || "") ? "SOURCE_INTEGRITY" : "INTERNAL_ERROR",
      nextSafeAction: { action: "review-installer-source", owner: "aibl-installer", targetClass: "source", approvalRequired: false },
      approvalState: "NOT_REQUIRED_READ_ONLY", writesAttempted: false, writesCommitted: false, rollback: "NOT_NEEDED", sourceIdentity: null,
    })}\n`);
    process.exitCode = 1;
    return;
  }
  console.error(`Guard refresh failed: ${error.message || String(error)}`);
  process.exitCode = 1;
});
}

function isMainModule() {
  const entry = process.argv[1];
  if (!entry) return false; // loaded by `node -e`, `--import` or the REPL: never the script being run
  try {
    return fs.realpathSync.native(entry) === fs.realpathSync.native(fileURLToPath(import.meta.url));
  } catch {
    return true;
  }
}

async function main() {
  enterStage("INPUT_SCOPE");
  const manifest = loadManifest();
  diagnosticSourceIdentity = manifest.ref;

  if (args.has("--check") && args.has("--session-check")) {
    fail("Use either --check or --session-check, not both.");
  }
  const unknown = [...args].filter((arg) => !["--check", "--session-check", "--json", "--claude", "--codex", "--diagnostic-json"].includes(arg));
  if (unknown.length > 0) fail(`Unknown option: ${unknown.join(", ")}`);
  if (diagnosticMode && (args.has("--check") || args.has("--session-check") || args.has("--json"))) fail("Use --diagnostic-json only for an installation attempt.");
  if (args.has("--json") && !args.has("--check")) {
    fail("Use --json with --check.");
  }
  assertGlobalTargetsSafe();

  if (args.has("--check") || args.has("--session-check")) {
    const status = inspectInstalledGuard(manifest);
    const ownership = inspectOwnership(manifest);
    const ownershipHealthy = ownership.status === "absent" || ownership.status === "installer-managed";
    if (args.has("--session-check")) {
      if (!status.healthy || !ownershipHealthy) {
        console.log([
          "The user-global secrets guard or its installer ownership is missing, stale, or incompletely wired.",
          "Before secret-bearing work, run node hooks/refresh-guard.mjs from your aibl-installer clone,",
          "fully quit and reopen both clients, then confirm /hooks lists the user-level guards.",
          "The project guard is only bootstrap protection for this repository.",
        ].join(" "));
      }
      return;
    }
    if (args.has("--json")) {
      process.stdout.write(`${JSON.stringify(jsonStatus(status, manifest, ownership), null, 2)}\n`);
    } else {
      printStatus(status);
      if (!ownershipHealthy) console.log("Installer ownership: invalid; repair the receipt before relying on this check.");
    }
    if (!status.healthy || !ownershipHealthy) process.exitCode = 1;
    return;
  }

  enterStage("OWNER_DISCOVERY");
  const existingOwnership = inspectOwnership(manifest, { requireSelected: false, verifySelectedBinding: false });
  enterStage("OWNER_BINDING");
  if (existingOwnership.status === "invalid") fail("Installer ownership receipt is invalid. No guard files were changed; review it before repair.");
  enterStage("INSTALLED_INSPECTION");
  const before = inspectInstalledGuard(manifest);
  enterStage("APPROVAL");
  enterStage("SOURCE_VERIFY");
  const hookNode = hookNodePath();

  // 1. Fetch every file and verify hash + syntax IN MEMORY before touching disk.
  const fetched = {};
  for (const file of FILES) {
    const bytes = await getFile(manifest.ref, file);
    const want = manifest.files[file];
    if (!want) fail(`The guard manifest has no hash for ${file}. Refusing to install an unverified guard.`);
    const got = sha256(bytes);
    if (got !== want) {
      fail([
        `Downloaded ${file} does not match the pinned release hash.`,
        `  expected ${want}`,
        `  got      ${got}`,
        "Nothing was installed. This can mean the release was re-cut without updating the manifest,",
        "or the file was changed without its manifest. Do NOT bypass this; ask in your program's Slack channel.",
      ].join("\n"));
    }
    if (!syntaxOk(file, bytes)) fail(`Downloaded ${file} failed a syntax check. Nothing was installed.`);
    fetched[file] = bytes;
  }

  // Current-release supplements and Codex adapters are reviewed in this repository and pinned
  // independently. They close known gaps without altering the immutable canonical release.
  const localGuardFiles = {};
  for (const file of LOCAL_GUARD_FILES) {
    const source = path.join(hooksSourceDir, file);
    const bytes = fs.readFileSync(source);
    const want = manifest.local_files?.[file];
    if (!want) fail(`The guard manifest has no hash for ${file}. Refusing to install an unverified local supplement.`);
    const got = sha256(bytes);
    if (got !== want) {
      if (sha256(normalizeLf(bytes)) === want) {
        // Git for Windows (core.autocrlf=true) rewrites LF to CRLF on checkout. Same reviewed
        // content, different line endings: accept it and say exactly that, in plain language.
        console.log(`Note: ${file}: same content, different line endings (CRLF vs LF); normalize line endings or see .gitattributes`);
      } else {
        fail([
          `${file} does not match its reviewed manifest hash.`,
          `  expected ${want}`,
          `  got      ${got}`,
          "Nothing was installed. Review the adapter change and update the trust manifest intentionally.",
        ].join("\n"));
      }
    }
    if (!syntaxOk(file, bytes)) fail(`${file} failed a syntax check. Nothing was installed.`);
    localGuardFiles[file] = bytes;
  }

  // Validate both merge targets before writing any hook bytes. A malformed user file is never
  // replaced or silently repaired because it may contain unrelated settings and hooks.
  if (APPS.claude) validateClaudeHooksMergeTarget(readJsonObjectIfExists(claudeSettingsPath, "~/.claude/settings.json"));
  if (APPS.codex) validateCodexHooksMergeTarget(readJsonObjectIfExists(codexHooksPath, "~/.codex/hooks.json"));

  enterStage("STAGE_WRITES");
  // 2. Stage + atomically swap only the files that differ. Both clients use the same pinned
  // canonical bytes plus narrowly scoped, checksum-pinned local supplements/adapters.
  const desired = [
    ...(APPS.claude ? FILES.map((file) => ({ target: path.join(claudeHooksDir, file), bytes: fetched[file], label: `Claude/${file}` })) : []),
    ...(APPS.claude ? CLAUDE_SUPPLEMENTAL_FILES.map((file) => ({
      target: path.join(claudeHooksDir, file), bytes: localGuardFiles[file], label: `Claude/${file}`,
    })) : []),
    ...(APPS.codex ? ["secrets-guard.js", "secrets-tripwire.js"].map((file) => ({
      target: path.join(codexHooksDir, file), bytes: fetched[file], label: `Codex/${file}`,
    })) : []),
    ...(APPS.codex ? CODEX_LOCAL_FILES.map((file) => ({
      target: path.join(codexHooksDir, file), bytes: localGuardFiles[file], label: `Codex/${file}`,
    })) : []),
  ];
  const changed = desired.filter(({ target, bytes }) => {
    const current = readIfExists(target);
    return current === null || !current.equals(bytes);
  });

  const launchers = ["codex-secrets-guard.mjs", "codex-secrets-tripwire.mjs"]
    .map((script) => path.join(codexHooksDir, codexLauncherName(script)));
  const transaction = beginGuardTransaction([
    ...desired.map(({ target }) => target),
    claudeSettingsPath, `${claudeSettingsPath}.backup.secrets-guard`,
    `${claudeSettingsPath}.backup.aws-credential-supplement`,
    codexHooksPath, `${codexHooksPath}.backup.secrets-guard`,
    ...launchers, ownershipReceiptPath,
  ]);
  try {
    enterStage("COMMIT_FILES");
    writesAttempted = true;
    // 3. Replace reviewed bytes; the transaction below also covers settings, launchers and receipt.
    for (const { target, bytes } of changed) {
      fs.mkdirSync(path.dirname(target), { recursive: true });
      const temp = `${target}.tmp.${process.pid}`;
      try {
        fs.writeFileSync(temp, bytes, { mode: 0o700 });
        fs.chmodSync(temp, 0o700);
        fs.renameSync(temp, target);
      } finally {
        if (fs.existsSync(temp)) fs.rmSync(temp, { force: true });
      }
    }
    if (changed.length > 0) console.log(`Secrets guard updated: ${changed.map(({ label }) => label).join(", ")}`);
    else console.log("Secrets guard files already current.");

  // 4. ALWAYS validate/repair the settings wiring — even when nothing downloaded. A guard whose
  //    PreToolUse hook is missing from settings.json is silently inactive; the installer is
  //    idempotent, so this is a quiet no-op when everything is already correct.
  enterStage("REGISTER_HOOKS");
  if (APPS.claude) {
    // The installer runs on the Node that is running now; CLAUDE_HOOK_NODE tells it which Node
    // path to WRITE into the hook commands (the stable launcher, see pickStableNode).
    const result = spawnSync(process.execPath, [path.join(claudeHooksDir, "install.mjs")], {
      stdio: diagnosticMode ? "pipe" : "inherit",
      env: { ...process.env, CLAUDE_HOOK_NODE: hookNode },
    });
    if (result.status !== 0) {
      fail("The guard installer did not finish cleanly. Read the message above; do not delete ~/.claude/settings.json.");
    }
    installClaudeSupplementalHooks(hookNode);
  }
  if (APPS.codex) installCodexHooks(hookNode);

  enterStage("POST_VERIFY");
  const after = inspectInstalledGuard(manifest);
  diagnosticProtection = after;
  if (!after.healthy) {
    fail([
      "The guard files were processed, but the user-global installation did not pass verification.",
      ...after.issues.map((issue) => `- ${issue}`),
      "Run node hooks/refresh-guard.mjs again after fixing the listed issue. Do not bypass this check.",
    ].join("\n"));
  }
  enterStage("RECEIPT_COMMIT");
  writeOwnershipReceipt(manifest, existingOwnership);
  const committedOwnership = inspectOwnership(manifest);
  if (committedOwnership.status !== "installer-managed") {
    fail("The committed receipt did not verify against both requested client bindings.");
  }
  diagnosticClients = committedOwnership.receipt.clients;
  diagnosticProtection = Object.fromEntries(diagnosticClients.map((client) => [
    client, client === "claude" ? inspectClaudeGuard(manifest) : inspectCodexGuard(manifest),
  ]));
  writesCommitted = true;
  transaction.commit();
  } catch (error) {
    rollbackState = transaction.rollback();
    writesCommitted = false;
    throw new Error(`${error.message || String(error)} Scoped rollback: ${rollbackState}.`);
  } finally {
    transaction.release();
  }
  enterStage("FINAL_REPORT");

  console.log("");
  console.log(`Hook commands run Node from ${hookNode}.`);
  if (changed.length > 0 || !before.healthy) {
    console.log(`User-global secrets guard on-disk installation verified for ${appsLabel}.`);
    console.log("Runtime activation is not observable from this installer.");
    console.log(`Manual proof required: fully quit and reopen ${APPS.claude && APPS.codex ? "both apps" : "the app"}${APPS.codex ? ", trust the Codex hooks on the review screen," : ""} and run the synthetic canaries.`);
  } else {
    console.log(`User-global ${appsLabel} secrets guard on-disk installation is healthy and already current.`);
    console.log("Runtime activation is not observable from this installer; restart, inspect /hooks, trust, and run synthetic canaries to prove it.");
  }
}

function inspectInstalledGuard(manifest) {
  const skipped = { healthy: true, issues: [], skipped: true };
  const claude = APPS.claude ? inspectClaudeGuard(manifest) : skipped;
  const codex = APPS.codex ? inspectCodexGuard(manifest) : skipped;
  return {
    healthy: claude.healthy && codex.healthy,
    claude,
    codex,
    issues: [
      ...claude.issues.map((issue) => `Claude Code: ${issue}`),
      ...codex.issues.map((issue) => `Codex: ${issue}`),
    ],
  };
}

function inspectClaudeGuard(manifest) {
  const issues = [];

  for (const file of FILES) {
    const expected = manifest.files?.[file];
    const installed = readIfExists(path.join(claudeHooksDir, file));
    if (!installed) {
      issues.push(`${file} is missing from ~/.claude/hooks.`);
    } else if (!expected || sha256(installed) !== expected) {
      issues.push(`${file} does not match the pinned release.`);
    }
  }
  for (const file of CLAUDE_SUPPLEMENTAL_FILES) {
    const expected = manifest.local_files?.[file];
    const installed = readIfExists(path.join(claudeHooksDir, file));
    if (!installed) issues.push(`${file} is missing from ~/.claude/hooks.`);
    else if (!expected || !matchesReviewedHash(installed, expected)) issues.push(`${file} does not match its reviewed manifest hash.`);
  }

  let settings;
  if (!fs.existsSync(claudeSettingsPath)) {
    issues.push("~/.claude/settings.json is missing.");
    return { healthy: false, issues };
  }
  try {
    settings = JSON.parse(fs.readFileSync(claudeSettingsPath, "utf8"));
  } catch (error) {
    issues.push("~/.claude/settings.json is not valid JSON.");
    return { healthy: false, issues };
  }
  if (!settings || typeof settings !== "object" || Array.isArray(settings)) {
    issues.push("~/.claude/settings.json must contain a JSON object.");
    return { healthy: false, issues };
  }

  if (settings.disableAllHooks === true) {
    issues.push("~/.claude/settings.json has disableAllHooks enabled.");
  }

  const deny = settings.permissions?.deny;
  if (!Array.isArray(deny)) {
    issues.push("User-level permissions.deny is missing or is not an array.");
  } else {
    const missing = REQUIRED_DENY.filter((rule) => !deny.includes(rule));
    if (missing.length > 0) issues.push(`User-level read deny rules are incomplete (${missing.length} missing).`);
  }

  verifyHook(settings, "PreToolUse", "secrets-guard.js", GUARD_MATCHER, claudeHooksDir, issues);
  verifyHook(settings, "PostToolUse", "secrets-tripwire.js", SHELL_MATCHER, claudeHooksDir, issues);
  verifyHook(settings, "PostToolUseFailure", "secrets-tripwire.js", SHELL_MATCHER, claudeHooksDir, issues);
  verifyHook(settings, "PreToolUse", "aws-credential-guard.mjs", SUPPLEMENT_PRE_MATCHER, claudeHooksDir, issues);
  verifyHook(settings, "PostToolUse", "aws-credential-tripwire.mjs", SUPPLEMENT_POST_MATCHER, claudeHooksDir, issues);
  verifyHook(settings, "PostToolUseFailure", "aws-credential-tripwire.mjs", SUPPLEMENT_POST_MATCHER, claudeHooksDir, issues);

  return { healthy: issues.length === 0, issues };
}

function inspectCodexGuard(manifest) {
  const issues = [];
  const expectedFiles = {
    "secrets-guard.js": manifest.files?.["secrets-guard.js"],
    "secrets-tripwire.js": manifest.files?.["secrets-tripwire.js"],
    ...Object.fromEntries(CODEX_LOCAL_FILES.map((file) => [file, manifest.local_files?.[file]])),
  };
  for (const [file, expected] of Object.entries(expectedFiles)) {
    const installed = readIfExists(path.join(codexHooksDir, file));
    if (!installed) issues.push(`${file} is missing from ~/.codex/hooks.`);
    else if (!expected || !(CODEX_LOCAL_FILES.includes(file) ? matchesReviewedHash(installed, expected) : sha256(installed) === expected)) {
      issues.push(`${file} does not match the pinned release.`);
    }
  }

  let settings;
  if (!fs.existsSync(codexHooksPath)) {
    issues.push("~/.codex/hooks.json is missing.");
    return { healthy: false, issues };
  }
  try {
    settings = JSON.parse(fs.readFileSync(codexHooksPath, "utf8"));
  } catch (error) {
    issues.push("~/.codex/hooks.json is not valid JSON.");
    return { healthy: false, issues };
  }
  if (!settings || typeof settings !== "object" || Array.isArray(settings)) {
    issues.push("~/.codex/hooks.json must contain a JSON object.");
    return { healthy: false, issues };
  }

  verifyCodexHook(settings, "PreToolUse", "codex-secrets-guard.mjs", SUPPLEMENT_PRE_MATCHER, issues);
  verifyCodexHook(settings, "PostToolUse", "codex-secrets-tripwire.mjs", CODEX_POST_MATCHER, issues);
  inspectCodexFeatureFlags(codexConfigPath, "~/.codex/config.toml", issues);
  inspectCodexRequirements(codexRequirementsPath, issues);
  return { healthy: issues.length === 0, issues };
}

function installClaudeSupplementalHooks(hookNode) {
  const settings = readJsonObjectIfExists(claudeSettingsPath, "~/.claude/settings.json");
  validateClaudeHooksMergeTarget(settings);
  const originalText = fs.readFileSync(claudeSettingsPath, "utf8");
  const nodeBin = normalizePath(hookNode);
  const ensureHook = (event, script, matcher) => {
    const current = settings.hooks[event] ?? [];
    const scriptPath = normalizePath(path.join(claudeHooksDir, script));
    const command = `"${nodeBin}" "${scriptPath}"`;
    const canonicalIndex = current.findIndex((group) =>
      group?.matcher === matcher
      && Array.isArray(group.hooks)
      && group.hooks.length === 1
      && group.hooks[0]?.type === "command"
      && group.hooks[0]?.command === command,
    );
    let removed = 0;
    const preserved = [];
    for (const [index, group] of current.entries()) {
      if (index === canonicalIndex) {
        preserved.push(group);
        continue;
      }
      if (!group || !Array.isArray(group.hooks)) {
        preserved.push(group);
        continue;
      }
      const before = removed;
      const hooks = group.hooks.filter((hook) => {
        const managed = hookRunsScript(hook, script);
        if (managed) removed += 1;
        return !managed;
      });
      if (hooks.length > 0 || removed === before) {
        preserved.push(hooks.length === group.hooks.length ? group : { ...group, hooks });
      }
    }
    const next = canonicalIndex >= 0
      ? preserved
      : [...preserved, { matcher, hooks: [{ type: "command", command }] }];
    settings.hooks[event] = next;
    if (JSON.stringify(current) === JSON.stringify(next)) return "already correct";
    return removed > 0 ? "repaired" : "added";
  };

  const preStatus = ensureHook("PreToolUse", "aws-credential-guard.mjs", SUPPLEMENT_PRE_MATCHER);
  const postStatus = ensureHook("PostToolUse", "aws-credential-tripwire.mjs", SUPPLEMENT_POST_MATCHER);
  const failureStatus = ensureHook("PostToolUseFailure", "aws-credential-tripwire.mjs", SUPPLEMENT_POST_MATCHER);
  const nextText = JSON.stringify(settings, null, 2) + "\n";
  if (nextText !== originalText) {
    const backup = `${claudeSettingsPath}.backup.aws-credential-supplement`;
    if (!fs.existsSync(backup)) {
      fs.copyFileSync(claudeSettingsPath, backup);
      fs.chmodSync(backup, 0o600);
    }
    const temp = `${claudeSettingsPath}.tmp.${process.pid}`;
    try {
      fs.writeFileSync(temp, nextText, { mode: 0o600 });
      fs.chmodSync(temp, 0o600);
      fs.renameSync(temp, claudeSettingsPath);
    } finally {
      if (fs.existsSync(temp)) fs.rmSync(temp, { force: true });
    }
  }
  fs.chmodSync(claudeSettingsPath, 0o600);
  console.log("Claude Code AWS credential supplement installed.");
  console.log(`  PreToolUse        (aws-credential-guard.mjs): ${preStatus}`);
  console.log(`  PostToolUse       (aws-credential-tripwire.mjs): ${postStatus}`);
  console.log(`  PostToolUseFailure(aws-credential-tripwire.mjs): ${failureStatus}`);
}

function installCodexHooks(hookNode) {
  fs.mkdirSync(codexHooksDir, { recursive: true });
  const settings = readJsonObjectIfExists(codexHooksPath, "~/.codex/hooks.json") ?? {};
  const originalText = fs.existsSync(codexHooksPath) ? fs.readFileSync(codexHooksPath, "utf8") : null;
  validateCodexHooksMergeTarget(settings);
  // Codex parses ~/.codex/hooks.json with a STRICT schema: any unknown top-level field makes it
  // reject the whole file with `unknown field ..., expected `hooks``, warn, and then run with NO
  // hooks loaded. That is silent: the file is on disk, the installer's own health check passes, and
  // the guard never executes. We used to write a `description` here, which tripped exactly that.
  // Delete it rather than merely stop writing it, so an install that already has it gets repaired.
  if (settings.description !== undefined) {
    delete settings.description;
    console.log("Removed a `description` field from ~/.codex/hooks.json; Codex rejects unknown top-level fields and would have loaded no hooks.");
  }
  settings.hooks ??= {};

  const ensureHook = (event, script, matcher) => {
    const current = settings.hooks[event] ?? [];
    if (!Array.isArray(current)) {
      fail(`~/.codex/hooks.json hooks.${event} must be an array. Fix it, then re-run; it was not overwritten.`);
    }
    // Register one wrapper script per hook, launched in the form codexHookCommand() explains. A
    // Claude-style `"<node>" "<script>"` value fails to launch under Codex, and Codex FAILS OPEN:
    // it reports `hook: PreToolUse Failed` and runs the tool call anyway.
    const command = codexHookCommand(writeCodexLauncher(script, hookNode));
    const canonicalIndex = current.findIndex((group) =>
      group?.matcher === matcher
      && Array.isArray(group.hooks)
      && group.hooks.length === 1
      && group.hooks[0]?.type === "command"
      && group.hooks[0]?.command === command,
    );

    let removed = 0;
    const preserved = [];
    for (const [index, group] of current.entries()) {
      if (index === canonicalIndex) {
        preserved.push(group);
        continue;
      }
      if (!group || !Array.isArray(group.hooks)) {
        preserved.push(group);
        continue;
      }
      const before = removed;
      const hooks = group.hooks.filter((hook) => {
        // Treat BOTH forms as ours so a previously-installed (and silently broken) direct-.mjs
        // command is replaced rather than left beside the launcher.
        const managed = hookRunsScript(hook, script) || hookRunsScript(hook, codexLauncherName(script));
        if (managed) removed += 1;
        return !managed;
      });
      if (hooks.length > 0 || removed === before) {
        preserved.push(hooks.length === group.hooks.length ? group : { ...group, hooks });
      }
    }
    const next = canonicalIndex >= 0
      ? preserved
      : [...preserved, {
          matcher,
          hooks: [{ type: "command", command, timeoutSec: 30, statusMessage: "Checking for secret exposure" }],
        }];
    settings.hooks[event] = next;
    if (JSON.stringify(current) === JSON.stringify(next)) return "already correct";
    return removed > 0 ? "repaired" : "added";
  };

  const preStatus = ensureHook("PreToolUse", "codex-secrets-guard.mjs", SUPPLEMENT_PRE_MATCHER);
  const postStatus = ensureHook("PostToolUse", "codex-secrets-tripwire.mjs", CODEX_POST_MATCHER);
  const nextText = JSON.stringify(settings, null, 2) + "\n";
  if (nextText !== originalText) {
    const backup = `${codexHooksPath}.backup.secrets-guard`;
    if (originalText !== null && !fs.existsSync(backup)) {
      fs.copyFileSync(codexHooksPath, backup);
      fs.chmodSync(backup, 0o600);
    }
    const temp = `${codexHooksPath}.tmp.${process.pid}`;
    try {
      fs.writeFileSync(temp, nextText, { mode: 0o600 });
      fs.chmodSync(temp, 0o600);
      fs.renameSync(temp, codexHooksPath);
    } finally {
      if (fs.existsSync(temp)) fs.rmSync(temp, { force: true });
    }
  }
  fs.chmodSync(codexHooksPath, 0o600);
  console.log("Codex secrets guard installed.");
  console.log(`  PreToolUse (codex-secrets-guard.mjs): ${preStatus}`);
  console.log(`  PostToolUse(codex-secrets-tripwire.mjs): ${postStatus}`);
}

// Codex runs a hook `command` through the session's shell (codex-rs core session/mod.rs,
// build_hooks_config): Windows PowerShell on a default Windows install, `cmd /C` when no shell is
// known, the user's shell on macOS. The adapter is therefore wrapped in a tiny platform launcher
// that execs Node on it, and the launcher is what gets registered. On codex-cli 0.145.0 the quoted
// two-token `"<node>" "<script>.mjs"` form yielded `hook: PreToolUse Failed`, which is PowerShell
// refusing two adjacent strings, while a launcher path yielded `hook: PreToolUse Blocked`.
export function codexLauncherName(script) {
  const base = script.replace(/\.mjs$/, "");
  return process.platform === "win32" ? `${base}.cmd` : `${base}.sh`;
}

// The hooks.json `command` value for a launcher. On Windows a bare path is not enough: PowerShell
// splits it at a space, so `C:/Users/First Last/.codex/hooks/x.cmd` runs a program named
// `C:/Users/First`, the hook fails, and Codex runs the tool call unguarded (student report
// 09-24-2026, codex-cli 0.156.1, a Windows account name with a space). Quoting alone does not help,
// because PowerShell prints a quoted string instead of running it. `cmd /d /c "<launcher>"` launches
// under cmd, Windows PowerShell and PowerShell 7 alike, with or without a space; `/d` skips cmd's
// AutoRun, which could otherwise print text into the hook's JSON reply. macOS account folders cannot
// contain a space, so the bare path stays there.
export function codexHookCommand(launcher) {
  return process.platform === "win32" ? `cmd /d /c "${launcher}"` : normalizePath(launcher);
}

function writeCodexLauncher(script, hookNode) {
  const launcher = path.join(codexHooksDir, codexLauncherName(script));
  const adapter = path.join(codexHooksDir, script);
  const node = hookNode;
  // Quote inside the launcher, which a shell parses; hooks.json takes the form codexHookCommand gives.
  const body = process.platform === "win32"
    ? `@echo off\r\n"${node}" "${adapter}" %*\r\n`
    : `#!/bin/sh\nexec "${node}" "${adapter}" "$@"\n`;
  const existing = readIfExists(launcher);
  if (existing === null || existing.toString("utf8") !== body) {
    fs.mkdirSync(path.dirname(launcher), { recursive: true });
    const temp = `${launcher}.tmp.${process.pid}`;
    try {
      fs.writeFileSync(temp, body, { mode: 0o700 });
      fs.chmodSync(temp, 0o700);
      fs.renameSync(temp, launcher);
    } finally {
      if (fs.existsSync(temp)) fs.rmSync(temp, { force: true });
    }
  } else {
    fs.chmodSync(launcher, 0o700);
  }
  return launcher;
}

// The Codex side registers a launcher in codexHookCommand's form, so it cannot reuse verifyHook
// (which requires the Claude `"<node>" "<script>"` shape). Assert the launcher is registered in
// exactly that form, present on disk, and actually points at the adapter it claims to.
function verifyCodexHook(settings, event, script, matcher, issues) {
  const launcherName = codexLauncherName(script);
  const groups = settings.hooks?.[event];
  if (!Array.isArray(groups)) {
    issues.push(`User-level ${event} hooks are missing.`);
    return;
  }
  const matching = groups.filter((group) =>
    Array.isArray(group?.hooks) && group.hooks.some((hook) => hookRunsScript(hook, launcherName)),
  );
  if (matching.length !== 1) {
    issues.push(`User-level ${event} must contain exactly one ${launcherName} hook.`);
    return;
  }
  const group = matching[0];
  if (group.matcher !== matcher || group.hooks.length !== 1 || group.hooks[0]?.type !== "command") {
    issues.push(`User-level ${event} ${launcherName} hook is not in its canonical matcher group.`);
    return;
  }
  const command = group.hooks[0].command;
  const launcherPath = path.join(codexHooksDir, launcherName);
  if (typeof command !== "string") {
    issues.push(`User-level ${event} ${launcherName} hook has no command.`);
    return;
  }
  if (normalizePath(command) !== normalizePath(codexHookCommand(launcherPath))) {
    // The bare path is the pre-09-24-2026 Windows shape: it fails to launch whenever the account
    // folder has a space, and Codex then fails open. Anything else is a wrong path or form.
    issues.push(normalizePath(command) === normalizePath(launcherPath)
      ? `User-level ${event} ${launcherName} hook uses the old Windows form, which fails when the account folder name has a space. Re-run with --codex to repair it.`
      : `User-level ${event} ${launcherName} hook points to the wrong path or uses the wrong form.`);
    return;
  }
  const onDisk = readIfExists(path.join(codexHooksDir, launcherName));
  if (onDisk === null) {
    issues.push(`${launcherName} is missing from ~/.codex/hooks.`);
    return;
  }
  const bindingIssue = codexLauncherIssue(path.join(codexHooksDir, launcherName), script);
  if (bindingIssue) issues.push(`${launcherName} ${bindingIssue}.`);
}

function codexLauncherIssue(launcher, script) {
  try {
    const stat = fs.lstatSync(launcher);
    if (!stat.isFile() || stat.isSymbolicLink()) return "is not a regular launcher";
    if (process.platform !== "win32" && (stat.mode & 0o100) === 0) return "is not executable";
    const rawBody = fs.readFileSync(launcher, "utf8");
    if (process.platform !== "win32" && rawBody.includes("\r")) return "has invalid Unix launcher line endings";
    const body = process.platform === "win32" ? rawBody.replaceAll("\r\n", "\n") : rawBody;
    // Parse the complete supported wrapper, never a comment/substring, and never execute it.
    // Shell expansion characters are excluded from quoted paths in the supported contract.
    const match = process.platform === "win32"
      ? body.match(/^@echo off\n"([^"%\r\n]+)" "([^"%\r\n]+)" %\*\n$/)
      : body.match(/^#!\/bin\/sh\nexec "([^"$`\\\r\n]+)" "([^"$`\\\r\n]+)" "\$@"\n$/);
    if (!match) return "does not have the supported invoking structure";
    const [, nodeBin, adapter] = match;
    if (!isAbsolutePortable(adapter)
      || normalizePath(adapter) !== normalizePath(path.join(codexHooksDir, script))) return "points to the wrong adapter";
    if (!isAbsolutePortable(nodeBin) || !/^node(?:\.exe)?$/i.test(path.win32.basename(nodeBin))
      || !fs.statSync(nodeBin).isFile()) return "has no supported Node executable";
    fs.accessSync(nodeBin, process.platform === "win32" ? fs.constants.F_OK : fs.constants.X_OK);
    return null;
  } catch {
    return "has an unavailable or unsafe launcher binding";
  }
}

function validateCodexHooksMergeTarget(settings) {
  if (settings === null) return;
  if (settings.hooks !== undefined && (!settings.hooks || typeof settings.hooks !== "object" || Array.isArray(settings.hooks))) {
    fail("~/.codex/hooks.json `hooks` must be an object. Fix it, then re-run; it was not overwritten.");
  }
  for (const event of ["PreToolUse", "PostToolUse"]) {
    if (settings.hooks?.[event] !== undefined && !Array.isArray(settings.hooks[event])) {
      fail(`~/.codex/hooks.json hooks.${event} must be an array. Fix it, then re-run; it was not overwritten.`);
    }
  }
}

function validateClaudeHooksMergeTarget(settings) {
  if (settings === null) return;
  if (settings.hooks !== undefined && (!settings.hooks || typeof settings.hooks !== "object" || Array.isArray(settings.hooks))) {
    fail("~/.claude/settings.json `hooks` must be an object. Fix it, then re-run; it was not overwritten.");
  }
  for (const event of ["PreToolUse", "PostToolUse", "PostToolUseFailure"]) {
    if (settings.hooks?.[event] !== undefined && !Array.isArray(settings.hooks[event])) {
      fail(`~/.claude/settings.json hooks.${event} must be an array. Fix it, then re-run; it was not overwritten.`);
    }
  }
}

function readJsonObjectIfExists(file, display) {
  if (!fs.existsSync(file)) return null;
  let value;
  try {
    value = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    fail(`${display} is not valid JSON. Fix it, then re-run; it was not overwritten.`);
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    fail(`${display} must contain a JSON object. Fix it, then re-run; it was not overwritten.`);
  }
  return value;
}

function verifyHook(settings, event, script, matcher, hookDirectory, issues) {
  const groups = settings.hooks?.[event];
  if (!Array.isArray(groups)) {
    issues.push(`User-level ${event} hooks are missing.`);
    return;
  }

  const matching = groups.filter((group) =>
    Array.isArray(group?.hooks) && group.hooks.some((hook) => hookRunsScript(hook, script)),
  );
  if (matching.length !== 1) {
    issues.push(`User-level ${event} must contain exactly one ${script} hook.`);
    return;
  }

  const group = matching[0];
  if (group.matcher !== matcher || group.hooks.length !== 1 || group.hooks[0]?.type !== "command") {
    issues.push(`User-level ${event} ${script} hook is not in its canonical matcher group.`);
    return;
  }

  const command = group.hooks[0].command;
  const parsed = typeof command === "string" ? command.match(/^"([^"]+)"\s+"([^"]+)"$/) : null;
  if (!parsed) {
    issues.push(`User-level ${event} ${script} hook does not use quoted absolute paths.`);
    return;
  }

  const [, nodeBin, scriptPath] = parsed;
  const expectedScript = normalizePath(path.join(hookDirectory, script));
  if (!isAbsolutePortable(nodeBin) || !fs.existsSync(nodeBin)) {
    issues.push(`User-level ${event} ${script} hook points to a missing or non-absolute Node runtime.`);
  }
  if (!isAbsolutePortable(scriptPath) || normalizePath(scriptPath) !== expectedScript) {
    issues.push(`User-level ${event} ${script} hook points to the wrong script path.`);
  }
}

function inspectCodexFeatureFlags(file, display, issues) {
  if (!fs.existsSync(file)) return;
  const text = fs.readFileSync(file, "utf8");
  const featureSection = text.match(/(?:^|\n)\s*\[features\]\s*\n([\s\S]*?)(?=\n\s*\[|$)/)?.[1] ?? "";
  if (/^\s*(?:hooks|codex_hooks)\s*=\s*false\s*(?:#.*)?$/m.test(featureSection)) {
    issues.push(`${display} disables lifecycle hooks under [features].`);
  }
}

function inspectCodexRequirements(file, issues) {
  if (!fs.existsSync(file)) return;
  const text = fs.readFileSync(file, "utf8");
  if (/^\s*allow_managed_hooks_only\s*=\s*true\s*(?:#.*)?$/m.test(text)) {
    issues.push("~/.codex/requirements.toml allows managed hooks only, so user hooks cannot run.");
  }
  inspectCodexFeatureFlags(file, "~/.codex/requirements.toml", issues);
}

function hookRunsScript(hook, script) {
  if (!hook || typeof hook.command !== "string") return false;
  const normalized = normalizePath(hook.command);
  return [normalizePath(path.join(claudeHooksDir, script)), normalizePath(path.join(codexHooksDir, script)), `~/.claude/hooks/${script}`].some((target) => {
    const escaped = target.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp(`(?:^|[\\s"'])${escaped}(?=$|[\\s"';&|])`, process.platform === "win32" ? "i" : "").test(normalized);
  });
}

function normalizePath(value) { return value.replaceAll("\\", "/"); }
function isAbsolutePortable(value) { return path.posix.isAbsolute(value) || path.win32.isAbsolute(value); }

function printStatus(status) {
  console.log(`Secrets guard scope: user-global (${appsLabel} projects for this OS account)`);
  console.log(`On-disk status: ${status.healthy ? "healthy" : "incomplete"}`);
  if (!status.healthy) {
    for (const issue of status.issues) console.log(`- ${issue}`);
    console.log("Repair: run node hooks/refresh-guard.mjs from your aibl-installer clone, restart both apps, and review Codex /hooks trust.");
  }
  console.log("Runtime activation: not observable from the installer");
  console.log("Manual proof required: restart both clients, inspect /hooks, trust the exact Codex hooks, and run synthetic canaries.");
}

function jsonStatus(status, manifest, ownership = inspectOwnership(manifest)) {
  const selected = Object.entries(APPS).filter(([, enabled]) => enabled).map(([client]) => client);
  const ownershipBindingFailed = ownership.status === "invalid"
    && !ownership.issues?.every((issue) => /^receipt (claude|codex) installed binding does not match this installer$/.test(issue));
  const healthy = status.healthy && ownership.status !== "invalid";
  const failure = healthy ? null : ownershipBindingFailed ? "OWNER_BINDING" : "INSTALLED_INSPECTION";
  const ids = ["INPUT_SCOPE", "OWNER_DISCOVERY", "OWNER_BINDING", "INSTALLED_INSPECTION", "APPROVAL",
    "SOURCE_VERIFY", "STAGE_WRITES", "COMMIT_FILES", "REGISTER_HOOKS", "POST_VERIFY", "RECEIPT_COMMIT", "FINAL_REPORT"];
  const failureIndex = failure ? ids.indexOf(failure) : -1;
  const mutationStages = new Set(["APPROVAL", "SOURCE_VERIFY", "STAGE_WRITES", "COMMIT_FILES", "REGISTER_HOOKS", "POST_VERIFY", "RECEIPT_COMMIT"]);
  const issueText = status.issues.join(" ");
  const failureClass = healthy ? "NONE" : ownershipBindingFailed ? "OWNERSHIP_INVALID"
    : /invalid Unix launcher line endings/i.test(issueText) ? "LAUNCHER_LINE_ENDINGS_INVALID"
    : /disableAllHooks|disabled|managed.only/i.test(issueText) ? "CLIENT_POLICY_DISABLED"
      : /runtime|Node path|node executable/i.test(issueText) ? "RUNTIME_PATH_INVALID"
        : /settings.json.*JSON|hooks.json.*JSON|read deny/i.test(issueText) ? "SETTINGS_INVALID"
          : /matcher|User.level|registration/i.test(issueText) ? "REGISTRATION_INVALID" : "INSTALLED_BYTES";
  const nextAction = ownershipBindingFailed ? "review-installer-receipt"
    : failureClass === "LAUNCHER_LINE_ENDINGS_INVALID" ? "inspect-private-launcher-line-endings"
    : failureClass === "SETTINGS_INVALID" ? "review-private-settings"
      : failureClass === "CLIENT_POLICY_DISABLED" ? "review-hook-policy"
        : failureClass === "RUNTIME_PATH_INVALID" ? "review-runtime-executable"
          : "run-approved-installer-repair";
  const stages = ids.map((id, index) => ({
    id,
    status: failure && index === failureIndex ? "FAIL"
      : failure && index > failureIndex ? "NOT_RUN"
        : mutationStages.has(id) ? "NOT_APPLICABLE" : "PASS",
    reason: mutationStages.has(id) ? "read-only inspection" : null,
  }));
  return {
    schemaVersion: 1,
    operation: "check",
    requiredClients: selected,
    approvedClients: [],
    perClient: Object.fromEntries(["claude", "codex"].map((client) => {
      const clientOwner = ownership.status === "installer-managed" && ownership.receipt.clients.includes(client)
        ? "installer-managed" : "unverified";
      return [client, {
        owner: clientOwner,
        protection: status[client].skipped ? "not selected" : status[client].healthy ? "healthy" : "incomplete",
        ownership: clientOwner,
      }];
    })),
    stages,
    lastGoodStage: failure ? ids[failureIndex - 1] : "FINAL_REPORT",
    firstFailedStage: failure,
    failureClass,
    nextSafeAction: healthy ? null : { action: nextAction, owner: "aibl-installer", targetClass: "user-global-guard", approvalRequired: nextAction === "run-approved-installer-repair" },
    approvalState: "NOT_REQUIRED_READ_ONLY",
    writesAttempted: false,
    writesCommitted: false,
    rollback: "NOT_NEEDED",
    sourceIdentity: manifest.ref,
    scope: "user-global",
    onDisk: {
      status: status.healthy ? "healthy" : "incomplete",
      claude: {
        status: status.claude.skipped ? "not selected" : status.claude.healthy ? "healthy" : "incomplete",
        issues: status.claude.issues,
      },
      codex: {
        status: status.codex.skipped ? "not selected" : status.codex.healthy ? "healthy" : "incomplete",
        issues: status.codex.issues,
      },
    },
    runtime: {
      status: "manual-proof-required",
      observableFromInstaller: false,
      requiredSteps: ["restart", "inspect-hooks", "trust-exact-hooks", "synthetic-canaries"],
    },
    ownership: {
      status: ownership.status,
      clients: Array.isArray(ownership.receipt?.clients) ? ownership.receipt.clients : [],
      issues: Array.isArray(ownership.issues) ? ownership.issues : [],
    },
  };
}

function receiptFor(manifest, clients = Object.entries(APPS).filter(([, selected]) => selected).map(([client]) => client)) {
  const managedFiles = {
    claude: clients.includes("claude") ? [...FILES, ...CLAUDE_SUPPLEMENTAL_FILES] : [],
    codex: clients.includes("codex") ? ["secrets-guard.js", "secrets-tripwire.js", ...CODEX_LOCAL_FILES] : [],
  };
  return {
    schemaVersion: 1,
    owner: "aibl-installer",
    source: { location: normalizePath(repoRoot) },
    manifest: { ref: manifest.ref, identity: sha256(normalizeLf(fs.readFileSync(manifestPath))) },
    managedFiles,
    clients: Object.entries(managedFiles).filter(([, files]) => files.length > 0).map(([client]) => client),
  };
}

function inspectOwnership(manifest, { requireSelected = true, verifySelectedBinding = true } = {}) {
  if (!fs.existsSync(ownershipReceiptPath)) return { status: "absent", receiptPath: normalizePath(ownershipReceiptPath) };
  let receipt;
  try {
    receipt = JSON.parse(fs.readFileSync(ownershipReceiptPath, "utf8"));
  } catch {
    return { status: "invalid", receiptPath: normalizePath(ownershipReceiptPath), issues: ["receipt is not valid JSON"] };
  }
  if (!Array.isArray(receipt?.clients) || receipt.clients.length === 0
    || receipt.clients.some((client) => !["claude", "codex"].includes(client))
    || new Set(receipt.clients).size !== receipt.clients.length) {
    return { status: "invalid", issues: ["receipt clients are invalid"] };
  }
  const expected = receiptFor(manifest, receipt.clients);
  // The checkout can move after installation. Its recorded path is recovery metadata, not a
  // trust input; ownership comes from the pinned manifest and independently inspected bindings.
  const fields = ["schemaVersion", "owner", "manifest", "managedFiles", "clients"];
  const issues = fields.filter((field) => JSON.stringify(receipt?.[field]) !== JSON.stringify(expected[field]));
  if (typeof receipt?.source?.location !== "string") issues.push("source metadata");
  for (const client of receipt.clients) {
    if (!verifySelectedBinding && APPS[client]) continue;
    const inspection = client === "claude" ? inspectClaudeGuard(manifest) : inspectCodexGuard(manifest);
    if (!inspection.healthy) issues.push(`${client} installed binding`);
  }
  if (requireSelected) for (const client of Object.keys(APPS)) {
    if (APPS[client] && !receipt.clients.includes(client)) issues.push(`${client} required ownership`);
  }
  if (issues.length > 0) return { status: "invalid", receiptPath: normalizePath(ownershipReceiptPath), issues: issues.map((field) => `receipt ${field} does not match this installer`) };
  return { status: "installer-managed", receiptPath: normalizePath(ownershipReceiptPath), receipt };
}

function writeOwnershipReceipt(manifest, previous) {
  const selected = Object.entries(APPS).filter(([, enabled]) => enabled).map(([client]) => client);
  const clients = ["claude", "codex"].filter((client) => selected.includes(client) || previous.receipt?.clients?.includes(client));
  for (const client of clients) {
    const inspection = client === "claude" ? inspectClaudeGuard(manifest) : inspectCodexGuard(manifest);
    if (!inspection.healthy) fail(`Installer ownership cannot be committed: ${client} binding is incomplete.`);
  }
  const receipt = JSON.stringify(receiptFor(manifest, clients), null, 2) + "\n";
  fs.mkdirSync(path.dirname(ownershipReceiptPath), { recursive: true });
  const temp = `${ownershipReceiptPath}.tmp.${process.pid}`;
  try {
    fs.writeFileSync(temp, receipt, { mode: 0o600 });
    fs.chmodSync(temp, 0o600);
    fs.renameSync(temp, ownershipReceiptPath);
  } finally {
    if (fs.existsSync(temp)) fs.rmSync(temp, { force: true });
  }
}

function loadManifest() {
  let manifest;
  try {
    manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  } catch (error) {
    fail(`Cannot read the guard manifest at ${manifestPath}. (${error.message || error})`);
  }
  if (!manifest.ref || manifest.ref === "REPLACE_AT_RELEASE") {
    fail([
      "The secrets guard is not pinned to a released version yet (manifest `ref` is unset).",
      "This build must not install an unreviewed guard. Ask your program's channel to",
      "publish the reviewed hooks/secrets-guard.manifest.json.",
    ].join("\n"));
  }
  if (!manifest.files || typeof manifest.files !== "object") {
    fail("Guard manifest has no `files` hashes. Refusing to install an unverified guard.");
  }
  if (!manifest.local_files || typeof manifest.local_files !== "object") {
    fail("Guard manifest has no `local_files` hashes. Refusing to install unverified supplements or adapters.");
  }
  return manifest;
}

async function getFile(ref, file) {
  // This repository is the canonical home: read the bytes beside this script (or from the
  // GUARD_SOURCE_DIR self-test seam). They are hash-verified against the manifest regardless.
  const sourceDir = process.env.GUARD_SOURCE_DIR || hooksSourceDir;
  const source = path.join(sourceDir, file);
  if (!fs.existsSync(source)) fail(`${file} is missing from ${sourceDir}. Nothing was installed. Re-clone aibl-installer and try again.`);
  // A Git for Windows checkout (core.autocrlf=true) carries CRLF; the manifest pins the LF bytes the
  // reviewed source has. Pure CRLF -> LF only, so a bare CR tamper still fails the hash below, and what
  // lands on disk is the exact pinned bytes on every platform.
  return normalizeLf(fs.readFileSync(source));
}

function syntaxOk(file, bytes) {
  const probe = path.join(os.tmpdir(), `guard-check-${process.pid}-${file}`);
  try {
    fs.writeFileSync(probe, bytes);
    return spawnSync(process.execPath, ["--check", probe], { encoding: "utf8" }).status === 0;
  } catch (_) {
    return false;
  } finally {
    try { fs.rmSync(probe); } catch (_) {}
  }
}

function beginGuardTransaction(targets) {
  const lock = path.join(claudeHooksDir, ".aibl-guard-writer.lock");
  const directories = [claudeHooksDir, path.dirname(claudeHooksDir), codexHooksDir, codexDir];
  const existingDirectories = new Set(directories.filter((directory) => fs.existsSync(directory)));
  statWithoutSymlink(claudeHooksDir);
  fs.mkdirSync(claudeHooksDir, { recursive: true });
  let fd;
  try { fd = fs.openSync(lock, "wx", 0o600); }
  catch { throw new Error("Another guard writer holds the user-global lock; no files were changed."); }
  const lockIdentity = fs.fstatSync(fd).ino;
  let snapshots;
  try {
    snapshots = [...new Set(targets)].map((target) => {
      const stat = statWithoutSymlink(target);
      return { target, exists: Boolean(stat), bytes: stat ? fs.readFileSync(target) : null, mode: stat ? stat.mode & 0o777 : null };
    });
  } catch (error) {
    fs.closeSync(fd);
    fs.rmSync(lock, { force: true });
    throw error;
  }
  let released = false;
  return {
    commit() { /* The receipt is verified by the caller before success is reported. */ },
    rollback() {
      let restored = true;
      for (const item of snapshots.reverse()) {
        try {
          const current = statWithoutSymlink(item.target);
          if (!item.exists) {
            if (current) fs.rmSync(item.target);
          } else {
            fs.mkdirSync(path.dirname(item.target), { recursive: true });
            const temp = `${item.target}.rollback.${process.pid}`;
            try {
              fs.writeFileSync(temp, item.bytes, { mode: item.mode });
              fs.chmodSync(temp, item.mode);
              fs.renameSync(temp, item.target);
            } finally { if (fs.existsSync(temp)) fs.rmSync(temp, { force: true }); }
          }
        } catch { restored = false; }
      }
      for (const directory of directories) {
        if (existingDirectories.has(directory)) continue;
        try { fs.rmdirSync(directory); } catch { /* only remove an empty directory we created */ }
      }
      for (const item of snapshots) {
        try {
          const stat = statWithoutSymlink(item.target);
          if (Boolean(stat) !== item.exists) restored = false;
          if (item.exists && (!fs.readFileSync(item.target).equals(item.bytes) || (stat.mode & 0o777) !== item.mode)) restored = false;
        } catch { restored = false; }
      }
      return restored ? "RESTORED" : "FAILED";
    },
    release() {
      if (released) return;
      released = true;
      fs.closeSync(fd);
      try { if (fs.lstatSync(lock).ino === lockIdentity) fs.rmSync(lock); } catch { /* do not clear another writer's lock */ }
    },
  };
}

function assertGlobalTargetsSafe() {
  const targets = [claudeHooksDir, codexHooksDir, claudeSettingsPath, codexHooksPath, ownershipReceiptPath,
    ...[...FILES, ...CLAUDE_SUPPLEMENTAL_FILES].map((name) => path.join(claudeHooksDir, name)),
    ...["secrets-guard.js", "secrets-tripwire.js", ...CODEX_LOCAL_FILES].map((name) => path.join(codexHooksDir, name)),
    ...["codex-secrets-guard.mjs", "codex-secrets-tripwire.mjs"].map((name) => path.join(codexHooksDir, codexLauncherName(name)))];
  for (const target of targets) statWithoutSymlink(target);
}

function statWithoutSymlink(target) {
  const homeRoot = os.homedir();
  const relative = path.relative(homeRoot, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) throw new Error("Guard target is outside the selected home.");
  let cursor = target;
  while (cursor !== path.dirname(homeRoot)) {
    try { if (fs.lstatSync(cursor).isSymbolicLink()) throw new Error("A managed guard target or parent is a symlink; no files were changed."); }
    catch (error) { if (error.code !== "ENOENT") throw error; }
    cursor = path.dirname(cursor);
  }
  try { return fs.lstatSync(target); }
  catch (error) { if (error.code === "ENOENT") return null; throw error; }
}

function readIfExists(p) { return fs.existsSync(p) ? fs.readFileSync(p) : null; }
function sha256(buf) { return crypto.createHash("sha256").update(buf).digest("hex"); }

// Git for Windows' default core.autocrlf=true rewrites LF to CRLF on checkout, so the on-disk
// bytes of a reviewed file can differ from the git blob by line endings alone. Normalize pure
// CRLF to LF before hashing and nothing else: a CR is dropped only when immediately followed by
// LF, so a bare trailing CR (or any other byte change) still fails closed. Byte-level, so
// non-UTF-8 content is never mangled.
function normalizeLf(buf) {
  const out = [];
  for (let index = 0; index < buf.length; index += 1) {
    if (buf[index] === 0x0d && buf[index + 1] === 0x0a) continue;
    out.push(buf[index]);
  }
  return Buffer.from(out);
}

// Reviewed local files are pinned by LF-normalized hash; everything else (the downloaded
// canonical release) is pinned by exact bytes and never goes through this helper.
function matchesReviewedHash(buf, expected) {
  return sha256(buf) === expected || sha256(normalizeLf(buf)) === expected;
}

function fail(message) {
  throw new Error(message);
}
