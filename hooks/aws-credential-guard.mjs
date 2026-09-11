#!/usr/bin/env node
// Supplemental Claude Code PreToolUse guard for AWS credential forms absent from the
// currently pinned immutable release. Installed and checksum-verified by refresh-guard.mjs.

import fs from "node:fs";
import { findAwsCredential } from "./aws-credential-patterns.mjs";

function deny(name) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason:
        `This tool input contains what looks like ${name}. Use a placeholder or inject AWS credentials at runtime. [AWS credential supplement]`,
    },
  }));
  process.exit(0);
}

let input;
try {
  input = JSON.parse(fs.readFileSync(0, "utf8"));
} catch {
  process.exit(0);
}

const strings = [];
const collect = (value) => {
  if (typeof value === "string") strings.push(value);
  else if (Array.isArray(value)) value.forEach(collect);
  else if (value && typeof value === "object") Object.values(value).forEach(collect);
};
collect(input.tool_input);
const hit = findAwsCredential(strings.join("\n"));
if (hit) deny(hit);
process.exit(0);
