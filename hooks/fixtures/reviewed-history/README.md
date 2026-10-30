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
- `workshop-<commit>/` (six folders) are the exact `hooks/` blobs of `aibuild-lab/workshop-installer`
  at that commit, checked against `hooks/secrets-guard.workshop-installer.identities.json`. Each
  holds all three files, so a test can install a workshop state with its own `install.mjs`.

The `.bytes` suffix keeps editors, linters and hook-source scanners from treating them as live code.
