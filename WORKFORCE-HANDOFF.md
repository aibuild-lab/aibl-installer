# Connect an Essentials workbench to Workforce

State: reviewable source bridge. No accepted distribution is published or
activated by these changes. If the course team has not supplied the approved
inputs below, verified delivery is unavailable. Do not invent a download URL,
use a moving branch, or recreate the student's workbench.

Wade's Essentials setup stays unchanged. This handoff begins only when the
student chooses Workforce, in the same private workbench and selected app.
Existing students with the older enrollment skill use this same handoff;
manual replacement of their skills is unnecessary.

## Official inputs

The course team supplies the independently admitted distribution file and its
independent SHA-256, and the exact clean installer retained at
`~/.aibl/installers/INSTALLER_COMMIT`. The installer revision and bridge file
hashes must be included in the admitted distribution. Use the existing reviewed
exact-engine acquisition procedure described in FROZEN-FAMILY-DISTRIBUTION.md;
do not run the new-workbench setup handoff against an existing workbench.
The family must admit template, core and Workforce packages. Publication,
readback and native student qualification remain separate activation gates.

The file's own digest is not independent admission. These instructions contain
argument placeholders, not an accepted release or permission to publish one.

## Retain the exact installer

A workbench built by the paste route (SETUP-PROMPT.md) has the installer at
`~/GitHub/aibl-installer`, at whatever revision it was cloned. The bridge does
not run from there, and that folder is never pulled, reset or moved. Retain a
second, exact copy instead. `INSTALLER_COMMIT` is `installer.revision` in the
distribution file (40 hexadecimal characters).

If `~/.aibl/installers/INSTALLER_COMMIT` does not exist:

```text
git clone https://github.com/aibuild-lab/aibl-installer ~/.aibl/installers/INSTALLER_COMMIT
git -C ~/.aibl/installers/INSTALLER_COMMIT checkout --detach INSTALLER_COMMIT
```

On Windows the folder is `$HOME\.aibl\installers\INSTALLER_COMMIT`. A fresh clone
at the detached admitted commit is clean and carries the public origin, which
is what the engine verification checks; a copy of the local clone would not,
because its origin would be a local path. If the folder already exists, do not
modify it: the engine checks its revision, cleanliness and file hashes itself
and names any mismatch. Run every enrollment command below from that folder,
with `python3 -B` (or `py -3 -B`), so no cache files are written into it.

## Agent-operated enrollment

Use the verified Python launcher for the host (`python3` normally on macOS,
`py -3` where verified on native Windows). Quote actual absolute paths. From the
exact retained installer, first inspect:

```text
python3 -B scripts/enroll.py --workbench WORKBENCH --check --json
```

This changes no student files. It reports actual access, not invitation timing.
Readability alone does not prove that verified delivery is available.

For a supported Essentials template workbench without a family record:

```text
python3 -B scripts/enroll.py --workbench WORKBENCH --program agent-workforce --preview --harness codex --distribution DISTRIBUTION_FILE --distribution-sha256 INDEPENDENT_SHA256 --json
```

Use `--harness claude` for the student's selected Claude client. Do not switch
clients. An existing verified family workbench uses its installed enrollment
helper and existing preview route, without the bridge arguments.

Explain the returned additions and replacements. The upgrade includes all three
supplied core skills: enrollment, personalization and checkpoint. Existing
context, root guidance, work, history and index are preserved. Recognized
unchanged template skills can be upgraded; edited skills, unknown collisions,
unsupported templates and damaged historical records stop for review.
No installed-family record is manufactured to bypass these checks.

After the student confirms those exact changes:

```text
python3 -B scripts/enroll.py --workbench WORKBENCH --apply-plan PLAN_ID --json
```

Selection and `--yes` do not authorize installation. A changed account, origin,
Git/file state, distribution or package input requires a fresh preview.
Do not commit, push, send work or change account/device permissions as part of
this operation. Refresh the same app after installation and follow the returned
`aibl-workforce` first action. `native_verification: pending` means no worker use
or learning outcome has yet been proven.

## Recovery

Retain the returned plan ID. Retry it after a lost response. An interrupted
package transaction names recovery explicitly: run the exact retained engine's
`scripts/workbench_packages.py recover --root WORKBENCH`, then retry that plan.
Recovery preserves unexpected edits and stops for review rather than deleting
work. Do not delete the journal, backup, or external distribution association.
An association reserved before a failed acquisition keeps its original trusted
inputs; obtaining different inputs requires separate reviewed recovery.

## Source review and activation gates

The installer PR must land before the companion template PR is activated. The
companion source revision is `913cdf1819610666de51cbe34d5da90080280114`; the prior
supported template revision is `d89625d3ce99ee48f11d11c6186a39e227f93b37`.
The installer embeds their reviewed supplied-file hashes and Git tree identities.
Root guidance and personalized seed files are never used as replaceable skills.
The public ZIP fixtures are exact `git archive` exports of those revisions;
private course payloads are never included in the public test fixtures.

Run `scripts/validate-course-setup`. The bridge tests exercise both actual public
template trees with real Git and package transactions. Account responses,
release transport, clock and retained-engine identity are simulated. Optionally
set `AIBL_BRIDGE_CANDIDATE_BUNDLES` to the external output of Internal's existing
`family_packages.py` builder to verify the actual course/core payloads and the
installed helper's argument interface. That test is a local private-source gate,
not public CI's substitute for an accepted release or a native worker invocation.

Before student activation, publish and read back the exact accepted package and
installer combination, then observe fresh and returning-student journeys on each
supported native client/platform, including the real Writer, student inspection,
Reviewer and return to saved work. Source checks do not satisfy those gates.
