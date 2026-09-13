#!/usr/bin/env node
// Codex adapter for the immutable Claude secrets tripwire installed beside it.
//
// The pinned tripwire detects and redacts secret-shaped values, but its
// `updatedToolOutput` field is Claude-specific. Codex PostToolUse does not offer
// a general shell-output replacement contract, so this adapter discards that
// field and emits only supported, names-only stop/warning fields. It never
// forwards the original or redacted tool response.

import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { redactAwsCredentials } from "./aws-credential-patterns.mjs";

const hooksDir = process.env.CODEX_GUARD_HOOKS_DIR
  ? path.resolve(process.env.CODEX_GUARD_HOOKS_DIR)
  : path.dirname(fileURLToPath(import.meta.url));
const canonicalTripwire = path.join(hooksDir, "secrets-tripwire.js");
const KNOWN_HIT_NAMES = [
  "1Password service token",
  "Anthropic API key",
  "Langfuse secret key",
  "OpenAI-style key",
  "GitHub token",
  "Slack token",
  "Supabase secret",
  "AWS access key id",
  "AWS secret access key",
  "AWS session token",
  "Apify token",
  "Firecrawl key",
  "Google API key",
  "private key block",
  "DB URL with password",
  "Bearer token",
  "JWT",
];

function stop(names = []) {
  const label = names.length ? names.join(", ") : "secret-shaped output";
  const message = `SECRET TRIPWIRE: ${label} detected. The value is not repeated. Treat it as compromised and rotate it.`;
  process.stdout.write(JSON.stringify({
    continue: false,
    stopReason: message,
    systemMessage: message,
  }));
  process.exit(0);
}

let raw = "";
let input;
try {
  raw = fs.readFileSync(0, "utf8");
  input = JSON.parse(raw);
} catch {
  stop();
}

const awsSource = input?.hook_event_name === "PostToolUseFailure"
  ? (typeof input.error === "string" ? input.error : "")
  : input?.tool_response;
const awsResult = redactAwsCredentials(awsSource);
if (awsResult.names.length) stop(awsResult.names);

if (!fs.existsSync(canonicalTripwire)) stop();

const child = spawnSync(process.execPath, [canonicalTripwire], {
  input: raw,
  encoding: "utf8",
  maxBuffer: 4 * 1024 * 1024,
  windowsHide: true,
});

if (child.status !== 0 || child.signal) stop();
if (!child.stdout.trim()) process.exit(0);

try {
  const result = JSON.parse(child.stdout);
  const context = result?.hookSpecificOutput?.additionalContext;
  if (typeof context !== "string") stop();
  const names = KNOWN_HIT_NAMES.filter((name) => context.includes(name));
  stop(names);
} catch {
  stop();
}
