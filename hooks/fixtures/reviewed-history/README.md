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

The `.bytes` suffix keeps editors, linters and hook-source scanners from treating them as live code.
