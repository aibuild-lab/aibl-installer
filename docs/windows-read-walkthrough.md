# Native Windows 11 Claude Desktop Code walkthrough: prepared, not executed

Status: **prepared only.** Nobody has run this procedure. Nothing in this repository claims that
built-in Read protection works in Claude Desktop on Windows. Source tests and disposable installs
(including `hooks/secrets-guard.read-paths.test.mjs`, which covers POSIX) cannot establish Desktop
activation. A working-Read announcement stays blocked until this walkthrough passes and a person
who did not write the change records the result.

Authorize one disposable Windows 11 account and one bounded attempt separately. Use only fake
content. Keep every record body-free and anonymous: classes, versions, hashes and PASS or HOLD
words, never file contents, account names or private paths. Do not retry a consumed attempt without
a diagnosed correction and a new bounded approval. Do not touch real learner credentials, remotes
or accounts.

## 0. Record the versions first

Write these down before changing anything:

- Claude Desktop version and the Claude Code runtime it bundles.
- Node version and the absolute Node path the hook command will use.
- Git version and credential helper name (name only).
- Windows 11 build.
- The exact reviewed source refs of the installer, Agent Native OS and Agent Native Camp
  checkouts (full commit IDs), the installer manifest `ref`, and the manifest SHA-256 shared by the
  installer current manifest and the OS current anchor.
- Whether the account directory contains a space (yes or no only).

## 1. Choose a hook-only discriminator, then confirm no native rule denies it

Claude Code's native `permissions.deny` rules the installer writes already deny built-in Read of
`.env`, `**/.env`, `**/.env.local`, `**/.env.*.local`, `**/.env.*`, `**/*.pem`, `**/id_rsa`,
`**/id_ed25519`, `**/credentials*` and `**/secrets/**`. A refusal for one of those names cannot show
that the hook ran. Use a name only the hook protects:

- Discriminator target: a fake file named `synthetic-hook-only.pfx` containing only the fake text
  `HOOK_ONLY_MARKER_FAKE`. (`.pfx`, `.p12`, `.jks`, `.keystore`, `prod.env`, `id_rsa.bak` and
  `aws-credentials.csv` are hook categories with no native rule.)
- Confirmation, on the **old** reviewed installation (the registration without `Read` in its
  matcher): ask Desktop Code to use built-in Read on the discriminator. It must **succeed** and show
  the fake marker. That proves no native rule denies it and that the old installation does not cover
  Read. If it is denied there, stop: the discriminator is also natively denied, and a different one
  is needed before anything else.

## 2. Recognized topology, preview and approval

1. On the old installation, record pre-state fingerprints (hashes and modes only), settings keys and
   hook registration. Create the reviewed topology for the case under test (the mixed state, or
   any of the receipt-free topologies in `hooks/README.md`).
2. From the verified, reviewed installer checkout run
   `node hooks/refresh-guard.mjs --migration-preview --json` (with the same client flags the install
   will use). Expect `eligibility: eligible-migration`, the named `topology` and `topologyClients`,
   zero writes, and a separate approval. Any `hold` stops the walkthrough at that stage: record the
   `failureClass` and next action, and do not apply anything.
3. After the separate bounded approval, run `node hooks/refresh-guard.mjs` for every named client.
   Run `--check --json` and the Agent Native OS check. Record the new receipt manifest identity, the
   exact Read matcher in the registration, the Codex registration, and that unrelated settings,
   hooks, project configuration and file modes are unchanged.

## 3. Prove the registered hook launches

A hook that cannot launch is a non-blocking error: the tool runs unguarded. So launching must be
shown without depending on a denial.

- Run the exact registered hook command from a PowerShell prompt in the same account with a
  synthetic PreToolUse payload for the discriminator path. Expect the fixed denial JSON containing
  `[secrets-guard hook]` and exit code 0. With the payload for an ordinary fake file expect no
  output and exit code 0. Record the Node path the command used.
- After the restart in step 4, open Desktop's hook inspection surface and record that the
  PreToolUse hook is registered with a matcher containing `Read`. Any "hook failed" or "hook error"
  line in the session means the activation stage is not proven.

## 4. Restart and new-session activation

