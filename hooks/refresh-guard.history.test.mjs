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

// Course-deployed prior states (agent-native-os, before 09-11-2026). The fixtures are the exact bytes
// that repository's refresher installed for secrets-guard-2026-09-02 (agent-native-os #108, f3231373).
const course = JSON.parse(fs.readFileSync(path.join(HOOKS, "secrets-guard.course-deployed.identities.json"), "utf8"));
const courseState = course.states.find((state) => state.agentNativeOsCommit === "f323137327a788bfe639c94052445f6a6ffe4e32");
check("course-deployed fixture secrets-guard.js is the agent-native-os #108 release", sha(fx("anos-2026-09-02", "secrets-guard.js")) === courseState?.files["secrets-guard.js"]);
check("course-deployed fixture codex-secrets-guard.mjs is the agent-native-os #108 adapter",
  sha(fx("anos-2026-09-02", "codex-secrets-guard.mjs")) === courseState?.local_files["codex-secrets-guard.mjs"]);
check("every course-deployed state names its source commit and shares the legacy tripwire and installer",
  course.states.length > 0 && course.states.every((state) => /^[0-9a-f]{40}$/.test(state.agentNativeOsCommit)
    && /^[0-9a-f]{40}$/.test(state.workshopInstallerTagCommit) && state.ref !== legacy.ref
    && state.files["secrets-tripwire.js"] === legacy.files["secrets-tripwire.js"] && state.files["install.mjs"] === legacy.files["install.mjs"]));

// The two field reports of 10-18-2026, by the SHA-256 each learner posted (no file contents).
// Learner B (Windows 11): every managed file is the agent-native-os secrets-guard-2026-09-02 state.
const LEARNER_B = {
  "secrets-guard.js": "126577de637de687fe58f7fcdc740fc1d0eae7fc3b5e087948692f9eaf1da568",
  "codex-secrets-guard.mjs": "2161dc1eee905fe5dd05b84415fa43967326dafa50a17d2aac2a7823f4b3acc1",
  "secrets-tripwire.js": "8db9436d1230b2b84f06416f84be4d44557454d87dca38fac2fc795f61a658e7",
  "install.mjs": "a28b70a42ee286cae0e916d62a24b4bf6ea7d3e3bc5cd593caada2c6eea40060",
  "codex-secrets-tripwire.mjs": "4816fb7233bf89195babdb00d42ba40006d67acb142383b23638c8aaa065de21",
  "aws-credential-patterns.mjs": "ab56ba1d82f0ac367dfe5542d378490833e540c55baff0f84cb413bae4422699",
  "aws-credential-guard.mjs": "1783032b3246d8323a77738bcc9c9789d2fd49ff59737971df17b294800c5409",
  "aws-credential-tripwire.mjs": "1bea3ccd1c113a1b2846f2d14ecaabe3d79a5bc833f46c37382b445f8bebe657",
};
check("learner B's posted hashes are exactly one agent-native-os state (#108)", Object.entries(LEARNER_B).every(([name, hash]) =>
  (courseState?.files[name] || courseState?.local_files[name]) === hash));
check("learner B's fixtures carry learner B's posted hashes", sha(fx("anos-2026-09-02", "secrets-guard.js")) === LEARNER_B["secrets-guard.js"]
  && sha(fx("anos-2026-09-02", "codex-secrets-guard.mjs")) === LEARNER_B["codex-secrets-guard.mjs"]);
// Learner A (macOS): the pinned legacy release on both clients, except one Codex adapter whose bytes no
// aibuild-lab repository ever contained (every ref and pull request searched 10-18-2026). It stays held.
const LEARNER_A_KNOWN = {
  "secrets-guard.js": "a1f5a937e231282225c88761e6312dd681abdf778e1aa7fd85985bc629efd1c4",
  "secrets-tripwire.js": "8db9436d1230b2b84f06416f84be4d44557454d87dca38fac2fc795f61a658e7",
  "codex-secrets-guard.mjs": "dcabd5c1ad5aa658b85a23234adcd48e2981fe7921e8db0dbec512391dfb6b64",
  "aws-credential-patterns.mjs": "ab56ba1d82f0ac367dfe5542d378490833e540c55baff0f84cb413bae4422699",
};
const LEARNER_A_UNPROVEN_TRIPWIRE = "1570edab2887cc4794f11ff630cbd373c90326dbf3b063e6b74128701010bf51";
check("learner A's other posted hashes are the pinned legacy release", Object.entries(LEARNER_A_KNOWN).every(([name, hash]) =>
  (legacy.files[name] || legacy.local_files[name]) === hash) && sha(fx("legacy", "secrets-guard.js")) === LEARNER_A_KNOWN["secrets-guard.js"]);
