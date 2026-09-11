# Secrets guard (Claude Code and Codex hooks)

Harness-level protection that stops Claude Code or Codex from printing a student's secrets to
the terminal. Installed by the AIBL installer at the **user level** (`~/.claude/settings.json`
and `~/.codex/hooks.json`), so it applies in **every** project on the machine, in both apps.

This directory is the canonical home of the guard as of 09-11-2026. It was ported from
`aibuild-lab/agent-native-os` (`scripts/refresh-guard.mjs` and the Codex and AWS adapters, plus
the pending Stripe rule from workshop-installer #17 and the trust-step documentation from
agent-native-os #89), so new students receive the current guard from one place.

**One command per app:** `node hooks/refresh-guard.mjs --claude` or `--codex` installs that app's
guard and touches nothing of the other's; with neither flag it installs both. `--check` inspects the
on-disk installation without changing anything (an app not selected reports "not selected"). The
app must then be fully quit and reopened, and Codex trusted once (below), before its guard is
actually running. The installer prompt passes the student's app and offers the other; a student
who chose one app never gets the other app's files unless they ask.

In one line for students: it only takes one time. One key printed to the screen, pasted into a chat,
or written into a file that gets pushed, and it is exposed; then you are rotating keys, checking what
had access, and telling people. The guard is the seatbelt, installed before anyone needs it.

Why a hook and not a CLAUDE.md rule: a written rule only works if the model chooses to obey
it every time. A `PreToolUse` hook inspects the literal command and refuses the dangerous
class deterministically, whether or not the model "remembers." (Anthropic issue #32523.)

## Files

- **`secrets-guard.js`** - `PreToolUse` hook. Blocks the *dump-a-secret-to-stdout* class:
  `infisical secrets`/`export`, `bw export`/`list items`, `op item get --reveal`, `--plain`,
  raw `op read`, secret-looking `echo`/`printf`/`printenv` variable reads, bare
  `env`/`printenv`/`set`/`declare -p`, reads of `.env`/`.pem`/`id_rsa`/`credentials`,
  language-eval exfil, `docker compose config`. **Allows** the legitimate forms: `op run` /
  `infisical run` (runtime injection), masked first4 checks, `bw get`, `op whoami`,
  `printenv PATH`, `env FOO=bar cmd`, `.env.example`. Vault-agnostic. Written in Node (a Claude
  Code dependency) so it runs unchanged on Mac and Windows/Git Bash. It guards **both** the Bash
  tool and the PowerShell tool: on Windows, Claude Code exposes a separate PowerShell tool, so
  the guard also blocks `Get-ChildItem Env:` (and `gci`/`ls`/`-Path`/piped forms),
  `[Environment]::GetEnvironmentVariables()`, bare `Get-Variable`/`gv`, and
  `Get-Content`/`gc`/`type`/`Select-String` reads of secret files, while allowing `$env:NAME`
  single reads and `ls $env:VAR` path uses. Command inspection is token-based and recursive, so a
  runtime-injection wrapper (`op run` / `infisical run`), a path-qualified command
  (`/usr/bin/env`), and a nested shell (`bash -c '<cmd>'`) are all vetted without dropping any
  sibling segment. It also blocks a literal vendor-shaped key embedded in a shell command
  (`printf`, heredoc, `node -e writeFileSync`, inline `Authorization: Bearer …`) and - via the
  `Write`/`Edit`/`MultiEdit`/`NotebookEdit` matcher - a real key written straight into a file.
  Direct `infisical dynamic-secrets` and `infisical pam` invocations are denied because they can
  return credentials outside the reviewed launcher lifecycle. Infisical token flags and sandbox
  bypass flags are denied for every Infisical command. The only `infisical secrets` exception is
  sandboxed `secrets agent-proxy run`, whose child is recursively inspected.
- **`secrets-tripwire.js`** - `PostToolUse` / `PostToolUseFailure` hook. On success it **redacts**
  every secret-shaped match from the tool output before Claude sees it (`updatedToolOutput`),
  preserving the output's shape; on failure (which cannot be rewritten) it emits names-only
  context telling the model not to echo the value. Either way it logs a dated near-miss to a
  `0600` file - names only, never the value.
- **`install.mjs`** - idempotent Claude installer. Merges the hooks + `permissions.deny` block into
  `~/.claude/settings.json` without clobbering existing keys; backs the file up first. Each managed
  hook gets its own dedicated matcher group, so repairing our matcher never widens or narrows an
  unrelated sibling hook's matcher; only whole-token copies of our own script are removed. Settings
  are written atomically (temp + rename) at mode `0600`, and the hook scripts are set to `0700`.
- **`refresh-guard.mjs`** - the installer for **both** apps. Reads the canonical files beside it,
  verifies every one against `secrets-guard.manifest.json` (LF-normalized sha256), stages and
  atomically swaps only what changed with backup and rollback, wires `~/.claude/settings.json`
  through `install.mjs`, and writes `~/.codex/hooks.json` (user level, strict schema: it strips a
  stray `description` key that would make Codex load no hooks) plus per-platform launchers.
  `--check` reports on-disk health; `--session-check` prints a one-line warning for a session
  hook. Neither can observe runtime activation.
- **`codex-secrets-guard.mjs`** - Codex `PreToolUse` adapter. Runs the canonical guard beside it
  and relays only reviewed, names-free denials, closing the `apply_patch` input-shape gap. Matches
  every locally hookable tool (`*`).
- **`codex-secrets-tripwire.mjs`** - Codex `PostToolUse` adapter. Codex cannot rewrite tool output,
  so this returns a names-only warning and stops the turn; it does not claim redaction.
- **`aws-credential-patterns.mjs`, `aws-credential-guard.mjs`, `aws-credential-tripwire.mjs`** -
  supplements for temporary `ASIA...` access-key ids and named secret-key or session-token
  assignments. Claude's post-use supplement redacts; Codex's warns.
- **`secrets-guard.manifest.json`** - the trust anchor: sha256 of every file above. A hash changes
  only in the same reviewed pull request as its file; `manifest.test.mjs` fails CI when they
  disagree, and `manifest-regen.mjs <ref>` rewrites the hashes for that reviewed change.

## Codex requires a one-time trust, or it silently runs no hooks

Installing the guard is not the same as it running. **Codex will not execute a hook until the
student has trusted it**, and an untrusted hook is skipped in silence: no warning, no error, and
every on-disk check still reports healthy. Trust is the difference between installed and working.

Grant it once, per machine:

1. Launch plain `codex` in a terminal, from the workbench folder.
2. Accept "Do you trust the contents of this directory?" if it appears.
3. On the **Hooks need review** screen, choose **Trust all and continue**. "Review hooks" shows
   exactly what is being approved.

Codex stores the decision in `~/.codex/config.toml` under `[hooks.state]` as a `trusted_hash` per
hook. Two consequences follow from it being a hash:

- **A guard update prompts again** ("1 hook is new or changed"). Expected, not a fault. Re-approve.
- **Headless Codex can never be trusted this way.** `codex exec`, schedulers, and CI have no
  screen, so they take the "Continue without trusting (hooks won't run)" branch every time. Hooks
  are not a secret boundary for automation; keep secrets out of the environment there instead.

**Prove it by behavior, never by installer output.** In the same interactive `codex` session, ask it
to run `cat .env`. A `hook: PreToolUse Blocked` line is proof. On-disk hashes are not. The Claude
side is proven the same way with a fresh headless process, because Claude Code's hooks do run
headless: `claude -p "Run the command: cat .env"` must show the guard's own refusal.

## Validation

Run all of these before a pull request; CI runs them on Ubuntu, Windows and macOS:

- `node hooks/manifest.test.mjs` - every pinned hash matches its file.
- `node hooks/secrets-guard.test.mjs` - the allow/block table for the canonical guard (Bash and
  PowerShell, the `$(op read ...)` injection shapes, vendor key shapes including Stripe live keys).
- `node hooks/secrets-tripwire.test.mjs` - redaction and names-only failure context.
- `node hooks/install.test.mjs` - the Claude settings installer against a throwaway HOME.
- `node hooks/codex-secrets-guard.test.mjs` - the Codex adapter relays reviewed denials only.
- `node hooks/refresh-guard.test.mjs` - the both-apps installer against a throwaway HOME: pinned
  hash verification, no partial write on a bad file, CRLF checkout acceptance, bare-CR tamper
  refusal, rollback, idempotence.

No secret command is executed by any test. See `Secrets-Guard-Hook-Plan.md` in Wade's workbench
for the full plan.

## Reviewer notes

- **The manifest is the pin.** The bytes are read from this directory, never downloaded, and
  refused if they do not match the manifest. Change a file and its hash in one reviewed change.
- **Conservative on language-eval.** The guard blocks any `node -e` / `python3 -c` that touches
  `process.env` / `.env`, including benign one-variable reads. Safe default; workaround is
  `printenv NAME`.
- The guard is a strong floor, not a proof - static matching has edge cases. It's paired with
  the tripwire and is best combined with narrow per-session secrets identities.

## Known limits (already triaged - please don't re-report as new)

A hook inspects a command string before it runs. It cannot follow data through a file, and it
cannot see what you type inside an interactive session. These are accepted consequences of that,
not oversights:

- **Path laundering.** `cp .env /tmp/x && cat /tmp/x` passes. Catching it needs data-flow
  analysis across commands, which a per-command matcher does not have.
- **Interactive sessions.** `docker exec -it web bash` and `aws ssm start-session` are allowed.
  The guard vets the command that opens the session; whatever you type inside it is invisible.
- **Bare `heroku config`.** Prints all values and is not blocked. Every rule tried for it also
  caught `git config --list`, and a false block on that is worse than this gap.
- **Names-only reads are allowed on purpose.** `grep -oE '^[A-Z_]+=' .env`, `grep -c`, and
  `sed -i` cannot print a value, so they pass. Confirming a key is present is fine; printing it
  is not. Same principle as the masked `... | head -c 4` fingerprint.
- **`show` and `describe` are qualified by binary**, so an unusual runtime's version of them is a
  miss. This is deliberate: unqualified, those two verbs cost 249 false blocks when replayed
  against ~9.5k real commands (`git show`, `npm show`, and the word "describe" in a commit body).
  Wrapper detection is the opposite case and fails *closed*.

Finding something outside this list is worth reporting. The hooks are validators, so a repro
never has to execute anything dangerous - feed the payload on stdin and read the verdict:

```bash
printf '{"tool_name":"Bash","tool_input":{"command":"<command>"}}' \
  | node ~/.claude/hooks/secrets-guard.js; echo "exit=$?"
```

Exit 0 with no deny output means the command would have run.
