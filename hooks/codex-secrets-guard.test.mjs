#!/usr/bin/env node
// Hermetic Codex protocol checks for the reviewed adapters. Uses the actual vendored
// canonical PreToolUse guard and a deterministic tripwire stub; no real secrets or HOME writes.

import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptsDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptsDir, "..");
const root = fs.mkdtempSync(path.join(os.tmpdir(), "codex-secrets-guard-"));
const hooksDir = path.join(root, "hooks");
fs.mkdirSync(hooksDir, { recursive: true });

const manifest = JSON.parse(fs.readFileSync(path.join(scriptsDir, "secrets-guard.manifest.json"), "utf8"));
const localFiles = [
  "aws-credential-patterns.mjs", "aws-credential-guard.mjs", "aws-credential-tripwire.mjs",
  "codex-secrets-guard.mjs", "codex-secrets-tripwire.mjs",
];
// The trust manifest pins LF-normalized content; a CRLF checkout (Git for Windows
// core.autocrlf=true) must hash to the same reviewed values. Pure CRLF -> LF only, matching
// the guard: a bare trailing CR must still change the hash.
const normalizeLf = (buf) => Buffer.from(buf.toString("utf8").replaceAll("\r\n", "\n"), "utf8");
for (const file of localFiles) {
  const actual = crypto.createHash("sha256").update(normalizeLf(fs.readFileSync(path.join(scriptsDir, file)))).digest("hex");
  assert.equal(actual, manifest.local_files?.[file], `${file} must match its reviewed manifest hash`);
}

for (const file of ["aws-credential-patterns.mjs", "codex-secrets-guard.mjs", "codex-secrets-tripwire.mjs"]) {
  fs.copyFileSync(path.join(scriptsDir, file), path.join(hooksDir, file));
}
fs.copyFileSync(
  path.join(scriptsDir, "secrets-guard.js"),
  path.join(hooksDir, "secrets-guard.js"),
);

const run = (script, input) => spawnSync(process.execPath, [path.join(hooksDir, script)], {
  input: JSON.stringify(input),
  encoding: "utf8",
  env: { ...process.env, CODEX_GUARD_HOOKS_DIR: hooksDir, HOME: root, USERPROFILE: root },
});
const decision = (result) => result.stdout
  ? JSON.parse(result.stdout).hookSpecificOutput?.permissionDecision ?? "allow"
  : "allow";
const denialReason = (result) => JSON.parse(result.stdout).hookSpecificOutput?.permissionDecisionReason ?? "";

const safeIdentity = run("codex-secrets-guard.mjs", {
  hook_event_name: "PreToolUse",
  tool_name: "Bash",
  tool_input: { command: "infisical run -- aws sts get-caller-identity" },
});
assert.equal(safeIdentity.status, 0);
assert.equal(decision(safeIdentity), "allow");

const envRead = run("codex-secrets-guard.mjs", {
  hook_event_name: "PreToolUse",
  tool_name: "Bash",
  tool_input: { command: "cat .env" },
});
assert.equal(decision(envRead), "deny");

const dockerConfigRead = run("codex-secrets-guard.mjs", {
  hook_event_name: "PreToolUse",
  tool_name: "Bash",
  tool_input: { command: "docker image inspect --format '{{json .Config.Env}}' example.invalid/image" },
});
assert.equal(decision(dockerConfigRead), "deny");
assert.equal(
  denialReason(dockerConfigRead),
  "Docker inspect may read only the reviewed non-secret metadata fields. Use one --format selector for those fields. [Codex secrets-guard adapter]",
);

