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

// Every receipt-bearing release since R-774 is preserved twice under one ref: its manifest, byte for
// byte (installations with a receipt), and its record in the installer-deployed identities
// (installations without one). refresh-guard.mjs must list exactly the preserved files.
const deployed = JSON.parse(fs.readFileSync(path.join(here, "secrets-guard.installer-deployed.identities.json"), "utf8")).states;
const preservedNames = fs.readdirSync(here).filter((name) => /^secrets-guard\..+\.manifest\.json$/.test(name)).sort();
const source = fs.readFileSync(path.join(here, "refresh-guard.mjs"), "utf8");
const listed = [...source.match(/PRIOR_RECEIPT_MANIFEST_FILES = \[([^\]]*)\]/)[1].matchAll(/"([^"]+)"/g)].map((found) => found[1]);
assert.deepEqual([...listed].sort(), preservedNames, "PRIOR_RECEIPT_MANIFEST_FILES must list every preserved manifest and nothing else");
const refs = [manifest.ref];
for (const name of preservedNames) {
  assert.ok(manifest.local_files[name], `${name} must be pinned in local_files`);
  const preserved = JSON.parse(fs.readFileSync(path.join(here, name), "utf8"));
  refs.push(preserved.ref);
  if (name === "secrets-guard.r774.manifest.json") continue; // R-774 is its own topology
  const records = deployed.filter((state) => state.ref === preserved.ref);
  assert.equal(records.length, 1, `${name}: its release needs exactly one installer-deployed record`);
  assert.deepEqual(records[0].files, preserved.files, `${name}: installer-deployed record files differ`);
  for (const [file, hash] of Object.entries(records[0].local_files))
    assert.equal(hash, preserved.local_files[file], `${name}: installer-deployed record ${file} differs`);
}
assert.equal(new Set(refs).size, refs.length, "every preserved release and the current one need their own ref");
assert.ok(!deployed.some((state) => state.ref === manifest.ref), "the current release is not yet an earlier release");
console.log(`manifest: ${checked}/${checked} pinned files match`);
console.log(`manifest: ${preservedNames.length} preserved releases agree with refresh-guard.mjs and the installer-deployed record`);