// Workshop-installer states (Camp and workshop alumni, 10-30-2026). aibuild-lab/workshop-installer's
// setup put its main branch's three hook files into ~/.claude/hooks. The fixtures are those exact git
// blobs, one folder per record, named by the workshop-installer commit that put them on main.
const workshop = JSON.parse(fs.readFileSync(path.join(HOOKS, "secrets-guard.workshop-installer.identities.json"), "utf8"));
const WORKSHOP_COMMITS = ["00eadf9", "86f9cbc", "d8fdc6b", "9ab6044", "f506b52", "64130d9"];
const workshopState = (short) => workshop.states.find((state) => state.workshopInstallerCommit.startsWith(short));
check("the workshop-installer record holds exactly the six workshop states no other record names",
  JSON.stringify(workshop.states.map((state) => state.workshopInstallerCommit.slice(0, 7))) === JSON.stringify(WORKSHOP_COMMITS));
for (const short of WORKSHOP_COMMITS) {
  const state = workshopState(short);
  check(`workshop ${short}: record names its full source commit and its own ref`, /^[0-9a-f]{40}$/.test(state?.workshopInstallerCommit || "")
    && state.ref === `workshop-installer-${short}` && Object.keys(state.local_files).length === 0);
  for (const name of ["secrets-guard.js", "secrets-tripwire.js", "install.mjs"])
    check(`workshop ${short}: fixture ${name} is the recorded hash`, sha(fx(`workshop-${short}`, name)) === state?.files[name]);
}
const knownTriples = [legacy, prior, ...course.states].map((source) => JSON.stringify(source.files));
check("no workshop record repeats a state an earlier record already names",
  workshop.states.every((state) => !knownTriples.includes(JSON.stringify(state.files)) && state.ref !== legacy.ref
    && !course.states.some((other) => other.ref === state.ref)));
check("QA's 10-30 finding: the workshop 64130d9 guard is the sha256 QA reported (02fbc66d...)",
  workshopState("64130d9")?.files["secrets-guard.js"].startsWith("02fbc66d"));

const pinnedEverywhere = JSON.stringify([prior, legacy, course, workshop,
  JSON.parse(fs.readFileSync(path.join(HOOKS, "secrets-guard.manifest.json"), "utf8"))]);
check("learner A's unproven Codex tripwire hash is pinned by no identity", !pinnedEverywhere.includes(LEARNER_A_UNPROVEN_TRIPWIRE));

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
  // learner B (10-18-2026): both clients exactly as agent-native-os #108 installed them
  "course-deployed-two": { flags: [], build(home) {
    const p = paths(home);
    put(path.join(p.claudeHooks, "secrets-guard.js"), fx("anos-2026-09-02", "secrets-guard.js"));
    for (const name of ["secrets-tripwire.js", "install.mjs"]) put(path.join(p.claudeHooks, name), fx("legacy", name));
    put(path.join(p.codexHooks, "secrets-guard.js"), fx("anos-2026-09-02", "secrets-guard.js"));
    put(path.join(p.codexHooks, "secrets-tripwire.js"), fx("legacy", "secrets-tripwire.js"));
    put(path.join(p.codexHooks, "codex-secrets-guard.mjs"), fx("anos-2026-09-02", "codex-secrets-guard.mjs"));
    useOldMatcher(home);
  } },
  // the same release on a Claude-only machine
  "course-deployed-claude": { flags: ["--claude"], build(home) {
    const p = paths(home);
    put(path.join(p.claudeHooks, "secrets-guard.js"), fx("anos-2026-09-02", "secrets-guard.js"));
    for (const name of ["secrets-tripwire.js", "install.mjs"]) put(path.join(p.claudeHooks, name), fx("legacy", name));
    useOldMatcher(home);
  } },
};
// Camp and workshop alumni: built the way the workshop installer's setup did it, on a home this
// installer never touched. The three files of one workshop state go into ~/.claude/hooks and that
// state's own install.mjs registers them (Claude only; the workshop installer never set up Codex).
function workshopBuild(short) {
  return (home) => {
    const p = paths(home);
    fs.mkdirSync(p.claudeHooks, { recursive: true });
    for (const name of ["secrets-guard.js", "secrets-tripwire.js", "install.mjs"]) put(path.join(p.claudeHooks, name), fx(`workshop-${short}`, name));
    const registered = spawnSync(process.execPath, [path.join(p.claudeHooks, "install.mjs")], {
      env: { ...process.env, HOME: home, USERPROFILE: home }, encoding: "utf8" });
    if (registered.status !== 0) throw new Error(`workshop ${short} install failed: ${registered.stderr}`);
  };
}
for (const short of WORKSHOP_COMMITS)
  TOPOLOGIES[`workshop-${short}-claude`] = { flags: ["--claude"], fresh: true, build: workshopBuild(short) };
