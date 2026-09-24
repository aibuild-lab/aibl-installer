#!/usr/bin/env node
// Hermetic test for hooks/refresh-guard.mjs (PR #62 review, 8Dvibes). Runs the REAL updater
// against a throwaway HOME + a throwaway repo (copied script + temp manifest) + a local source
// dir (GUARD_SOURCE_DIR). No network. Proves: pinned-hash verification, no partial write on a
// hash mismatch, settings ALWAYS repaired even when nothing changed, user-global health checks,
// session-safe diagnostics, and fail-safe behavior when the release is unpinned.
// Run: `node hooks/refresh-guard.test.mjs`.

import { spawnSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REAL_SCRIPT = fileURLToPath(import.meta.url).replace(/\.test\.mjs$/, ".mjs");
const REAL_LOCAL_FILES = [
  "aws-credential-patterns.mjs", "aws-credential-guard.mjs", "aws-credential-tripwire.mjs",
  "codex-secrets-guard.mjs", "codex-secrets-tripwire.mjs",
]
  .map((name) => [name, path.join(path.dirname(REAL_SCRIPT), name)]);
const sha256 = (s) => crypto.createHash("sha256").update(s).digest("hex");
// The trust manifest pins LF-normalized content, so manifest regeneration must normalize the
// same way the guard does (pure CRLF -> LF, nothing else); a CRLF checkout must not change the
// pinned hashes, and a bare trailing CR must still change them.
const normalizeLf = (buf) => Buffer.from(buf.toString("utf8").replaceAll("\r\n", "\n"), "utf8");

const failures = [];
const check = (name, cond) => {
  if (cond) console.log(`ok   - ${name}`);
  else { failures.push(name); console.error(`FAIL - ${name}`); }
};

// --- scratch layout ---
const root = fs.mkdtempSync(path.join(os.tmpdir(), "refresh-guard-"));
const home = path.join(root, "home");
const src = path.join(root, "src");
const repo = path.join(root, "repo");
fs.mkdirSync(home, { recursive: true });
fs.mkdirSync(src, { recursive: true });
fs.mkdirSync(path.join(repo, "hooks"), { recursive: true });

const REQUIRED_DENY = [
  "Read(.env)", "Read(**/.env)", "Read(**/.env.local)", "Read(**/.env.*.local)",
  "Read(**/*.pem)", "Read(**/id_rsa)", "Read(**/id_ed25519)", "Read(**/credentials*)",
  "Read(**/.env.*)", "Read(**/secrets/**)",
];

// The updater runs the installer it just placed. This deterministic stub records each run and
// writes the same canonical user-level hook shape as the reviewed installer.
const STUB = {
  "secrets-guard.js": "#!/usr/bin/env node\nprocess.exit(0);\n",
  "secrets-tripwire.js": "#!/usr/bin/env node\nprocess.exit(0);\n",
  "install.mjs":
    "import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path';\n" +
    "const m = path.join(os.homedir(), '.claude', 'installer-runs.txt');\n" +
    "fs.mkdirSync(path.dirname(m), { recursive: true });\n" +
    "fs.appendFileSync(m, 'ran\\n');\n" +
    "const settingsPath = path.join(os.homedir(), '.claude', 'settings.json');\n" +
    "let settings = {};\n" +
    "if (fs.existsSync(settingsPath)) { try { settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8')); } catch { process.exit(1); } }\n" +
    `settings.permissions = { ...(settings.permissions ?? {}), deny: ${JSON.stringify(REQUIRED_DENY)} };\n` +
    "const node = (process.env.CLAUDE_HOOK_NODE || process.execPath).split(path.sep).join('/');\n" +
    "const hook = (name) => path.join(os.homedir(), '.claude', 'hooks', name).split(path.sep).join('/');\n" +
    "settings.hooks = { ...(settings.hooks ?? {}),\n" +
    "  PreToolUse: [{ matcher: 'Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit', hooks: [{ type: 'command', command: `\\\"${node}\\\" \\\"${hook('secrets-guard.js')}\\\"` }] }],\n" +
    "  PostToolUse: [{ matcher: 'Bash|PowerShell', hooks: [{ type: 'command', command: `\\\"${node}\\\" \\\"${hook('secrets-tripwire.js')}\\\"` }] }],\n" +
    "  PostToolUseFailure: [{ matcher: 'Bash|PowerShell', hooks: [{ type: 'command', command: `\\\"${node}\\\" \\\"${hook('secrets-tripwire.js')}\\\"` }] }],\n" +
    "};\n" +
    "fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2) + '\\n');\n",
};
for (const [name, body] of Object.entries(STUB)) fs.writeFileSync(path.join(src, name), body);

// Copy the real updater into the throwaway repo so it resolves OUR temp manifest (beside it in hooks/).
fs.copyFileSync(REAL_SCRIPT, path.join(repo, "hooks", "refresh-guard.mjs"));
const LOCAL_FILES = {};
for (const [name, source] of REAL_LOCAL_FILES) {
  const body = fs.readFileSync(source);
  LOCAL_FILES[name] = body;
  fs.copyFileSync(source, path.join(repo, "hooks", name));
}
const manifestPath = path.join(repo, "hooks", "secrets-guard.manifest.json");
const writeManifest = (ref, bodies) => fs.writeFileSync(manifestPath, JSON.stringify({
  ref,
  files: Object.fromEntries(Object.entries(bodies).map(([n, b]) => [n, sha256(b)])),
  local_files: Object.fromEntries(Object.entries(LOCAL_FILES).map(([n, b]) => [n, sha256(normalizeLf(b))])),
}, null, 2));

const run = (args = []) => spawnSync(process.execPath, [path.join(repo, "hooks", "refresh-guard.mjs"), ...args], {
  env: { ...process.env, HOME: home, USERPROFILE: home, GUARD_SOURCE_DIR: src },
  encoding: "utf8",
});
const installerRuns = () => {
  const f = path.join(home, ".claude", "installer-runs.txt");
  return fs.existsSync(f) ? fs.readFileSync(f, "utf8").trim().split("\n").filter(Boolean).length : 0;
};
const installed = (name) => {
  const f = path.join(home, ".claude", "hooks", name);
  return fs.existsSync(f) ? fs.readFileSync(f, "utf8") : null;
};
const codexInstalled = (name) => {
  const f = path.join(home, ".codex", "hooks", name);
  return fs.existsSync(f) ? fs.readFileSync(f) : null;
};

// === Phase 0: the Node path written into every hook command ===
// Importing the real script must NOT run the installer (isMainModule guards that).
const { pickStableNode } = await import(pathToFileURL(REAL_SCRIPT).href);
check("importing refresh-guard.mjs installs nothing", !fs.existsSync(path.join(home, ".claude")) && !fs.existsSync(path.join(home, ".codex")));
{
  // process.execPath through Homebrew's symlink is the versioned Cellar path, which `brew upgrade node`
  // deletes. The picker must return the launcher instead, but only when it is the SAME binary.
  const cellar = "/opt/homebrew/Cellar/node/25.6.1/bin/node";
  const brewOnly = (p) => (p === "/opt/homebrew/bin/node" || p === cellar ? cellar : null);
  check("Homebrew Cellar path is replaced by the stable launcher",
    pickStableNode(cellar, ["/opt/homebrew/bin/node", "/usr/local/bin/node"], brewOnly) === "/opt/homebrew/bin/node");
  const nvmNode = "/Users/s/.nvm/versions/node/v25.6.1/bin/node";
  const otherNode = (p) => (p === "/opt/homebrew/bin/node" ? "/opt/homebrew/Cellar/node/24.0.0/bin/node" : p === nvmNode ? p : null);
  check("a launcher for a DIFFERENT Node is never substituted", pickStableNode(nvmNode, ["/opt/homebrew/bin/node"], otherNode) === nvmNode);
  check("no launcher present keeps execPath", pickStableNode(cellar, ["/opt/homebrew/bin/node"], (p) => (p === cellar ? cellar : null)) === cellar);
  check("unresolvable execPath is returned unchanged", pickStableNode("/nowhere/node", ["/opt/homebrew/bin/node"], () => null) === "/nowhere/node");
  if (process.platform === "win32") {
    const exe = "C:\\Program Files\\nodejs\\node.exe";
    check("Windows path comparison ignores case", pickStableNode("c:\\program files\\nodejs\\node.exe", [exe], (p) => p.toUpperCase()) === exe);
  }
}
// What THIS machine's install should write: the launcher when Node came from Homebrew or Program
// Files, otherwise the running binary. Every hook command below must use exactly this path.
const expectedNode = pickStableNode(process.execPath).split(path.sep).join("/");
const hookNodeOf = (command) => (typeof command === "string" ? command.match(/^"([^"]+)"/)?.[1] ?? null : null);

// === Phase A: missing install is detected; valid pinned manifest installs and verifies ===
writeManifest("test-ref", STUB);
const missing = run(["--check"]);
check("missing user-global installation fails health check", missing.status !== 0 && /On-disk status: incomplete/.test(missing.stdout));
const missingSession = run(["--session-check"]);
check("session check reports missing protection without blocking startup", missingSession.status === 0 && /run node hooks\/refresh-guard\.mjs/.test(missingSession.stdout));

const a1 = run();
check("first run succeeds", a1.status === 0);
check("all three hooks installed", STUB["secrets-guard.js"] === installed("secrets-guard.js")
  && STUB["install.mjs"] === installed("install.mjs")
  && STUB["secrets-tripwire.js"] === installed("secrets-tripwire.js"));
check("Claude receives the checksum-pinned AWS credential supplement",
  LOCAL_FILES["aws-credential-patterns.mjs"].equals(Buffer.from(installed("aws-credential-patterns.mjs")))
  && LOCAL_FILES["aws-credential-guard.mjs"].equals(Buffer.from(installed("aws-credential-guard.mjs")))
  && LOCAL_FILES["aws-credential-tripwire.mjs"].equals(Buffer.from(installed("aws-credential-tripwire.mjs"))));
check("Codex receives the pinned hooks and reviewed adapters",
  Buffer.from(STUB["secrets-guard.js"]).equals(codexInstalled("secrets-guard.js"))
  && Buffer.from(STUB["secrets-tripwire.js"]).equals(codexInstalled("secrets-tripwire.js"))
  && LOCAL_FILES["aws-credential-patterns.mjs"].equals(codexInstalled("aws-credential-patterns.mjs"))
  && LOCAL_FILES["codex-secrets-guard.mjs"].equals(codexInstalled("codex-secrets-guard.mjs"))
  && LOCAL_FILES["codex-secrets-tripwire.mjs"].equals(codexInstalled("codex-secrets-tripwire.mjs")));
const claudeSettings = JSON.parse(fs.readFileSync(path.join(home, ".claude", "settings.json"), "utf8"));
check("Claude AWS supplement covers every local tool path before and after use",
  claudeSettings.hooks.PreToolUse.some((group) =>
    group.matcher === "*"
    && group.hooks?.[0]?.command?.includes("aws-credential-guard.mjs"))
  && claudeSettings.hooks.PostToolUse.some((group) =>
    group.matcher === "*" && group.hooks?.[0]?.command?.includes("aws-credential-tripwire.mjs"))
  && claudeSettings.hooks.PostToolUseFailure.some((group) =>
    group.matcher === "*" && group.hooks?.[0]?.command?.includes("aws-credential-tripwire.mjs")));
check("every Claude hook command runs the stable Node path (canonical guard via CLAUDE_HOOK_NODE, supplements directly)",
  ["PreToolUse", "PostToolUse", "PostToolUseFailure"].every((event) =>
    claudeSettings.hooks[event].every((group) => group.hooks.every((hook) => hookNodeOf(hook.command) === expectedNode))));
const codexHooksPath = path.join(home, ".codex", "hooks.json");
const codexHooks = JSON.parse(fs.readFileSync(codexHooksPath, "utf8"));
// Codex runs `command` through the session's shell (PowerShell on Windows), so these register a
// platform launcher (.cmd / .sh) rather than the adapter directly. A quoted `"<node>" "<script>"`
// value fails to launch there, and Codex FAILS OPEN.
const launcherExt = process.platform === "win32" ? ".cmd" : ".sh";
const codexLauncher = (base) => `${base}${launcherExt}`;
// Launch a hooks.json command the way Codex does: `cmd /C "<command>"` (raw) when no shell is known,
// `<powershell> -NoProfile -Command <command>` for a Windows PowerShell session, `sh -c` elsewhere.
const CODEX_HOOK_SHELLS = process.platform === "win32"
  ? {
      "cmd /C": (command, input) => spawnSync("cmd.exe", ["/C", `"${command}"`], { input, encoding: "utf8", windowsVerbatimArguments: true }),
      "Windows PowerShell": (command, input) => spawnSync("powershell.exe", ["-NoProfile", "-Command", command], { input, encoding: "utf8" }),
      "PowerShell 7": (command, input) => spawnSync("pwsh.exe", ["-NoProfile", "-Command", command], { input, encoding: "utf8" }),
    }
  : { "sh -c": (command, input) => spawnSync("sh", ["-c", command], { input, encoding: "utf8" }) };
// The canonical guard is stubbed to allow here, so leak payloads use a rule the ADAPTER owns (its
// AWS credential scan). The value is assembled from fragments and is not a real key.
const leakPayload = JSON.stringify({ tool_name: "Bash", tool_input: { command: `echo ${"ASIA" + "ABCDEFGH12345678"}` } });
const deniedThrough = (result) => {
  if (result.error || result.status !== 0 || !result.stdout) return false;
  try { return JSON.parse(result.stdout)?.hookSpecificOutput?.permissionDecision === "deny"; } catch { return false; }
};
check("Codex supplemental PreToolUse covers every local tool path",
  codexHooks.hooks.PreToolUse.some((group) =>
    group.matcher === "*"
    && group.hooks?.[0]?.command?.includes(codexLauncher("codex-secrets-guard"))));
check("Codex PostToolUse uses the names-only compatibility adapter",
  codexHooks.hooks.PostToolUse.some((group) =>
    group.matcher === "*"
    && group.hooks?.[0]?.command?.includes(codexLauncher("codex-secrets-tripwire"))));
check(process.platform === "win32"
    ? "Codex hook command is `cmd /d /c \"<launcher>\"` (survives PowerShell and a space in the path)"
    : "Codex hook command is the bare launcher path",
  ["PreToolUse", "PostToolUse"].every((event) => codexHooks.hooks[event].every((group) =>
    group.hooks.every((hook) => process.platform === "win32"
      ? /^cmd \/d \/c "[^"]+\.cmd"$/.test(hook.command)
      : typeof hook.command === "string" && !/^\s*"/.test(hook.command)))));
check("Codex launcher execs the stable Node path", (() => {
  const p = path.join(home, ".codex", "hooks", codexLauncher("codex-secrets-guard"));
  // The launcher body quotes the path as the OS spells it; compare on forward slashes.
  const quoted = fs.readFileSync(p, "utf8").match(/"([^"]+)"/)?.[1] ?? "";
  return quoted.split(path.sep).join("/") === expectedNode;
})());
check("Codex launcher exists on disk and invokes its adapter", (() => {
  const p = path.join(home, ".codex", "hooks", codexLauncher("codex-secrets-guard"));
  return fs.existsSync(p) && fs.readFileSync(p, "utf8").includes("codex-secrets-guard.mjs");
})());
// Codex 0.140 and older parse ~/.codex/hooks.json with a STRICT schema: any unknown top-level field
// makes it reject the whole file, warn, and load NO hooks, reporting
// `unknown field \`description\`, expected \`hooks\``. Silent by design gap — the file exists, every
// on-disk health check passes, and the guard simply never runs. Keep this file schema-exact.
check("Codex hooks.json carries no top-level field other than `hooks`",
  JSON.stringify(Object.keys(codexHooks)) === JSON.stringify(["hooks"]));
// The regression test that actually matters: drive the FULL chain the way Codex does, by running the
// registered command through each shell Codex may use, with a leak payload on stdin. Proves the
// guard can be REACHED, which no on-disk hash check can. Codex sends Claude's dialect (tool_name
// "Bash", command a string). A shell that is not installed here is reported and skipped.
for (const [shell, launch] of Object.entries(CODEX_HOOK_SHELLS)) {
  const probe = launch(codexHooks.hooks.PreToolUse[0].hooks[0].command, leakPayload);
  if (probe.error?.code === "ENOENT") { console.log(`skip - ${shell} is not installed on this machine`); continue; }
  check(`leak payload through the registered hook command is DENIED under ${shell} (end-to-end chain)`, deniedThrough(probe));
}
check("installer ran once", installerRuns() === 1);
check("first run verifies user-global on-disk scope", /on-disk installation verified/.test(a1.stdout));
check("installer distinguishes runtime activation from disk health",
  /Runtime activation is not observable/.test(a1.stdout) && /Manual proof required/.test(a1.stdout));

const healthy = run(["--check"]);
check("healthy user-global installation passes check mode", healthy.status === 0 && /On-disk status: healthy/.test(healthy.stdout));
check("human check requires manual runtime proof",
  /Runtime activation: not observable/.test(healthy.stdout) && /Manual proof required/.test(healthy.stdout));
const healthyJson = run(["--check", "--json"]);
const parsedHealthyJson = JSON.parse(healthyJson.stdout);
check("JSON check reports deterministic per-client disk health",
  healthyJson.status === 0
  && parsedHealthyJson.schemaVersion === 1
  && parsedHealthyJson.onDisk.status === "healthy"
  && parsedHealthyJson.onDisk.claude.status === "healthy"
  && parsedHealthyJson.onDisk.codex.status === "healthy"
  && parsedHealthyJson.runtime.status === "manual-proof-required"
  && parsedHealthyJson.runtime.observableFromInstaller === false
  && parsedHealthyJson.ownership.status === "installer-managed"
  && parsedHealthyJson.ownership.receipt.owner === "aibl-installer"
  && parsedHealthyJson.ownership.receipt.source.location === fs.realpathSync(repo)
  && parsedHealthyJson.ownership.receipt.clients.join(",") === "claude,codex");
const receiptPath = path.join(home, ".claude", "hooks", "aibl-installer-guard-receipt.json");
fs.writeFileSync(receiptPath, "{broken");
const damagedReceipt = run(["--check", "--json"]);
check("damaged ownership receipt is reported without hiding healthy guard files",
  damagedReceipt.status === 0 && JSON.parse(damagedReceipt.stdout).ownership.status === "invalid");
const badJsonMode = run(["--json"]);
check("--json is accepted only with --check", badJsonMode.status !== 0 && /Use --json with --check/.test(badJsonMode.stderr));
const healthySession = run(["--session-check"]);
check("healthy session check is silent", healthySession.status === 0 && healthySession.stdout === "");

const a2 = run();
check("second run succeeds with nothing changed", a2.status === 0 && /already current/.test(a2.stdout));
check("installer ALWAYS re-runs to repair settings even when no file changed", installerRuns() === 2);

// === Phase B: stale wiring, missing files, stale files, and malformed settings are diagnosed ===
const settingsPath = path.join(home, ".claude", "settings.json");
const canonicalSettings = fs.readFileSync(settingsPath, "utf8");
const staleSettings = JSON.parse(canonicalSettings);
staleSettings.hooks.PreToolUse[0].matcher = "Bash|PowerShell";
fs.writeFileSync(settingsPath, JSON.stringify(staleSettings, null, 2));
const staleMatcher = run(["--check"]);
check("old narrow matcher is unhealthy", staleMatcher.status !== 0 && /canonical matcher group/.test(staleMatcher.stdout));
const repairedMatcher = run();
check("normal refresh repairs stale settings wiring", repairedMatcher.status === 0 && /on-disk installation verified/.test(repairedMatcher.stdout));

const disabledSettings = JSON.parse(fs.readFileSync(settingsPath, "utf8"));
disabledSettings.disableAllHooks = true;
fs.writeFileSync(settingsPath, JSON.stringify(disabledSettings, null, 2));
const disabled = run(["--check"]);
check("disableAllHooks prevents a healthy global status", disabled.status !== 0 && /disableAllHooks enabled/.test(disabled.stdout));
const disabledRepair = run();
check("refresh does not silently override the user's disableAllHooks choice", disabledRepair.status !== 0);
delete disabledSettings.disableAllHooks;
fs.writeFileSync(settingsPath, JSON.stringify(disabledSettings, null, 2));

const missingDenySettings = JSON.parse(fs.readFileSync(settingsPath, "utf8"));
missingDenySettings.permissions.deny = missingDenySettings.permissions.deny.slice(1);
fs.writeFileSync(settingsPath, JSON.stringify(missingDenySettings, null, 2));
const missingDeny = run(["--check"]);
check("missing read-deny rules are unhealthy", missingDeny.status !== 0 && /read deny rules are incomplete/.test(missingDeny.stdout));
check("refresh repairs missing read-deny rules", run().status === 0);

const missingNodeSettings = JSON.parse(fs.readFileSync(settingsPath, "utf8"));
missingNodeSettings.hooks.PreToolUse[0].hooks[0].command = `"${path.join(root, "missing-node")}" "${path.join(home, ".claude", "hooks", "secrets-guard.js")}"`;
fs.writeFileSync(settingsPath, JSON.stringify(missingNodeSettings, null, 2));
const missingNode = run(["--check"]);
check("missing absolute Node runtime is unhealthy", missingNode.status !== 0 && /missing or non-absolute Node runtime/.test(missingNode.stdout));
check("refresh repairs the stale Node runtime path", run().status === 0);
check("the repaired command uses the stable Node path (the brew-upgrade case, fixed by one re-run)",
  hookNodeOf(JSON.parse(fs.readFileSync(settingsPath, "utf8")).hooks.PreToolUse[0].hooks[0].command) === expectedNode);

const staleCodex = JSON.parse(fs.readFileSync(codexHooksPath, "utf8"));
staleCodex.hooks.PreToolUse.find((group) =>
  group.hooks?.some((hook) => hook.command?.includes(codexLauncher("codex-secrets-guard"))),
).matcher = "Bash";
fs.writeFileSync(codexHooksPath, JSON.stringify(staleCodex, null, 2));
const staleCodexMatcher = run(["--check"]);
check("stale Codex matcher is unhealthy", staleCodexMatcher.status !== 0 && /Codex:.*canonical matcher group/.test(staleCodexMatcher.stdout));
check("refresh repairs Codex supplemental PreToolUse to all local tools", run().status === 0
  && JSON.parse(fs.readFileSync(codexHooksPath, "utf8")).hooks.PreToolUse.some((group) =>
    group.matcher === "*" && group.hooks?.some((hook) => hook.command?.includes(codexLauncher("codex-secrets-guard")))));

const narrowCodexPost = JSON.parse(fs.readFileSync(codexHooksPath, "utf8"));
narrowCodexPost.hooks.PostToolUse.find((group) =>
  group.hooks?.some((hook) => hook.command?.includes(codexLauncher("codex-secrets-tripwire"))),
).matcher = "Bash|PowerShell";
fs.writeFileSync(codexHooksPath, JSON.stringify(narrowCodexPost, null, 2));
const narrowCodexPostStatus = run(["--check"]);
check("shell-only Codex PostToolUse coverage is unhealthy",
  narrowCodexPostStatus.status !== 0 && /Codex:.*canonical matcher group/.test(narrowCodexPostStatus.stdout));
check("refresh widens Codex PostToolUse to all local tool paths", run().status === 0
  && JSON.parse(fs.readFileSync(codexHooksPath, "utf8")).hooks.PostToolUse.some((group) =>
    group.matcher === "*" && group.hooks?.some((hook) => hook.command?.includes(codexLauncher("codex-secrets-tripwire")))));

// An install that already carries the schema-breaking `description` must be REPAIRED, not merely
// left alone. Earlier releases wrote it, so a returning student has an inert guard sitting on disk.
const withDescription = JSON.parse(fs.readFileSync(codexHooksPath, "utf8"));
withDescription.description = "User-global secret protection installed by Agent Native OS.";
fs.writeFileSync(codexHooksPath, JSON.stringify(withDescription, null, 2));
const descriptionRepair = run();
check("a pre-existing `description` field is removed from Codex hooks.json",
  descriptionRepair.status === 0
  && JSON.stringify(Object.keys(JSON.parse(fs.readFileSync(codexHooksPath, "utf8")))) === JSON.stringify(["hooks"]));
check("the `description` repair is reported in plain language",
  /Removed a `description` field from ~\/\.codex\/hooks\.json/.test(descriptionRepair.stdout));

const codexConfigPath = path.join(home, ".codex", "config.toml");
fs.writeFileSync(codexConfigPath, "[features]\nhooks = false\n");
const codexDisabled = run(["--check"]);
check("Codex feature flag cannot silently disable the guard", codexDisabled.status !== 0 && /disables lifecycle hooks/.test(codexDisabled.stdout));
fs.writeFileSync(codexConfigPath, "[features]\nhooks = true\n");
check("enabled Codex hooks feature restores healthy status", run(["--check"]).status === 0);

const narrowClaudeSupplement = JSON.parse(fs.readFileSync(settingsPath, "utf8"));
narrowClaudeSupplement.hooks.PreToolUse.find((group) =>
  group.hooks?.some((hook) => hook.command?.includes("aws-credential-guard.mjs")),
).matcher = "Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit";
narrowClaudeSupplement.hooks.PostToolUse.find((group) =>
  group.hooks?.some((hook) => hook.command?.includes("aws-credential-tripwire.mjs")),
).matcher = "Bash|PowerShell";
fs.writeFileSync(settingsPath, JSON.stringify(narrowClaudeSupplement, null, 2));
const narrowClaudeSupplementStatus = run(["--check"]);
check("narrow Claude AWS supplement is unhealthy",
  narrowClaudeSupplementStatus.status !== 0 && /Claude Code:.*canonical matcher group/.test(narrowClaudeSupplementStatus.stdout));
check("refresh restores all-tool Claude AWS input and output coverage", run().status === 0
  && JSON.parse(fs.readFileSync(settingsPath, "utf8")).hooks.PreToolUse.some((group) =>
    group.matcher === "*" && group.hooks?.some((hook) => hook.command?.includes("aws-credential-guard.mjs"))));

fs.rmSync(path.join(home, ".claude", "hooks", "secrets-tripwire.js"));
const missingTripwire = run(["--check"]);
check("missing tripwire is unhealthy", missingTripwire.status !== 0 && /secrets-tripwire\.js is missing/.test(missingTripwire.stdout));
check("refresh restores a missing tripwire", run().status === 0);

fs.rmSync(path.join(home, ".claude", "hooks", "aws-credential-guard.mjs"));
const missingAwsSupplement = run(["--check"]);
check("missing Claude AWS supplement is unhealthy",
  missingAwsSupplement.status !== 0 && /aws-credential-guard\.mjs is missing/.test(missingAwsSupplement.stdout));
check("refresh restores a missing Claude AWS supplement", run().status === 0);

fs.writeFileSync(path.join(home, ".claude", "hooks", "secrets-guard.js"), "#!/usr/bin/env node\n// stale\n");
const staleGuard = run(["--check"]);
check("stale guard bytes are unhealthy", staleGuard.status !== 0 && /does not match the pinned release/.test(staleGuard.stdout));
check("refresh restores stale guard bytes", run().status === 0);

const validSettings = fs.readFileSync(settingsPath, "utf8");
fs.writeFileSync(settingsPath, "{ not json");
const malformed = run(["--check"]);
check("malformed user settings fail closed", malformed.status !== 0 && /not valid JSON/.test(malformed.stdout));
const malformedRepair = run();
check("refresh does not overwrite malformed user settings", malformedRepair.status !== 0);
fs.writeFileSync(settingsPath, validSettings);

const validCodexHooks = fs.readFileSync(codexHooksPath, "utf8");
fs.writeFileSync(codexHooksPath, "{ not json");
const malformedCodex = run(["--check"]);
check("malformed Codex hooks fail closed", malformedCodex.status !== 0 && /hooks\.json is not valid JSON/.test(malformedCodex.stdout));
const malformedCodexRepair = run();
check("refresh does not overwrite malformed Codex hooks", malformedCodexRepair.status !== 0
  && fs.readFileSync(codexHooksPath, "utf8") === "{ not json");
fs.writeFileSync(codexHooksPath, validCodexHooks);

// === Phase C: tampered source (hash != manifest) -> fail safe, no partial write ===
fs.writeFileSync(path.join(src, "secrets-guard.js"), "#!/usr/bin/env node\n// tampered\nprocess.exit(0);\n");
const runsBeforeTamper = installerRuns();
const b = run();
check("tampered download is rejected (non-zero exit)", b.status !== 0);
check("tamper error explains the hash mismatch", /does not match the pinned release hash/.test(b.stderr));
check("no partial write: installed guard is still the pinned bytes", installed("secrets-guard.js") === STUB["secrets-guard.js"]);
check("installer did NOT run on the rejected update", installerRuns() === runsBeforeTamper);
fs.writeFileSync(path.join(src, "secrets-guard.js"), STUB["secrets-guard.js"]); // restore

const codexAdapterPath = path.join(repo, "hooks", "codex-secrets-guard.mjs");
const validCodexAdapter = fs.readFileSync(codexAdapterPath);
fs.writeFileSync(codexAdapterPath, "#!/usr/bin/env node\n// tampered\n");
const tamperedAdapter = run();
check("tampered Codex adapter is rejected", tamperedAdapter.status !== 0 && /does not match its reviewed manifest hash/.test(tamperedAdapter.stderr));
check("installed Codex adapter remains the reviewed bytes",
  LOCAL_FILES["codex-secrets-guard.mjs"].equals(codexInstalled("codex-secrets-guard.mjs")));
fs.writeFileSync(codexAdapterPath, validCodexAdapter);

const supplementPath = path.join(repo, "hooks", "aws-credential-patterns.mjs");
const validSupplement = fs.readFileSync(supplementPath);
fs.writeFileSync(supplementPath, "// tampered AWS supplement\n");
const tamperedSupplement = run();
check("tampered AWS supplement is rejected",
  tamperedSupplement.status !== 0 && /does not match its reviewed manifest hash/.test(tamperedSupplement.stderr));
check("installed Claude AWS supplement remains the reviewed bytes",
  LOCAL_FILES["aws-credential-patterns.mjs"].equals(Buffer.from(installed("aws-credential-patterns.mjs"))));
fs.writeFileSync(supplementPath, validSupplement);

// === Phase E: a CRLF checkout (Git for Windows core.autocrlf=true) is not tampering ===
const lfSupplement = fs.readFileSync(supplementPath);
const crlfSupplement = Buffer.from(lfSupplement.toString("utf8").replaceAll("\n", "\r\n"), "utf8");
fs.writeFileSync(supplementPath, crlfSupplement);
const crlfRun = run();
check("CRLF-only difference passes the guard (Windows checkout)", crlfRun.status === 0);
check("CRLF case says line endings, not tampering",
  /same content, different line endings \(CRLF vs LF\); normalize line endings or see \.gitattributes/.test(crlfRun.stdout));
const crlfHealthy = run(["--check"]);
check("installed CRLF-variant supplement passes the health check", crlfHealthy.status === 0);

const crlfTampered = Buffer.from(`${lfSupplement.toString("utf8").replaceAll("\n", "\r\n")}// real tamper\r\n`, "utf8");
fs.writeFileSync(supplementPath, crlfTampered);
const crlfTamperRun = run();
check("CRLF plus a real modification still fails closed",
  crlfTamperRun.status !== 0 && /does not match its reviewed manifest hash/.test(crlfTamperRun.stderr));
check("real tamper keeps the tampering error, not the line-endings note",
  !/different line endings/.test(crlfTamperRun.stdout) && !/different line endings/.test(crlfTamperRun.stderr));
check("no partial write: installed supplement is still the reviewed content",
  normalizeLf(Buffer.from(installed("aws-credential-patterns.mjs"))).equals(normalizeLf(LOCAL_FILES["aws-credential-patterns.mjs"])));

// A bare trailing CR is not a line-ending difference; it is a byte change and must fail closed.
const trailingCr = Buffer.from(`${lfSupplement.toString("utf8").replace(/\n$/, "")}\r`, "utf8");
fs.writeFileSync(supplementPath, trailingCr);
const trailingCrRun = run();
check("appended bare CR (no final newline) still fails closed",
  trailingCrRun.status !== 0 && /does not match its reviewed manifest hash/.test(trailingCrRun.stderr));
check("bare-CR tamper is not mislabeled as a line-endings difference",
  !/different line endings/.test(trailingCrRun.stdout) && !/different line endings/.test(trailingCrRun.stderr));
check("no partial write on the bare-CR tamper either",
  normalizeLf(Buffer.from(installed("aws-credential-patterns.mjs"))).equals(normalizeLf(LOCAL_FILES["aws-credential-patterns.mjs"])));
fs.writeFileSync(supplementPath, lfSupplement);
check("restored LF supplement installs cleanly after the CRLF cases", run().status === 0);

// === Phase D: unpinned manifest -> fail safe, never falls back to a mutable branch ===
writeManifest("REPLACE_AT_RELEASE", STUB);
const c = run();
check("unpinned manifest fails safe (non-zero exit)", c.status !== 0);
// --- a student's own global instruction files are never touched ---
{
  const mine = path.join(root, "mine");
  writeManifest("good", STUB); // the unpinned case above deliberately left a manifest with no ref
  fs.mkdirSync(path.join(mine, ".claude"), { recursive: true });
  fs.mkdirSync(path.join(mine, ".codex"), { recursive: true });
  const claudeMd = ["# My global rules", "Always answer in French.", ""].join("\n");
  const agentsMd = ["# My Codex rules", "Never touch prod.", ""].join("\n");
  const priorSettings = JSON.stringify({ theme: "dark", permissions: { allow: ["Bash(ls:*)"] } }, null, 2) + "\n";
  fs.writeFileSync(path.join(mine, ".claude", "CLAUDE.md"), claudeMd);
  fs.writeFileSync(path.join(mine, ".codex", "AGENTS.md"), agentsMd);
  fs.writeFileSync(path.join(mine, ".claude", "settings.json"), priorSettings);
  const r = spawnSync(process.execPath, [path.join(repo, "hooks", "refresh-guard.mjs")], {
    env: { ...process.env, HOME: mine, USERPROFILE: mine, GUARD_SOURCE_DIR: src }, encoding: "utf8",
  });
  check("install succeeds beside a student's own global files", r.status === 0);
  if (r.status !== 0) console.error(`[global-files case] exit ${r.status}\n${r.stderr}\n${r.stdout.slice(-400)}`);
  check("student's global ~/.claude/CLAUDE.md is byte-identical after install", fs.readFileSync(path.join(mine, ".claude", "CLAUDE.md"), "utf8") === claudeMd);
  check("student's global ~/.codex/AGENTS.md is byte-identical after install", fs.readFileSync(path.join(mine, ".codex", "AGENTS.md"), "utf8") === agentsMd);
  const merged = JSON.parse(fs.readFileSync(path.join(mine, ".claude", "settings.json"), "utf8"));
  check("student's existing settings keys survive the merge", merged.theme === "dark" && merged.permissions.allow.includes("Bash(ls:*)"));
}

// --- opt-in per app: --claude must not touch ~/.codex, --codex must not touch ~/.claude ---
{
  const only = path.join(root, "only");
  fs.mkdirSync(only, { recursive: true });
  writeManifest("good", STUB);
  const runOnly = (flags) => spawnSync(process.execPath, [path.join(repo, "hooks", "refresh-guard.mjs"), ...flags], {
    env: { ...process.env, HOME: only, USERPROFILE: only, GUARD_SOURCE_DIR: src }, encoding: "utf8",
  });
  const c = runOnly(["--claude"]);
  check("--claude installs the Claude guard", c.status === 0 && fs.existsSync(path.join(only, ".claude", "hooks", "secrets-guard.js")));
  check("--claude leaves ~/.codex untouched", !fs.existsSync(path.join(only, ".codex")));
  const cc = runOnly(["--check", "--claude", "--json"]);
  check("--check --claude is healthy and reports Codex as not selected", cc.status === 0 && /"status": "not selected"/.test(cc.stdout));
  const x = runOnly(["--codex"]);
  check("--codex installs the Codex guard", x.status === 0 && fs.existsSync(path.join(only, ".codex", "hooks.json")));
  const both = runOnly(["--check", "--json"]);
  check("after both opt-ins, the no-flag check sees both as healthy", both.status === 0 && !/not selected|incomplete/.test(both.stdout));
}

// --- a Windows account folder whose name has a space (student report 09-24-2026) ---
// Codex runs hook commands through PowerShell on Windows. The old bare launcher path was split at
// the space, the hook failed to launch (`hook: PreToolUse Failed`), and Codex ran the tool call
// unguarded. Every other check in this file uses a home path without a space, so none caught it.
if (process.platform === "win32") {
  const spaced = path.join(root, "First Last");
  fs.mkdirSync(spaced, { recursive: true });
  writeManifest("good", STUB);
  const runSpaced = (flags) => spawnSync(process.execPath, [path.join(repo, "hooks", "refresh-guard.mjs"), ...flags], {
    env: { ...process.env, HOME: spaced, USERPROFILE: spaced, GUARD_SOURCE_DIR: src }, encoding: "utf8",
  });
  check("--codex installs under an account folder with a space", runSpaced(["--codex"]).status === 0);
  const spacedHooksPath = path.join(spaced, ".codex", "hooks.json");
  const spacedHooks = JSON.parse(fs.readFileSync(spacedHooksPath, "utf8"));
  const preCommand = spacedHooks.hooks.PreToolUse[0].hooks[0].command;
  const postCommand = spacedHooks.hooks.PostToolUse[0].hooks[0].command;
  for (const [shell, launch] of Object.entries(CODEX_HOOK_SHELLS)) {
    const pre = launch(preCommand, leakPayload);
    if (pre.error?.code === "ENOENT") { console.log(`skip - ${shell} is not installed on this machine`); continue; }
    check(`space in account folder: leak is DENIED through the PreToolUse command under ${shell}`, deniedThrough(pre));
    const post = launch(postCommand, JSON.stringify({ tool_name: "Bash", tool_response: { stdout: "ordinary output" } }));
    check(`space in account folder: the PostToolUse command launches under ${shell}`, post.status === 0);
  }
  // Pin the bug itself, so a future "simplification" back to the bare path fails here.
  const bareLauncher = path.join(spaced, ".codex", "hooks", codexLauncher("codex-secrets-guard")).replaceAll("\\", "/");
  check("the old bare-path form FAILS under Windows PowerShell with a space (the bug this guards against)",
    !deniedThrough(CODEX_HOOK_SHELLS["Windows PowerShell"](bareLauncher, leakPayload)));
  // An install made before the fix is flagged by --check and repaired by --codex.
  const oldShape = structuredClone(spacedHooks);
  oldShape.hooks.PreToolUse[0].hooks[0].command = bareLauncher;
  fs.writeFileSync(spacedHooksPath, JSON.stringify(oldShape, null, 2) + "\n");
  const stale = runSpaced(["--check", "--codex"]);
  check("--check flags the old Windows form and says how to repair it",
    stale.status !== 0 && /old Windows form/.test(stale.stdout + stale.stderr));
  runSpaced(["--codex"]);
  const repaired = JSON.parse(fs.readFileSync(spacedHooksPath, "utf8"));
  check("--codex repairs the old Windows form in place, with exactly one guard hook",
    repaired.hooks.PreToolUse.length === 1 && repaired.hooks.PreToolUse[0].hooks[0].command === preCommand);
  check("after repair, --check --codex is healthy", runSpaced(["--check", "--codex"]).status === 0);
}

check("unpinned error says it is not pinned to a release", /not pinned to a released version/.test(c.stderr));

try { fs.rmSync(root, { recursive: true, force: true }); } catch { /* best effort */ }

console.log(`\n${failures.length ? failures.length + " FAILED" : "all refresh-guard checks passed"}`);
process.exit(failures.length ? 1 : 0);
