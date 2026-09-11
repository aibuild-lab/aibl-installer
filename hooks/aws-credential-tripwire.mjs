#!/usr/bin/env node
// Supplemental Claude Code PostToolUse/PostToolUseFailure protection for AWS credential
// forms absent from the currently pinned immutable release. Successful output is redacted;
// failure output receives names-only context and is never repeated.

import fs from "node:fs";
import { redactAwsCredentials } from "./aws-credential-patterns.mjs";

let input;
try {
  input = JSON.parse(fs.readFileSync(0, "utf8"));
} catch {
  process.exit(0);
}

const eventName = input.hook_event_name || "PostToolUse";
if (!["PostToolUse", "PostToolUseFailure"].includes(eventName)) process.exit(0);
const source = eventName === "PostToolUse" ? input.tool_response : (typeof input.error === "string" ? input.error : "");
const result = redactAwsCredentials(source);
if (!result.names.length) process.exit(0);

const hookSpecificOutput = {
  hookEventName: eventName,
  additionalContext:
    `AWS SECRET TRIPWIRE: ${result.names.join(", ")} detected. Do not reconstruct or repeat the value. Treat it as compromised and rotate it.`,
};
if (eventName === "PostToolUse") hookSpecificOutput.updatedToolOutput = result.value;
process.stdout.write(JSON.stringify({ hookSpecificOutput }));
process.exit(0);
