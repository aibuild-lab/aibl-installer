// hooks/manifest-regen.mjs
// Rewrite the trust manifest's hashes from the LF-normalized bytes beside it. Run this ONLY in the
// same reviewed pull request that changes a guard file; the point of the manifest is that the two
// never drift apart unreviewed. Usage: node hooks/manifest-regen.mjs <ref-name>
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const file = path.join(here, "secrets-guard.manifest.json");
const manifest = JSON.parse(fs.readFileSync(file, "utf8"));
const ref = process.argv[2];
if (!ref) { console.error("Usage: node hooks/manifest-regen.mjs <ref-name>   (for example aibl-installer-2026-09-11)"); process.exit(2); }
const normalizeLf = (buf) => Buffer.from(buf.toString("utf8").replaceAll("\r\n", "\n"), "utf8");
const sha = (name) => crypto.createHash("sha256").update(normalizeLf(fs.readFileSync(path.join(here, name)))).digest("hex");
for (const group of ["files", "local_files"]) {
  for (const name of Object.keys(manifest[group])) manifest[group][name] = sha(name);
}
manifest.ref = ref;
fs.writeFileSync(file, JSON.stringify(manifest, null, 2) + "\n");
console.log(`manifest rewritten for ${ref}; review the diff alongside the file change.`);
