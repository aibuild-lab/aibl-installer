# Reviewed historical hook bytes

These files are exact historical bytes of the guard components, kept so migration tests exercise
real reviewed content instead of comment-shaped stand-ins. They are test inputs only: they are
never executed, never installed by the installer, and never an authority.

Identity comes from the pinned compatibility records, not from this folder:

- `legacy/` is checked at test time against `hooks/secrets-guard.legacy.identities.json`
  (`secrets-guard-2026-09-08`).
- `r774/` is checked against the immutable `hooks/secrets-guard.r774.manifest.json`
  (`aibl-installer-r774-guard-ownership`). The R-774 tripwire is byte-identical to the current
  `hooks/secrets-tripwire.js` and is not duplicated here.
- `anos-2026-09-02/` is checked against the agent-native-os #108 record (`f3231373`) in
  `hooks/secrets-guard.course-deployed.identities.json` (`secrets-guard-2026-09-02`). Its tripwire
  and installer are the legacy bytes above, and its other adapters equal the current ones.
- `installer-2026-09-24/` is checked against `hooks/secrets-guard.installer-deployed.identities.json`
  (`aibl-installer-2026-09-24-secrets-guard-narrow-false-positives`, commit `181fa82`, #27). Its
  tripwire and adapters are the current bytes and are not duplicated here.
- `workshop-<commit>/` (six folders) are the exact `hooks/` blobs of `aibuild-lab/workshop-installer`
  at that commit, checked against `hooks/secrets-guard.workshop-installer.identities.json`. Each
  holds all three files, so a test can install a workshop state with its own `install.mjs`.
- `workshop-<commit>-crlf/` (thirteen folders, one per workshop main state) are the same three files
  as a Git for Windows checkout (`core.autocrlf=true`) of `aibuild-lab/workshop-installer` at that
  commit leaves them: CRLF line endings, nothing else different. Checked against the `-crlf` records
  in the same identities file. `.gitattributes` keeps them byte-exact (`-text`).

The `.bytes` suffix keeps editors, linters and hook-source scanners from treating them as live code.
