# Frozen Workforce setup

The shared launchers retain the existing interactive course selector. A reviewed
Workforce distribution adds a frozen route that pins the AIBL launcher, installer
revision, setup code/catalog and both private product releases. No release ID or
private payload is embedded in this public installer repository.

## Build the external lock candidate

After the installer is committed, independently reviewed and locally validated,
use the two accepted product pins from the internal release owner:

```sh
python3 scripts/pin-course-distribution.py --essentials-pin "$ESSENTIALS_PIN" --workforce-pin "$WORKFORCE_PIN" --output "$EXTERNAL_LOCK"
```

The output directory must be outside this checkout. Existing output is never
replaced. The candidate has `aibl.course-distribution/v1`, course ID
`agent-workforce` (the registry program id), the exact installer repository/commit and five source
file hashes, and both exact `aibl.release-pin/v3` objects. Both product pins
must name the same accepted internal source commit. The release handoff
independently reviews and distributes the lock's SHA-256 and each launcher
SHA-256. Taking a pin from the archive being downloaded is not verification.

The six pinned files are `start.sh`, `start.ps1`, `course-options.json`,
`scripts/course_setup.py`, `scripts/pinned_distribution.py` and
`SETUP-PROMPT.md` (the guided app-first entry, so a cohort's instructions are
byte-identical too). The lock
generator is an operator tool; its output is independently reviewed and not
executed by the student launcher.

## Launch the exact distribution

The cohort handoff supplies exact download links at the installer commit,
the lock file, its digest and the platform launcher digest. Download the
launcher first and compare its hash before executing it. The launchers repeat
the launcher/lock hash check before installing missing prerequisites.

On macOS, after substituting the reviewed values:

```sh
bash ./start.sh agent-workforce ./course-distribution.json "$LOCK_SHA256" "$INSTALLER_COMMIT" "$START_SH_SHA256"
```

On native Windows PowerShell, after verifying the downloaded script's hash and
using the device's approved execution policy:

```powershell
./start.ps1 -Course agent-workforce -DistributionLock ./course-distribution.json -DistributionSHA256 $LockSHA256 -InstallerCommit $InstallerCommit -LauncherSHA256 $StartPS1SHA256
```

No command disables or bypasses execution policy. An effective Restricted or
signing policy can still prevent the script from starting; that requires the
device's approved route and separate observed acceptance. Browser GitHub and
Claude sign-in remains visible and with the student. Do not paste credentials
or account codes into course chat.

The pinned route fetches only the full installer commit into a fresh isolated
temporary checkout. It verifies the checked-out revision, clean state, source
hashes and the actual executed launcher bytes against the external lock before
running course setup. It then verifies student access to both private course
repositories and downloads `manifest.json` and `payload.zip` from the exact
Essentials product release. Archive and manifest hashes, product/source IDs,
regular files, paths, sizes and file hashes are checked before payload code runs.

## Private workbench and recovery

Pinned setup creates an empty private student repository and seeds it from the
verified archive with one independent initial Git commit. It never uses a
moving template default branch. The initial push is re-read and compared with
the local commit before setup continues. Only this initial accepted source is
pushed automatically; subsequent student work follows the course's reviewed
checkpoint/push flow. Git uses the student's configured native credential path;
this code does not alter global Git identity or credential configuration.

The project stores the Essentials installed manifest and a distribution record
under `.aibl/`. Both product pins are recorded, with Workforce adoption still
pending the Essentials gate. The local setup attempt records the distribution
digest, actual tool versions, source revision, launcher hash and observed
student commit/tree. This is provenance, not a passed learning assessment.

Interrupted creation is reconciled using the saved private-repository ID or
the exact local creation marker before retry. A lost initial push response
resumes the same staging history after re-reading the private remote. Existing
name collisions, unexpected staging files, modified supplied helpers, a changed
remote or a different distribution stop and preserve work. An older or newer
release needs the supported course update path; setup never relabels earlier
completion or overwrites a student's changes. An interrupted partial file may
need diagnosis when its bytes cannot be proved to be the accepted payload.

For source qualification run `scripts/validate-course-setup` and, with a
PowerShell runtime, `pwsh -NoProfile -File tests/test_windows_launcher.ps1`.
The pinned tests use synthetic bundles and account responses with real Git
init/commit/push/readback, including lost replies and student-work preservation.
They create no live accounts or repositories. Portable PowerShell parsing on
macOS does not establish native Windows setup.

The distribution freezes AIBL source and private course bytes. Official vendor
prerequisite installers and package managers still supply available compatible
versions, which are recorded at runtime. A frozen lock alone does not certify
every vendor version, bootstrap duration, native device policy, account flow or
beginner outcome. The course's complete distribution qualification must retain
those observed versions and untested boundaries.
