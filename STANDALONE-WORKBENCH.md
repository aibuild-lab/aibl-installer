# Standalone My Workbench route

State: successor source implementation. Publication readback, native app use
and ordinary-student qualification require their own exact-version evidence.

The verified v2 family contains `agent-workbench` and `workbench-core`. Setup
creates an independent private `my-workbench` from those public packages. It
does not require private Essentials or Workforce access. The generic core
supplies `aibl-personalize`, `aibl-checkpoint` and `aibl-enroll` in both supported
app locations. Students use the app they selected.

## Setup

The successor official handoff supplies a downloaded native launcher, its
independent SHA-256, an exact installer commit, and a frozen family distribution
with its independent SHA-256. On macOS the argument order is
`bash start.sh my-workbench DISTRIBUTION_FILE DISTRIBUTION_SHA256 INSTALLER_COMMIT LAUNCHER_SHA256`;
select Codex with `AIBL_HARNESS=codex`. On native Windows use
`start.ps1 -Course my-workbench -DistributionLock DISTRIBUTION_FILE
-DistributionSHA256 DISTRIBUTION_SHA256 -InstallerCommit INSTALLER_COMMIT
-LauncherSHA256 LAUNCHER_SHA256 -Harness codex` (or `claude`). These are argument
templates, not approved release identities. Do not replace the placeholders
with mutable branches or hashes from an untrusted download.

Both launchers retain the exact engine at `.aibl/installers/INSTALLER_COMMIT`
before `family_setup_handoff.py` verifies and acquires public template/core.
Sign-ins remain visible. No successor is advertised through the existing public
entry until the exact distribution and native student gates are complete.

From the clean retained installer named by an independently admitted family,
run `scripts/course_setup.py` with `--family-lock`, `--family-sha256` and
`--family-bundles`, plus `--harness claude` or `--harness codex`. The bootstrap
owns acquiring those independently admitted inputs. Do not treat an installed
marker, a downloaded package or a moving branch as a new trust admission.

The selected app and GitHub must be signed in. Setup uses a verified empty
private repository and a local staging folder, makes one initial commit,
pushes it, and verifies the remote identity before showing the workbench.
Progress lives outside the repository in `~/.aibl/setup/`.

The official handoff also reserves a private immutable association in
`~/.aibl/workbench-distributions/`, keyed to the resolved workbench path. It
retains the originally supplied independent distribution digest, distribution
bytes, student repository and exact installer, before any repository creation.
Interrupted setup reuses that same association. Changed distribution or account
identity stops rather than replacing it. Keep this custody directory and its
verified package cache; it is not part of the student's Git repository.

If creation or the first push loses its response, rerun with the same inputs.
Setup reads the provider and local state before deciding whether an operation
is still needed. It never overwrites a nonempty foreign repository or folder.
Interrupted seed writes reuse package recovery. Additional work or changed
seed files stop for review and remain in place.

An established v2 workbench exits before composition, context creation, Git
configuration, or any student-repository write. It preserves edited and deleted
files, uncommitted work, unpushed commits, the index and local learning state.
The result is `already_initialized`, not a new claim of native verification.

## Enrollment

The workbench's `aibl-enroll` wrapper invokes the unchanged exact retained
installer. It does not clone or pull a newer engine.

1. Inspect with `scripts/enroll.py --workbench PATH --check --json`. Only
   readable programs appear, as `Ready to add` or `Already connected`. Missing
   program help names the signed-in username without guessing access status.
2. Select if useful with `--program agent-workforce --yes`. This records only
   the choice. It does not install files or grant access.
3. Preview with `--preview --program agent-workforce --workbench PATH --json`.
   The official setup association supplies the independently retained admission.
   Only the selected optional package is acquired; installed template/core and
   any earlier program bundles are reverified from the retained cache. Each
   explicit acquisition checks the admitted index's expiry and withdrawal state.
   The result includes `plan_id`,
   file changes and the verified first action. Plans live privately outside the
   workbench in `~/.aibl/enrollment/`.
4. Explain the preview and obtain the student's confirmation. Apply that exact
   ID with `--apply-plan ID --workbench PATH --json`. The stored plan binds
   account, repository, Git state, local changes, candidate hashes and connection
   metadata. Changed inputs require a fresh preview and confirmation.
5. Refresh the selected app and perform the first action. The file installer
   returns `installed` with `native_verification: pending`. It does not convert
   file presence or a simulated exercise into native or student evidence.

The explicit `--family-lock`, `--family-sha256`, `--family-bundles` trio remains
available for independently reviewed candidate inputs. A workbench without a
retained official association must obtain those official independent inputs;
the helper never creates trust from its installed marker. Changed origin,
engine, association, distribution, installed pins or cached bytes stop for
review. Established official setup reruns read their existing association and
make no workbench file or Git writes, downloads or replacement admissions.
Enrollment does not refresh the engine or silently advance a distribution.
After a package or installer update, the original setup association is not
silently replaced. If that original binding differs from the current workbench,
acquire the newly approved distribution with `scripts/frozen_family.py`, including
all installed products and the selected optional product, and pass its explicit
family-lock/digest/bundles trio to enrollment preview. This is a new independent
admission, not a digest inferred from an installed marker.

The optional free lesson-8 support uses `--program agent-essentials` with its
publicly admitted package. It is absent from day-one setup and supplies only
its declared support files. The Lab has no installation route in this release.

A confirmed apply can be retried with the same plan. If a package transaction
was interrupted, run the retained package engine's `recover --root PATH`, then
retry. Completed writes with a lost response are reconciled against the exact
completed backup transaction. Later edits are preserved. Keep the returned
rollback identity; local learning backup is separate from Git and package
recovery.

Enrollment refuses to change an already installed package pin. Later updates
require one student-owned PR, explicit student approval, merge readback, safe
local synchronization, selected-app refresh and verification. Faculty have no
routine role in approving or merging that PR.
