# From Essentials to Workforce

Review candidate: this PR does not activate a cutover or publish course files.
After team approval, current enrollment uses `aibuild-lab/agent-workforce`,
branch `student`, in the student's existing private `my-workbench`.

## Student steps

1. **No workbench yet:** complete [Essentials setup](START-HERE.md), then open
   the resulting `my-workbench` in your chosen app.
2. **Already set up:** open that same folder. Use the [update prompt](START-HERE.md#later-update-your-workbench)
   if its enrollment/update skills are old. Review and approve each replacement;
   preserve your customizations. Do not rerun setup.
3. Run `aibl-enroll` (slash in Claude, dollar sign in Codex), choose Workforce,
   inspect the additions and approve the exact preview. Your GitHub account
   must be able to read the repository; Learn visibility is a separate check.
4. Start a new session in that folder, run `aibl-workforce`, and follow the
   installed orientation. A real named-agent response verifies execution;
   seeing files alone does not.
5. Later, use `aibl-update`. It describes incoming changes and asks before
   applying them. A checkpoint to your private repository is a separate choice.

## Existing package installations

Use the same enrollment skill to compare the package files with the Git branch.
Identical overlaps need no replacement decision. Different files require a
specific keep, take, or combine choice before merging. Unfinished work, ignored
file collisions, wrong remotes, or unexpected file boundaries stop for review.
Keep existing settings, personal folders, root guidance and package receipts.
Once connected by Git, old package hashes describe history; do not run package
repair/update against the Git-managed course files.

## Routing and troubleshooting

`course-options.json` explicitly declares Workforce's current `enrollment`
repository and branch. Its `publisher`, `release_product`, and `adopt_skill`
remain the historical package interface. An older retained registry without
`enrollment` must not override the current skill's Git destination. Do not pull
or rewrite retained installers to change that history. Historical `enroll.py`
package commands below remain available only for their original pinned routes.

- Wrong folder: open `my-workbench`, not the installer or a course-source clone.
- Missing skill: use the official update prompt, then start a new session.
- Repository unavailable: inspect the signed-in GitHub username and contact the
  course team yourself. A 404 does not establish invitation timing.
- Missing student branch or failed fetch: stop; never enroll from main or a stale ref.
- Existing customizations: preview choices; never automatically stash or discard.
- Agent not discovered: retain the error and installed revision for support;
  do not copy agents into global folders as an improvised repair.

See [the team review packet](docs/essentials-workforce-review.md) for evidence,
remaining acceptance checks and proposed rollout. Nothing is merged or activated
by preparing these PRs.

---

# Historical verified-package bridge

The following procedure retains its original independently admitted distribution
contract. It is not the current Git-enrollment instruction.


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