Fully quit Claude Desktop (including its tray entry; confirm no Claude process remains), reopen it,
and start a **new** Code session. Record that it is new. A session opened before the registration
changed does not count.

## 5. Control matrix

Record each row separately. A model declining in its own words, a missing-file result, or a refusal
whose source cannot be named is not proof.

| Control | Tool | Expected | Evidence to record |
|---|---|---|---|
| Normal command `echo CAMP_CANARY_ALLOWED` | PowerShell | runs | output present |
| Ordinary fake file | built-in Read | allowed | marker shown |
| Exact templates `.env.example`, `.env.sample`, `.env.template`, `.env.dist` | built-in Read | allowed | marker shown for each |
| Nonexistent ordinary file | built-in Read | file-not-found, not a hook denial | message class |
| Hook-only discriminator `.pfx` | built-in Read | denied by the hook | `[secrets-guard hook]` present, marker absent |
| Nonexistent `.pfx` path | built-in Read | hook denial (name is judged without opening) | `[secrets-guard hook]` present, differs from the file-not-found row |
| Protected `.env` | built-in Read | denied; attribute to native or hook | which text appeared; a native-only refusal is `ATTRIBUTION_NATIVE`, not hook proof |
| `.env.example.local` | built-in Read | denied; attribute | same |
| Protected file | PowerShell `Get-Content` | denied by the shell guard | `[secrets-guard hook]` present; a separate route from built-in Read |

For independent hook attribution beyond the discriminator, use a separate isolated synthetic hook
configuration only if still needed, and keep learner-normal protection enabled.

## 6. Windows alias controls

Run each against the hook-only discriminator so a native rule cannot mask the result, once from an
ordinary account directory and once from an account directory containing a space. Record one of
`DENIED_BY_HOOK`, `ALLOWED_UNEXPECTED`, or `UNOBSERVED`. An alias that cannot be created or run is
`UNOBSERVED` and stays pending. It is never a pass by omission, and an unsupported alias is not
claimed to be protected.

- Directory junction (`mklink /J`) to the folder holding the file, read through the junction path.
- File symbolic link, if the account may create one (Developer Mode or elevation); otherwise
  `UNOBSERVED`.
- Extended-length path `\\?\C:\...`.
- UNC path to the same file through an administrative share, if the account can use one.
- Forward-slash spelling `C:/.../synthetic-hook-only.pfx`.
- Case variant `SYNTHETIC-HOOK-ONLY.PFX`.
- `..` traversal in a plain path, and `..` after the junction.
- NTFS alternate-data-stream spellings (`file.pfx::$DATA`, `file.pfx:stream`). The source tests do
  not classify these lexically; record exactly what the hook did.
- Trailing dot and trailing space (`file.pfx.`, `file.pfx `).
- An 8.3 short name, if short names are enabled on the volume.

## 7. Governed update dry preview (fake transport only)

From the Camp checkout run `node scripts/safe-os-update.mjs --os "<disposable OS path>" --dry-run`
against a disposable private Git fixture with a fake remote. Expect an unproven HTTPS credential to
stop before any merge, and `A separate gh login does not prove Git push authority` in the report.
Git Credential Manager (`credential.helper = manager`) is the Windows default and is **not** a
recognized HTTPS route today (see `docs/course-safety.md`, Facilitator workflow authorization
recovery), so an HTTPS hold is the expected Windows result. A positive path can be exercised only
with a repository-authorized SSH fixture remote, and an SSH URL alone is not proof of authentication
or repository permission.

## 8. Cleanup and result

Remove only the disposable markers, junctions, links, streams and fixture repositories this attempt
created. Capture final fingerprints and compare them with the pre-state. Keep the retained installer
files and the receipt for comparison.

Record, per stage, one of `PASS`, `HOLD`, `UNOBSERVED`, `UNVERIFIED_CLIENT_ACTIVATION`: versions,
discriminator confirmation, preview, apply, hook launch, restart, each control row, each alias, the
dry preview, cleanup. Any stage that could not run keeps its specific hold; nothing is inferred
from a neighbor. Source implementation, on-disk health, client activation, behavioral proof,
review, merge and publication remain separate statements.