function receiptFreeHome(name) {
  const home = newHome();
  const { flags, build, fresh } = TOPOLOGIES[name];
  if (fresh) {
    build(home);
    addUnrelated(home);
    return home;
  }
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
  "course-deployed-two": { topology: "course-deployed", clients: ["claude", "codex"], priorRef: "secrets-guard-2026-09-02" },
  "course-deployed-claude": { topology: "course-deployed", clients: ["claude"], priorRef: "secrets-guard-2026-09-02" },
};
for (const short of WORKSHOP_COMMITS)
  EXPECTED[`workshop-${short}-claude`] = { topology: "course-deployed", clients: ["claude"], priorRef: `workshop-installer-${short}`,
    workshopCommit: workshopState(short)?.workshopInstallerCommit, workshopPullRequest: workshopState(short)?.workshopInstallerPullRequest };
const priorStateMatches = (want, priorState) => want.workshopCommit
  ? priorState?.ref === want.priorRef && priorState.sourceRepository === "aibuild-lab/workshop-installer"
    && JSON.stringify(priorState.workshopInstallerCommits) === JSON.stringify([want.workshopCommit])
    && JSON.stringify(priorState.workshopInstallerPullRequests) === JSON.stringify([want.workshopPullRequest])
    && priorState.agentNativeOsCommits === undefined
  : priorState?.ref === want.priorRef && priorState.sourceRepository === "aibuild-lab/agent-native-os"
    && priorState.agentNativeOsCommits.includes("f323137327a788bfe639c94052445f6a6ffe4e32")
    && priorState.agentNativeOsPullRequests.includes(108);
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
  check(`${name}: preview names the attributed prior state only for a course-deployed installation`, want.priorRef
    ? priorStateMatches(want, proposal?.priorState)
    : proposal?.priorState === undefined, JSON.stringify(proposal?.priorState));
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
  // The field canary from learner A, against the migrated guard: Claude's built-in Read of a synthetic,
  // content-free .env outside any project. The hook classifies by path metadata and never opens it.
  const outside = path.join(approved, "outside-project");
  fs.mkdirSync(outside, { recursive: true });
  fs.writeFileSync(path.join(outside, ".env"), "");
  const readCanary = spawnSync(process.execPath, [path.join(paths(approved).claudeHooks, "secrets-guard.js")], {
    input: JSON.stringify({ tool_name: "Read", tool_input: { file_path: path.join(outside, ".env") } }), encoding: "utf8", cwd: outside });
  check(`${name}: migrated guard denies a built-in Read of a .env outside the project`, readCanary.status === 0
    && /"permissionDecision":"deny"/.test(readCanary.stdout), readCanary.stdout + readCanary.stderr);
  fs.rmSync(outside, { recursive: true, force: true });
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
  // learner A: the legacy release on both clients with a Codex tripwire adapter no reviewed source contains
  const home = receiptFreeHome("legacy-two");
  const unproven = Buffer.concat([current("codex-secrets-tripwire.mjs"), Buffer.from("// locally changed adapter\n")]);
  check("learner A stand-in tripwire is pinned by no identity", !pinnedEverywhere.includes(sha(unproven)));
  put(path.join(paths(home).codexHooks, "codex-secrets-tripwire.mjs"), unproven);
  agree("learner A: legacy release with an unproven Codex tripwire", home, [], { failureClass: "UNKNOWN_MANAGED_BYTES", firstFailedStage: "OWNER_DISCOVERY", action: "review-private-ownership" });
  agree("learner A: the same installation with Claude alone selected", home, ["--claude"], { failureClass: "CLIENT_SELECTION_INCOMPLETE", firstFailedStage: "OWNER_BINDING", action: "rerun-with-required-clients" });
}
{
  // a course-deployed guard with one byte changed is not that release
  const home = receiptFreeHome("course-deployed-two");
  const edited = Buffer.from(fx("anos-2026-09-02", "secrets-guard.js"));
  edited[edited.length - 2] ^= 0x20;
  put(path.join(paths(home).claudeHooks, "secrets-guard.js"), edited);
  agree("course-deployed guard with one changed byte", home, [], { failureClass: "UNKNOWN_MANAGED_BYTES", firstFailedStage: "OWNER_DISCOVERY", action: "review-private-ownership" });
}
{
  // two individually proven releases on two clients are not a reviewed combination
  const home = receiptFreeHome("course-deployed-two");
  for (const name of ["secrets-guard.js", "secrets-tripwire.js"]) put(path.join(paths(home).codexHooks, name), fx("legacy", name));
  put(path.join(paths(home).codexHooks, "codex-secrets-guard.mjs"), current("codex-secrets-guard.mjs"));
  agree("course-deployed Claude beside a legacy Codex installation", home, [], { failureClass: "MIGRATION_TOPOLOGY_UNRECOGNIZED", firstFailedStage: "OWNER_BINDING", action: "escalate-unreviewed-topology" });
}
{
  // a course-deployed adapter attributes nothing beside another release's guard
  const home = receiptFreeHome("legacy-two");
  put(path.join(paths(home).codexHooks, "codex-secrets-guard.mjs"), fx("anos-2026-09-02", "codex-secrets-guard.mjs"));
  agree("course-deployed Codex adapter beside a legacy guard", home, [], { failureClass: "MIGRATION_TOPOLOGY_UNRECOGNIZED", firstFailedStage: "OWNER_BINDING", action: "escalate-unreviewed-topology" });
}
{
  // and a course-deployed guard needs its own release's adapter, not the current one
  const home = receiptFreeHome("course-deployed-two");
  put(path.join(paths(home).codexHooks, "codex-secrets-guard.mjs"), current("codex-secrets-guard.mjs"));
  agree("course-deployed guard beside the current Codex adapter", home, [], { failureClass: "MIGRATION_TOPOLOGY_UNRECOGNIZED", firstFailedStage: "OWNER_BINDING", action: "escalate-unreviewed-topology" });
}
{
  const home = receiptFreeHome("course-deployed-two");
  agree("course-deployed two-client installation with one client selected", home, ["--codex"], { failureClass: "CLIENT_SELECTION_INCOMPLETE", firstFailedStage: "OWNER_BINDING", action: "rerun-with-required-clients" });
}
{
  // the course-deployed record is pinned by refresh-guard.mjs; any change to it is a source-integrity hold
  const home = receiptFreeHome("course-deployed-two");
  const hooksCopy = path.join(root, "tampered-course-source");
  fs.mkdirSync(hooksCopy);
  fs.cpSync(HOOKS, path.join(hooksCopy, "hooks"), { recursive: true });
  fs.appendFileSync(path.join(hooksCopy, "hooks", "secrets-guard.course-deployed.identities.json"), " ");
  const tampered = path.join(hooksCopy, "hooks", "refresh-guard.mjs");
  const go = (flags) => spawnSync(process.execPath, [tampered, ...flags], { env: { ...process.env, HOME: home, USERPROFILE: home }, encoding: "utf8" });
  const before = snapshot(home);
  const preview = json(go(["--migration-preview", "--json"]));
  const apply = json(go(["--diagnostic-json"]));
  check("tampered course-deployed record: preview and application hold with SOURCE_INTEGRITY and write nothing",
    preview?.failureClass === "SOURCE_INTEGRITY" && apply?.failureClass === "SOURCE_INTEGRITY"
    && preview.eligibility !== "eligible-migration" && snapshot(home) === before, JSON.stringify(preview));
}
{
  // the workshop 64130d9 guard with one changed byte is not that release: it still holds
  const home = receiptFreeHome("workshop-64130d9-claude");
  const edited = Buffer.from(fx("workshop-64130d9", "secrets-guard.js"));
  edited[edited.length - 2] ^= 0x20;
  put(path.join(paths(home).claudeHooks, "secrets-guard.js"), edited);
  agree("workshop 64130d9 guard with one changed byte", home, ["--claude"], { failureClass: "UNKNOWN_MANAGED_BYTES", firstFailedStage: "OWNER_DISCOVERY", action: "review-private-ownership" });
}
{
  // and so does a copy with an extra line added at the end
  const home = receiptFreeHome("workshop-64130d9-claude");
  put(path.join(paths(home).claudeHooks, "secrets-guard.js"),
    Buffer.concat([fx("workshop-64130d9", "secrets-guard.js"), Buffer.from("// edited locally\n")]));
  agree("workshop 64130d9 guard with a line added", home, ["--claude"], { failureClass: "UNKNOWN_MANAGED_BYTES", firstFailedStage: "OWNER_DISCOVERY", action: "review-private-ownership" });
}
{
  // individually known workshop files from two different states are not one release
  const home = receiptFreeHome("workshop-64130d9-claude");
  for (const name of ["secrets-tripwire.js", "install.mjs"]) put(path.join(paths(home).claudeHooks, name), fx("workshop-9ab6044", name));
  agree("workshop 64130d9 guard beside the June workshop tripwire and installer", home, ["--claude"], { failureClass: "MIGRATION_TOPOLOGY_UNRECOGNIZED", firstFailedStage: "OWNER_BINDING", action: "escalate-unreviewed-topology" });
}
{
  // a workshop state attributes no adapter: an AWS supplement beside it is not a reviewed combination
  const home = receiptFreeHome("workshop-64130d9-claude");
  put(path.join(paths(home).claudeHooks, "aws-credential-guard.mjs"), current("aws-credential-guard.mjs"));
  agree("workshop 64130d9 guard beside an AWS supplement", home, ["--claude"], { failureClass: "MIGRATION_TOPOLOGY_UNRECOGNIZED", firstFailedStage: "OWNER_BINDING", action: "escalate-unreviewed-topology" });
}
{
  // a Claude-only workshop installation, previewed from Codex, asks to include Claude like any reviewed release
  const home = receiptFreeHome("workshop-64130d9-claude");
  agree("workshop 64130d9 Claude installation with only Codex selected", home, ["--codex"], { failureClass: "CLIENT_SELECTION_INCOMPLETE", firstFailedStage: "OWNER_BINDING", action: "rerun-with-required-clients" });
}
{
  // the workshop-installer record is pinned by refresh-guard.mjs; any change to it is a source-integrity hold
  const home = receiptFreeHome("workshop-64130d9-claude");
  const hooksCopy = path.join(root, "tampered-workshop-source");
  fs.mkdirSync(hooksCopy);
  fs.cpSync(HOOKS, path.join(hooksCopy, "hooks"), { recursive: true });
  fs.appendFileSync(path.join(hooksCopy, "hooks", "secrets-guard.workshop-installer.identities.json"), " ");
  const tampered = path.join(hooksCopy, "hooks", "refresh-guard.mjs");
  const go = (flags) => spawnSync(process.execPath, [tampered, ...flags], { env: { ...process.env, HOME: home, USERPROFILE: home }, encoding: "utf8" });
  const before = snapshot(home);
  const preview = json(go(["--migration-preview", "--json", "--claude"]));
  const apply = json(go(["--diagnostic-json", "--claude"]));
  check("tampered workshop-installer record: preview and application hold with SOURCE_INTEGRITY and write nothing",
    preview?.failureClass === "SOURCE_INTEGRITY" && apply?.failureClass === "SOURCE_INTEGRITY"
    && preview.eligibility !== "eligible-migration" && snapshot(home) === before, JSON.stringify(preview));
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

{
  // A failure with no typed cause is reported honestly by stage: before any approval or effect it is an
  // unidentified installation (reviewed, never "approve and retry"); after approval a retry needs approval.
  const home = receiptFreeHome("recognized-mixed");
  const early = json(run(home, ["--diagnostic-json"], { AIBL_GUARD_TEST_HOME: home, AIBL_GUARD_TEST_FAIL_STAGE: "OWNER_DISCOVERY" }));
  check("an untyped failure before approval names private review, not approve-and-retry", early?.firstFailedStage === "OWNER_DISCOVERY"
    && early.nextSafeAction.action === "review-private-ownership" && early.nextSafeAction.approvalRequired === false, JSON.stringify(early?.nextSafeAction));
  const late = json(run(home, ["--diagnostic-json"], { AIBL_GUARD_TEST_HOME: home, AIBL_GUARD_TEST_FAIL_STAGE: "REGISTER_HOOKS" }));
  check("a failure after approval keeps review-and-retry with approval and a restored rollback", late?.firstFailedStage === "REGISTER_HOOKS"
    && late.nextSafeAction.action === "review-and-retry" && late.nextSafeAction.approvalRequired === true && late.rollback === "RESTORED");
}

try { fs.rmSync(root, { recursive: true, force: true }); } catch { /* best effort */ }
console.log(`\n${checks - failures.length}/${checks} history checks passed`);
process.exit(failures.length ? 1 : 0);