const agentProxyPolicyCases = [
  ["infisical secrets agent-proxy run --no-sandbox -- /bin/true", /This guard blocks --no-sandbox flags in Infisical commands\./],
  ["infisical secrets agent-proxy run --token=PASTE_YOUR_TOKEN_HERE -- /bin/true", /Do not place an Infisical token in a command/],
  ["infisical secrets agent-proxy run --pass-env EXA_API_KEY -- /bin/true", /Do not pass credential-shaped host environment variables/],
  ["infisical secrets agent-proxy run --set-env EXA_API_KEY=placeholder -- /bin/true", /Do not set credential-shaped environment variables/],
  ["infisical secrets agent-proxy start", /^Infisical secrets subcommands can print vault values\. Use a reviewed runtime delivery command instead\. \[Codex secrets-guard adapter\]$/],
  ["infisical secrets agent-proxy connect", /^Infisical secrets subcommands can print vault values\. Use a reviewed runtime delivery command instead\. \[Codex secrets-guard adapter\]$/],
];
for (const [command, expectedReason] of agentProxyPolicyCases) {
  const result = run("codex-secrets-guard.mjs", {
    hook_event_name: "PreToolUse",
    tool_name: "Bash",
    tool_input: { command },
  });
  assert.equal(result.status, 0);
  assert.equal(JSON.parse(result.stdout).hookSpecificOutput.hookEventName, "PreToolUse");
  assert.equal(decision(result), "deny");
  assert.match(denialReason(result), expectedReason);
  assert.doesNotMatch(denialReason(result), /Use a placeholder or inject the value at runtime/);
  assert.ok(!result.stdout.includes(command));
}

// Exercise display compatibility using DENY-only child fixtures. Policy checks above and
// below still use the exact vendored canonical guard; no real tool command is executed.
const canonicalPath = path.join(hooksDir, "secrets-guard.js");
const canonicalBytes = fs.readFileSync(canonicalPath);
const genericDenial = "The pinned guard detected a command or write that could expose a secret. Use a placeholder or inject the value at runtime.";
const canonicalMessageCases = [
  ["Infisical agent access must keep its operating-system sandbox enabled.", "This guard blocks --no-sandbox flags in Infisical commands."],
  ["The local Infisical Agent Proxy must keep its OS sandbox enabled.", "This guard blocks --no-sandbox flags in Infisical commands."],
  ["Do not place an Infisical token in a command. Use the named-human login session.", "Do not place an Infisical token in a command. Use the named-human login session."],
  ["Do not place an Infisical token in the Agent Proxy command. Use the named-human login session.", "Do not place an Infisical token in a command. Use the named-human login session."],
  ["`docker inspect` renders the target's full configuration, which includes its environment variables. Read the single setting you need, or pass a --format/--property selector that excludes Env.", "Docker inspect may read only the reviewed non-secret metadata fields. Use one --format selector for those fields."],
  ["Unrecognized denial with PRIVATE_TEST_MARKER", genericDenial],
];
try {
  for (const [canonicalReason, expectedReason] of canonicalMessageCases) {
    const denial = { hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: canonicalReason + "  [secrets-guard hook]",
    } };
    fs.writeFileSync(canonicalPath, "process.stdout.write(" + JSON.stringify(JSON.stringify(denial)) + ");\n");
    const result = run("codex-secrets-guard.mjs", {
      hook_event_name: "PreToolUse", tool_name: "Bash",
      tool_input: { command: "echo guard-compatibility-fixture" },
    });
    assert.equal(result.status, 0);
    assert.equal(JSON.parse(result.stdout).hookSpecificOutput.hookEventName, "PreToolUse");
    assert.equal(decision(result), "deny");
    assert.equal(denialReason(result), expectedReason + " [Codex secrets-guard adapter]");
    assert.ok(!result.stdout.includes("PRIVATE_TEST_MARKER"));
    assert.ok(!result.stdout.includes("guard-compatibility-fixture"));
  }
} finally {
  fs.writeFileSync(canonicalPath, canonicalBytes);
}

