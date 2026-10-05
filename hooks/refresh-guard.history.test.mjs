#!/usr/bin/env node
// op-tripwire: detector-rule
// Receipt-free recovery against ACTUAL reviewed historical bytes (R-774 review corrections F-4, F-6).
// Run: `node hooks/refresh-guard.history.test.mjs`
//
// Every installation here lives in a disposable home under the temp directory and is built from
// the exact legacy and R-774 bytes kept in hooks/fixtures/reviewed-history, whose hashes are
// first checked against the pinned compatibility records. The real refresh-guard.mjs in this
// checkout runs unchanged; nothing touches a real account, client, or credential.

import { spawnSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HOOKS = path.dirname(fileURLToPath(import.meta.url));
const SCRIPT = path.join(HOOKS, "refresh-guard.mjs");
const FIXTURES = path.join(HOOKS, "fixtures", "reviewed-history");
const sha = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");
const failures = [];
let checks = 0;
function check(label, ok, detail = "") {
  checks++;
  if (!ok) { failures.push(label); console.error(`FAIL - ${label}${detail ? `\n    ${String(detail).slice(0, 400)}` : ""}`); }
  else console.log(`ok   - ${label}`);
}

// ---- the fixtures are the reviewed bytes, not stand-ins -------------------------------------
const prior = JSON.parse(fs.readFileSync(path.join(HOOKS, "secrets-guard.r774.manifest.json"), "utf8"));
const legacy = JSON.parse(fs.readFileSync(path.join(HOOKS, "secrets-guard.legacy.identities.json"), "utf8"));
const fx = (set, name) => fs.readFileSync(path.join(FIXTURES, set, `${name}.bytes`));
const current = (name) => fs.readFileSync(path.join(HOOKS, name));
for (const name of ["secrets-guard.js", "secrets-tripwire.js", "install.mjs"])
  check(`legacy fixture ${name} is the pinned legacy release`, sha(fx("legacy", name)) === legacy.files[name]);
for (const name of ["secrets-guard.js", "install.mjs"])
  check(`R-774 fixture ${name} is the pinned R-774 release`, sha(fx("r774", name)) === prior.files[name]);
check("the R-774 tripwire is byte-identical to the current tripwire", sha(current("secrets-tripwire.js")) === prior.files["secrets-tripwire.js"]);

// ---- harness ---------------------------------------------------------------------------------
// Not realpath'd: the gated test seams compare the home with os.tmpdir() as the child sees it.
const root = fs.mkdtempSync(path.join(os.tmpdir(), "guard-history-"));
let counter = 0;
const newHome = () => { const home = path.join(root, `home-${++counter}`); fs.mkdirSync(home); return home; };
const run = (home, args = [], env = {}) => spawnSync(process.execPath, [SCRIPT, ...args], {
  env: { ...process.env, HOME: home, USERPROFILE: home, ...env }, encoding: "utf8",
});
const json = (result) => { try { return JSON.parse(result.stdout); } catch { return null; } };
const paths = (home) => ({
  claudeHooks: path.join(home, ".claude", "hooks"), codexHooks: path.join(home, ".codex", "hooks"),
  settings: path.join(home, ".claude", "settings.json"), codexJson: path.join(home, ".codex", "hooks.json"),
  receipt: path.join(home, ".claude", "hooks", "aibl-installer-guard-receipt.json"),
});
function snapshot(home) {
  const entries = [];
  const walk = (directory) => {
    for (const item of fs.readdirSync(directory, { withFileTypes: true })) {
      const target = path.join(directory, item.name);
      if (item.isDirectory()) walk(target);
      else if (item.isSymbolicLink()) entries.push([path.relative(home, target), "link", fs.readlinkSync(target)]);
      else entries.push([path.relative(home, target), fs.statSync(target).mode & 0o777, sha(fs.readFileSync(target))]);
    }
  };
  walk(home);
  return JSON.stringify(entries.sort((a, b) => a[0].localeCompare(b[0])));
}
const put = (file, bytes) => { fs.writeFileSync(file, bytes); fs.chmodSync(file, 0o700); };
const OLD_MATCHER = "Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit";
function useOldMatcher(home) {
  const target = paths(home).settings;
  const value = JSON.parse(fs.readFileSync(target, "utf8"));
  value.hooks.PreToolUse.find((group) => group.hooks?.some((hook) => hook.command?.includes("secrets-guard.js"))).matcher = OLD_MATCHER;
  fs.writeFileSync(target, JSON.stringify(value, null, 2) + "\n");
}
// Unrelated configuration that every migration must leave exactly as it found it.
function addUnrelated(home) {
  const p = paths(home);
  const settings = JSON.parse(fs.readFileSync(p.settings, "utf8"));
  settings.unrelatedKey = { keep: true };
  settings.permissions = { ...(settings.permissions || {}), allow: [...(settings.permissions?.allow || []), "Bash(ls:*)"] };
  (settings.hooks.PreToolUse ||= []).push({ matcher: "Edit", hooks: [{ type: "command", command: "echo unrelated" }] });
  fs.writeFileSync(p.settings, JSON.stringify(settings, null, 2) + "\n");
  if (fs.existsSync(p.codexJson)) {
    const codex = JSON.parse(fs.readFileSync(p.codexJson, "utf8"));
    codex.unrelatedCodexKey = ["keep"];
    fs.writeFileSync(p.codexJson, JSON.stringify(codex, null, 2) + "\n");
  }
  fs.mkdirSync(path.join(home, "project", ".claude"), { recursive: true });
  fs.writeFileSync(path.join(home, "project", ".claude", "settings.json"), '{"projectOnly":true}\n');
  fs.writeFileSync(path.join(home, "project", "CLAUDE.md"), "project instructions\n");
}
function unrelatedPreserved(home) {
  const p = paths(home);
  const settings = JSON.parse(fs.readFileSync(p.settings, "utf8"));
  const codex = fs.existsSync(p.codexJson) ? JSON.parse(fs.readFileSync(p.codexJson, "utf8")) : null;
  return settings.unrelatedKey?.keep === true && settings.permissions.allow.includes("Bash(ls:*)")
    && settings.hooks.PreToolUse.some((group) => group.matcher === "Edit" && group.hooks?.[0]?.command === "echo unrelated")
    && (!codex || codex.unrelatedCodexKey?.[0] === "keep")
    && fs.readFileSync(path.join(home, "project", ".claude", "settings.json"), "utf8") === '{"projectOnly":true}\n'
    && fs.readFileSync(path.join(home, "project", "CLAUDE.md"), "utf8") === "project instructions\n";
}

// Build a receipt-free installation of an exact reviewed topology on top of a current install.
const TOPOLOGIES = {
  // T1: both clients on the pinned legacy release
  "legacy-two": { flags: [], build(home) {
    const p = paths(home);
    for (const name of ["secrets-guard.js", "secrets-tripwire.js", "install.mjs"]) put(path.join(p.claudeHooks, name), fx("legacy", name));
    for (const name of ["secrets-guard.js", "secrets-tripwire.js"]) put(path.join(p.codexHooks, name), fx("legacy", name));
    useOldMatcher(home);
  } },
  // T2: both clients on the R-774 files, ownership receipt absent
  "prior-two": { flags: [], build(home) {
    const p = paths(home);
    for (const name of ["secrets-guard.js", "install.mjs"]) put(path.join(p.claudeHooks, name), fx("r774", name));
    put(path.join(p.codexHooks, "secrets-guard.js"), fx("r774", "secrets-guard.js"));
    useOldMatcher(home);
  } },
  // T3: current bytes with a damaged Claude registration and no receipt
  "current-damaged": { flags: [], build(home) {
    // remove only the guard's own registrations; unrelated hooks stay
    const settings = JSON.parse(fs.readFileSync(paths(home).settings, "utf8"));
    for (const event of Object.keys(settings.hooks)) {
      settings.hooks[event] = settings.hooks[event].filter((group) => !group.hooks?.some((hook) =>
        /secrets-(?:guard|tripwire)|aws-credential/.test(hook.command || "")));
      if (settings.hooks[event].length === 0) delete settings.hooks[event];
    }
    fs.writeFileSync(paths(home).settings, JSON.stringify(settings, null, 2) + "\n");
  } },
  // T4: a legacy Claude-only installation
  "legacy-claude": { flags: ["--claude"], build(home) {
    const p = paths(home);
    for (const name of ["secrets-guard.js", "secrets-tripwire.js", "install.mjs"]) put(path.join(p.claudeHooks, name), fx("legacy", name));
    useOldMatcher(home);
  } },
  // the topology reported from a real learner device
  "recognized-mixed": { flags: [], build(home) {
    const p = paths(home);
    put(path.join(p.claudeHooks, "secrets-guard.js"), fx("r774", "secrets-guard.js"));
    put(path.join(p.claudeHooks, "install.mjs"), fx("legacy", "install.mjs"));
    for (const name of ["secrets-guard.js", "secrets-tripwire.js"]) put(path.join(p.codexHooks, name), fx("legacy", name));
    useOldMatcher(home);
  } },
};
function receiptFreeHome(name) {
  const home = newHome();
  const { flags, build } = TOPOLOGIES[name];
  const installed = run(home, flags);
  if (installed.status !== 0) throw new Error(`fixture install failed: ${installed.stderr}`);
  addUnrelated(home);
  fs.rmSync(paths(home).receipt);
  build(home);
  return home;
}
const noStrayHome = (result, home) => !(result.stdout + result.stderr).includes(home);

// ---- reviewed topologies: preview -> approval -> apply -> idempotence -> OS-visible health ----
const EXPECTED = {
  "legacy-two": { topology: "legacy", clients: ["claude", "codex"] },
  "prior-two": { topology: "r774", clients: ["claude", "codex"] },
  "current-damaged": { topology: "current", clients: ["claude", "codex"] },
  "legacy-claude": { topology: "legacy", clients: ["claude"] },
  "recognized-mixed": { topology: "recognized-mixed", clients: ["claude", "codex"] },
};
for (const [name, want] of Object.entries(EXPECTED)) {
  const flags = TOPOLOGIES[name].flags;
  const home = receiptFreeHome(name);
  const before = snapshot(home);
  const preview = run(home, ["--migration-preview", "--json", ...flags]);
  const proposal = json(preview);
  check(`${name}: read-only preview proposes an eligible migration`, preview.status === 0 && proposal?.eligibility === "eligible-migration"
    && proposal.topology === want.topology && JSON.stringify(proposal.topologyClients) === JSON.stringify(want.clients)
    && proposal.writesAttempted === false && proposal.verified === false && proposal.failureClass === "NONE", preview.stdout);
  check(`${name}: preview names a separate approval and is not healthy`, proposal?.approvalClass === "separate-human-migration-approval"
    && proposal.nextSafeAction.action === "seek-separate-approval" && proposal.nextSafeAction.approvalRequired === true
    && proposal.stages.find((stage) => stage.id === "COMMIT_FILES").status === "NOT_RUN");
  check(`${name}: preview wrote nothing and leaked no path`, snapshot(home) === before && noStrayHome(preview, home));
  const readOnly = run(home, ["--check", "--json", ...flags]);
  check(`${name}: read-only check is not healthy before migration`, readOnly.status !== 0 && snapshot(home) === before);

  // rollback: a late registration fault restores every byte, mode and the absent receipt
  const fault = run(home, ["--diagnostic-json", ...flags], { AIBL_GUARD_TEST_HOME: home, AIBL_GUARD_TEST_FAIL_STAGE: "REGISTER_HOOKS" });
  check(`${name}: injected late fault restores exact prior files, settings, modes and receipt state`,
    fault.status !== 0 && json(fault)?.rollback === "RESTORED" && snapshot(home) === before, fault.stdout);
  // honest recovery failure: when restoration itself fails the report says so and asks for manual recovery
  const unrecoverable = run(home, ["--diagnostic-json", ...flags], {
    AIBL_GUARD_TEST_HOME: home, AIBL_GUARD_TEST_FAIL_STAGE: "REGISTER_HOOKS", AIBL_GUARD_TEST_FAIL_ROLLBACK: "1" });
  const failedReport = json(unrecoverable);
  check(`${name}: a failed rollback is reported as FAILED with manual recovery`, unrecoverable.status !== 0
    && failedReport?.rollback === "FAILED" && failedReport.nextSafeAction.action === "manual-recovery", unrecoverable.stdout);
  fs.rmSync(home, { recursive: true, force: true });

  const approved = receiptFreeHome(name);
  const beforeApply = snapshot(approved);
  const concurrent = run(approved, ["--diagnostic-json", ...flags], { AIBL_GUARD_TEST_HOME: approved, AIBL_GUARD_TEST_CONCURRENT_CHANGE: "1" });
  const concurrentReport = json(concurrent);
  check(`${name}: concurrent mutation holds before any installer write with a preview-first remedy`, concurrent.status !== 0
    && concurrentReport?.failureClass === "CONCURRENT_CHANGE" && concurrentReport.writesAttempted === false
    && concurrentReport.nextSafeAction.action === "rerun-migration-preview" && concurrentReport.nextSafeAction.approvalRequired === false);
  // the seam only appended a newline to settings; put the home back to its exact earlier bytes
  fs.writeFileSync(paths(approved).settings, fs.readFileSync(paths(approved).settings, "utf8").replace(/\n\n$/, "\n"));
  check(`${name}: nothing but the simulated settings edit changed`, snapshot(approved) === beforeApply);

  const applied = run(approved, flags);
  check(`${name}: approved application succeeds`, applied.status === 0, applied.stderr || applied.stdout);
  const after = json(run(approved, ["--check", "--json", ...flags]));
  check(`${name}: installer inspection is healthy and installer-managed`, after?.ownership?.status === "installer-managed"
    && after.onDisk.status === "healthy" && after.failureClass === "NONE");
  check(`${name}: receipt committed only after verification, mode 0600`, fs.existsSync(paths(approved).receipt)
    && (fs.statSync(paths(approved).receipt).mode & 0o777) === 0o600);
  check(`${name}: unrelated settings, hooks, permissions and project configuration survive`, unrelatedPreserved(approved));
  const matcher = JSON.parse(fs.readFileSync(paths(approved).settings, "utf8")).hooks?.PreToolUse
    ?.find((group) => group.hooks?.some((hook) => hook.command?.includes("secrets-guard.js")))?.matcher ?? "";
  check(`${name}: registration now carries the Read matcher`, /\|Read\|/.test(matcher));
  const settled = snapshot(approved);
  const second = run(approved, flags);
  check(`${name}: second application is idempotent and writes nothing`, second.status === 0 && /already current/.test(second.stdout) && snapshot(approved) === settled);
  fs.rmSync(approved, { recursive: true, force: true });
}

// ---- holds: the preview and the application report one cause, stage and next action ----------
function agree(label, home, flags, want) {
  const before = snapshot(home);
  const preview = json(run(home, ["--migration-preview", "--json", ...flags]));
  const applyRun = run(home, ["--diagnostic-json", ...flags]);
  const apply = json(applyRun);
  const fields = (report) => JSON.stringify([report?.failureClass, report?.firstFailedStage, report?.lastGoodStage,
    (report?.stages || []).filter((stage) => stage.status === "NOT_RUN").map((stage) => stage.id),
    report?.nextSafeAction]);
  check(`${label}: preview holds with ${want.failureClass}`, preview?.eligibility === "hold" && preview.failureClass === want.failureClass, JSON.stringify(preview));
  check(`${label}: application reports the same class, stages, downstream NOT_RUN and next action`, fields(preview) === fields(apply),
    `${fields(preview)}\n${fields(apply)}`);
  check(`${label}: first failed stage is ${want.firstFailedStage}, next action ${want.action}`, preview?.firstFailedStage === want.firstFailedStage
    && preview?.nextSafeAction?.action === want.action);
  check(`${label}: no approval or retry is offered for an unidentified or blocked installation`, preview?.nextSafeAction?.approvalRequired === false
    && apply?.nextSafeAction?.approvalRequired === false && apply?.nextSafeAction?.action !== "review-and-retry");
  check(`${label}: nothing written, downstream execution counters stay at zero, no path leaked`, snapshot(home) === before
    && preview?.writesAttempted === false && apply?.writesAttempted === false && apply?.writesCommitted === false
    && ["COMMIT_FILES", "REGISTER_HOOKS", "POST_VERIFY", "RECEIPT_COMMIT"].every((id) => apply?.stages?.find((stage) => stage.id === id)?.status === "NOT_RUN")
    && noStrayHome({ stdout: JSON.stringify(preview) + JSON.stringify(apply), stderr: "" }, home));
}
{
  const home = receiptFreeHome("recognized-mixed");
  fs.writeFileSync(path.join(paths(home).codexHooks, "secrets-guard.js"), "unreviewed bytes\n");
  agree("unknown bytes", home, [], { failureClass: "UNKNOWN_MANAGED_BYTES", firstFailedStage: "OWNER_DISCOVERY", action: "review-private-ownership" });
}
{
  const home = receiptFreeHome("recognized-mixed");
  fs.writeFileSync(paths(home).settings, "{malformed settings");
  agree("malformed settings", home, [], { failureClass: "SETTINGS_INVALID", firstFailedStage: "OWNER_DISCOVERY", action: "review-private-settings" });
}
{
  const home = receiptFreeHome("recognized-mixed");
  fs.writeFileSync(paths(home).receipt, JSON.stringify({ schemaVersion: 1, owner: "aibl-installer", clients: ["claude", "codex"],
    manifest: { ref: "forged", identity: "0".repeat(64) }, managedFiles: {}, source: { location: "x" } }));
  agree("forged receipt", home, [], { failureClass: "OWNERSHIP_INVALID", firstFailedStage: "OWNER_BINDING", action: "review-installer-receipt" });
}
{
  const home = receiptFreeHome("recognized-mixed");
  agree("recognized mix with one client selected", home, ["--claude"], { failureClass: "CLIENT_SELECTION_INCOMPLETE", firstFailedStage: "OWNER_BINDING", action: "rerun-with-required-clients" });
}
{
  const home = receiptFreeHome("legacy-two");
  agree("reviewed two-client legacy with one client selected", home, ["--codex"], { failureClass: "CLIENT_SELECTION_INCOMPLETE", firstFailedStage: "OWNER_BINDING", action: "rerun-with-required-clients" });
}
{
  const home = receiptFreeHome("recognized-mixed");
  const p = paths(home);
  fs.renameSync(p.claudeHooks, `${p.claudeHooks}-real`);
  fs.symlinkSync(`${p.claudeHooks}-real`, p.claudeHooks);
  agree("symlinked managed directory", home, [], { failureClass: "UNSAFE_TARGET", firstFailedStage: "INPUT_SCOPE", action: "review-private-ownership" });
}
{
  // individually reviewed files that are not a reviewed combination are never attributed
  const home = receiptFreeHome("legacy-two");
  put(path.join(paths(home).claudeHooks, "secrets-guard.js"), current("secrets-guard.js"));
  agree("known hashes in an unreviewed combination (current Claude guard, legacy rest)", home, [], { failureClass: "MIGRATION_TOPOLOGY_UNRECOGNIZED", firstFailedStage: "OWNER_BINDING", action: "escalate-unreviewed-topology" });
}
{
  const home = receiptFreeHome("legacy-two");
  put(path.join(paths(home).codexHooks, "secrets-guard.js"), current("secrets-guard.js"));
  agree("current Codex guard beside a legacy Claude installation", home, [], { failureClass: "MIGRATION_TOPOLOGY_UNRECOGNIZED", firstFailedStage: "OWNER_BINDING", action: "escalate-unreviewed-topology" });
}
{
  const home = receiptFreeHome("legacy-claude");
  fs.rmSync(path.join(paths(home).claudeHooks, "secrets-tripwire.js"));
  agree("partial legacy installation (tripwire missing)", home, ["--claude"], { failureClass: "MIGRATION_TOPOLOGY_UNRECOGNIZED", firstFailedStage: "OWNER_BINDING", action: "escalate-unreviewed-topology" });
}
{
  // an unselected client's unrecognized files are preserved and never block
  const home = newHome();
  fs.mkdirSync(path.join(home, ".codex", "hooks"), { recursive: true });
  fs.writeFileSync(path.join(home, ".codex", "hooks", "secrets-guard.js"), "unrelated synthetic Codex bytes\n");
  const claudeOnly = run(home, ["--claude"]);
  check("Claude-only install preserves an unselected client's unrecognized files", claudeOnly.status === 0
    && fs.readFileSync(path.join(home, ".codex", "hooks", "secrets-guard.js"), "utf8") === "unrelated synthetic Codex bytes\n");
}
{
  // a source-integrity failure is the same hold in the preview and in the application
  const home = receiptFreeHome("recognized-mixed");
  const hooksCopy = path.join(root, "tampered-source");
  fs.mkdirSync(hooksCopy);
  fs.cpSync(HOOKS, path.join(hooksCopy, "hooks"), { recursive: true });
  fs.appendFileSync(path.join(hooksCopy, "hooks", "secrets-guard.legacy.identities.json"), " ");
  const tampered = path.join(hooksCopy, "hooks", "refresh-guard.mjs");
  const go = (flags) => spawnSync(process.execPath, [tampered, ...flags], { env: { ...process.env, HOME: home, USERPROFILE: home }, encoding: "utf8" });
  const before = snapshot(home);
  const preview = json(go(["--migration-preview", "--json"]));
  const apply = json(go(["--diagnostic-json"]));
  check("source integrity: preview and application agree on class, stage and next action",
    preview?.failureClass === "SOURCE_INTEGRITY" && apply?.failureClass === "SOURCE_INTEGRITY"
    && preview.firstFailedStage === "SOURCE_VERIFY" && apply.firstFailedStage === "SOURCE_VERIFY"
    && JSON.stringify(preview.nextSafeAction) === JSON.stringify(apply.nextSafeAction) && snapshot(home) === before);
}

try { fs.rmSync(root, { recursive: true, force: true }); } catch { /* best effort */ }
console.log(`\n${checks - failures.length}/${checks} history checks passed`);
process.exit(failures.length ? 1 : 0);
