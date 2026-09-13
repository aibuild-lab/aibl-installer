#!/usr/bin/env node
// Codex adapter for the immutable secrets-guard release installed beside this file.
//
// The canonical guard already understands Codex's Claude-compatible PreToolUse
// deny response. This adapter closes the apply_patch input-shape gap and relays
// only reviewed names-free denials, so a malformed or surprising child response
// can never echo tool input back to Codex.

import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { findAwsCredential } from "./aws-credential-patterns.mjs";

const hooksDir = process.env.CODEX_GUARD_HOOKS_DIR
  ? path.resolve(process.env.CODEX_GUARD_HOOKS_DIR)
  : path.dirname(fileURLToPath(import.meta.url));
const canonicalGuard = path.join(hooksDir, "secrets-guard.js");

// The canonical guard owns these policy decisions. Keep the adapter useful without
// forwarding arbitrary child text by translating only exact, reviewed reasons from
// the pinned canonical release. Any unrecognized denial stays on the generic path.
const SAFE_CANONICAL_DENIALS = new Map([
  [
    "Infisical agent access must keep its operating-system sandbox enabled.  [secrets-guard hook]",
    "This guard blocks --no-sandbox flags in Infisical commands.",
  ],
  [
    "The local Infisical Agent Proxy must keep its OS sandbox enabled.  [secrets-guard hook]",
    "This guard blocks --no-sandbox flags in Infisical commands.",
  ],
  [
    "Do not place an Infisical token in a command. Use the named-human login session.  [secrets-guard hook]",
    "Do not place an Infisical token in a command. Use the named-human login session.",
  ],
  [
    "Do not place an Infisical token in the Agent Proxy command. Use the named-human login session.  [secrets-guard hook]",
    "Do not place an Infisical token in a command. Use the named-human login session.",
  ],
  [
    "Do not pass credential-shaped host environment variables into the Agent Proxy child.  [secrets-guard hook]",
    "Do not pass credential-shaped host environment variables into the Agent Proxy child.",
  ],
  [
    "Do not set credential-shaped environment variables in the Agent Proxy child.  [secrets-guard hook]",
    "Do not set credential-shaped environment variables in the Agent Proxy child.",
  ],
  [
    "infisical secrets commands can print vault values. Use a reviewed runtime delivery command instead.  [secrets-guard hook]",
    "Infisical secrets subcommands can print vault values. Use a reviewed runtime delivery command instead.",
  ],
  [
    "`docker inspect` renders the target's full configuration, which includes its environment variables. Read the single setting you need, or pass a --format/--property selector that excludes Env.  [secrets-guard hook]",
    "Docker inspect may read only the reviewed non-secret metadata fields. Use one --format selector for those fields.",
  ],
]);

function deny(reason) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: `${reason} [Codex secrets-guard adapter]`,
    },
  }));
  process.exit(0);
}

let raw = "";
try {
  raw = fs.readFileSync(0, "utf8");
} catch {
  deny("The secrets guard could not inspect this tool call, so it was blocked safely.");
}

let input;
try {
  input = JSON.parse(raw);
} catch {
  deny("The secrets guard received malformed tool input, so the call was blocked safely.");
}

const inputStrings = [];
const collectInputStrings = (value) => {
  if (typeof value === "string") inputStrings.push(value);
  else if (Array.isArray(value)) value.forEach(collectInputStrings);
  else if (value && typeof value === "object") Object.values(value).forEach(collectInputStrings);
};
collectInputStrings(input?.tool_input);
if (findAwsCredential(inputStrings.join("\n"))) {
  deny("The AWS credential supplement detected a literal credential in this command or write. Use a placeholder or inject it at runtime.");
}

// Codex can match apply_patch as apply_patch, Edit, or Write. The canonical
// guard's high-confidence write scanner understands the latter two. Normalize
// the free-form patch payload into Write.content without changing shell calls.
if (input?.tool_name === "apply_patch") {
  const strings = [];
  const collect = (value) => {
    if (typeof value === "string") strings.push(value);
    else if (Array.isArray(value)) value.forEach(collect);
    else if (value && typeof value === "object") Object.values(value).forEach(collect);
  };
  collect(input.tool_input);
  input = {
    ...input,
    tool_name: "Write",
    tool_input: { content: strings.join("\n") },
  };
}

if (!fs.existsSync(canonicalGuard)) {
  deny("The pinned secrets guard is missing, so this tool call was blocked safely.");
}

const child = spawnSync(process.execPath, [canonicalGuard], {
  input: JSON.stringify(input),
  encoding: "utf8",
  maxBuffer: 1024 * 1024,
  windowsHide: true,
});

if (child.status !== 0 || child.signal) {
  deny("The pinned secrets guard failed closed while inspecting this tool call.");
}

if (!child.stdout.trim()) process.exit(0);

try {
  const result = JSON.parse(child.stdout);
  if (result?.hookSpecificOutput?.permissionDecision === "deny") {
    const canonicalReason = result?.hookSpecificOutput?.permissionDecisionReason;
    deny(SAFE_CANONICAL_DENIALS.get(canonicalReason)
      || "The pinned guard detected a command or write that could expose a secret. Use a placeholder or inject the value at runtime.");
  }
} catch {
  deny("The pinned secrets guard returned an invalid response, so this tool call was blocked safely.");
}

process.exit(0);