const syntheticAwsId = `AKIA${"Q7W8E9R0T1Y2U3I4"}`;
const syntheticAwsTempId = `ASIA${"T7U8V9W0X1Y2Z3Q4"}`;
const syntheticAwsSecret = "aB3dE5fG7hJ9kL2mN4pQ6rS8tU0vW1xY3zA5bC7d".slice(0, 40);
const patchWrite = run("codex-secrets-guard.mjs", {
  hook_event_name: "PreToolUse",
  tool_name: "apply_patch",
  tool_input: { patch: `*** Add File: example.txt\n+${syntheticAwsId}\n` },
});
assert.equal(decision(patchWrite), "deny");
assert.ok(!patchWrite.stdout.includes(syntheticAwsId));

const tempIdBash = run("codex-secrets-guard.mjs", {
  hook_event_name: "PreToolUse",
  tool_name: "Bash",
  tool_input: { command: `AWS_ACCESS_KEY_ID=${syntheticAwsTempId} ./deploy.sh` },
});
assert.equal(decision(tempIdBash), "deny");
assert.ok(!tempIdBash.stdout.includes(syntheticAwsTempId));

const tempIdPatch = run("codex-secrets-guard.mjs", {
  hook_event_name: "PreToolUse",
  tool_name: "apply_patch",
  tool_input: { patch: `*** Add File: example.txt\n+AWS_ACCESS_KEY_ID=${syntheticAwsTempId}\n` },
});
assert.equal(decision(tempIdPatch), "deny");
assert.ok(!tempIdPatch.stdout.includes(syntheticAwsTempId));

const namedAwsSecret = run("codex-secrets-guard.mjs", {
  hook_event_name: "PreToolUse",
  tool_name: "Bash",
  tool_input: { command: `aws configure set aws_secret_access_key ${syntheticAwsSecret}` },
});
assert.equal(decision(namedAwsSecret), "deny");
assert.ok(!namedAwsSecret.stdout.includes(syntheticAwsSecret));

const genericMcpTempId = run("codex-secrets-guard.mjs", {
  hook_event_name: "PreToolUse",
  tool_name: "mcp__example__write_record",
  tool_input: { record: { accessKeyId: syntheticAwsTempId } },
});
assert.equal(decision(genericMcpTempId), "deny");
assert.ok(!genericMcpTempId.stdout.includes(syntheticAwsTempId));

const genericFunctionSecret = run("codex-secrets-guard.mjs", {
  hook_event_name: "PreToolUse",
  tool_name: "custom_local_function",
  tool_input: { arguments: { config: `SecretAccessKey: "${syntheticAwsSecret}"` } },
});
assert.equal(decision(genericFunctionSecret), "deny");
assert.ok(!genericFunctionSecret.stdout.includes(syntheticAwsSecret));

const placeholderPatch = run("codex-secrets-guard.mjs", {
  hook_event_name: "PreToolUse",
  tool_name: "apply_patch",
  tool_input: { patch: "*** Add File: .env.example\n+AWS_ACCESS_KEY_ID=PASTE_YOUR_KEY_HERE\n" },
});
assert.equal(decision(placeholderPatch), "allow");
const placeholderNamedCredential = run("codex-secrets-guard.mjs", {
  hook_event_name: "PreToolUse",
  tool_name: "Bash",
  tool_input: { command: "AWS_SECRET_ACCESS_KEY=PASTE_YOUR_AWS_SECRET_ACCESS_KEY_HERE ./deploy.sh" },
});
assert.equal(decision(placeholderNamedCredential), "allow");
const safeGenericReferences = run("codex-secrets-guard.mjs", {
  hook_event_name: "PreToolUse",
  tool_name: "mcp__example__write_record",
  tool_input: {
    placeholder: "AWS_SECRET_ACCESS_KEY=PASTE_YOUR_AWS_SECRET_ACCESS_KEY_HERE",
    runtimeReference: "AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN}",
  },
});
assert.equal(decision(safeGenericReferences), "allow");

