// hooks/manifest.test.mjs
// The trust manifest must agree with the bytes beside it. Hashes are computed over LF-normalized
// content (pure CRLF -> LF, nothing else), exactly as refresh-guard.mjs does, so a Git for
// Windows checkout hashes the same as the reviewed source.
import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const manifest = JSON.parse(fs.readFileSync(path.join(here, "secrets-guard.manifest.json"), "utf8"));
const normalizeLf = (buf) => Buffer.from(buf.toString("utf8").replaceAll("\r\n", "\n"), "utf8");
const sha = (name) => crypto.createHash("sha256").update(normalizeLf(fs.readFileSync(path.join(here, name)))).digest("hex");

let checked = 0;
for (const group of ["files", "local_files"]) {
  for (const [name, want] of Object.entries(manifest[group])) {
    assert.equal(sha(name), want, `${name} differs from its manifest hash; change both in one reviewed pull request (node hooks/manifest-regen.mjs)`);
    checked += 1;
  }
}
assert.ok(typeof manifest.ref === "string" && manifest.ref.length > 0, "manifest.ref must name the reviewed change");
console.log(`manifest: ${checked}/${checked} pinned files match`);