const tripwirePath = path.join(hooksDir, "secrets-tripwire.js");
const syntheticOpenAi = `sk-proj-${"Z9y8X7w6V5u4T3s2R1q0"}`;
fs.writeFileSync(tripwirePath, [
  "#!/usr/bin/env node",
  "const fs = require('fs');",
  "const input = JSON.parse(fs.readFileSync(0, 'utf8'));",
  "if (!input.tool_response?.hit) process.exit(0);",
  `const value = ${JSON.stringify(syntheticOpenAi)};`,
  "process.stdout.write(JSON.stringify({ hookSpecificOutput: {",
  "  hookEventName: 'PostToolUse',",
  "  additionalContext: 'SECRET TRIPWIRE: OpenAI-style key detected.',",
  "  updatedToolOutput: { stdout: value },",
  "} }));",
].join("\n"));

const postHit = run("codex-secrets-tripwire.mjs", {
  hook_event_name: "PostToolUse",
  tool_name: "Bash",
  tool_response: { hit: true, stdout: syntheticOpenAi },
});
assert.equal(postHit.status, 0);
const postOutput = JSON.parse(postHit.stdout);
assert.deepEqual(Object.keys(postOutput).sort(), ["continue", "stopReason", "systemMessage"]);
assert.equal(postOutput.continue, false);
assert.match(postOutput.systemMessage, /OpenAI-style key/);
assert.ok(!postHit.stdout.includes(syntheticOpenAi));
assert.ok(!postHit.stdout.includes("updatedToolOutput"));

const postMcpHit = run("codex-secrets-tripwire.mjs", {
  hook_event_name: "PostToolUse",
  tool_name: "mcp__example__read_record",
  tool_response: { hit: true, content: [{ type: "text", text: syntheticOpenAi }] },
});
assert.equal(postMcpHit.status, 0);
assert.equal(JSON.parse(postMcpHit.stdout).continue, false);
assert.match(JSON.parse(postMcpHit.stdout).systemMessage, /OpenAI-style key/);
assert.ok(!postMcpHit.stdout.includes(syntheticOpenAi));

const postAwsMcpHit = run("codex-secrets-tripwire.mjs", {
  hook_event_name: "PostToolUse",
  tool_name: "mcp__example__read_record",
  tool_response: { content: [{ type: "text", text: `AccessKeyId=${syntheticAwsTempId}` }] },
});
assert.equal(postAwsMcpHit.status, 0);
assert.equal(JSON.parse(postAwsMcpHit.stdout).continue, false);
assert.match(JSON.parse(postAwsMcpHit.stdout).systemMessage, /AWS access key id/);
assert.ok(!postAwsMcpHit.stdout.includes(syntheticAwsTempId));

const postAwsNamedHit = run("codex-secrets-tripwire.mjs", {
  hook_event_name: "PostToolUse",
  tool_name: "Bash",
  tool_response: { stdout: `AWS_SECRET_ACCESS_KEY=${syntheticAwsSecret}` },
});
assert.equal(JSON.parse(postAwsNamedHit.stdout).continue, false);
assert.match(JSON.parse(postAwsNamedHit.stdout).systemMessage, /AWS secret access key/);
assert.ok(!postAwsNamedHit.stdout.includes(syntheticAwsSecret));

const postMiss = run("codex-secrets-tripwire.mjs", {
  hook_event_name: "PostToolUse",
  tool_name: "Bash",
  tool_response: { stdout: "ordinary output" },
});
assert.equal(postMiss.status, 0);
assert.equal(postMiss.stdout, "");

fs.writeFileSync(tripwirePath, "#!/usr/bin/env node\nprocess.exit(1);\n");
const postFailure = run("codex-secrets-tripwire.mjs", {
  hook_event_name: "PostToolUse",
  tool_name: "Bash",
  tool_response: { stdout: "ordinary output" },
});
assert.equal(postFailure.status, 0);
assert.equal(JSON.parse(postFailure.stdout).continue, false);
assert.ok(!postFailure.stdout.includes("ordinary output"));

fs.rmSync(root, { recursive: true, force: true });
console.log("all Codex secrets-guard adapter checks passed");
