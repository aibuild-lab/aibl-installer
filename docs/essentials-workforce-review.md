# Essentials to Workforce: team review

Status: **unmerged review candidate; no cutover authorized by this packet**.
Primary: [installer #21](https://github.com/aibuild-lab/aibl-installer/pull/21).
Companion: [template #8](https://github.com/aibuild-lab/my-workbench-template/pull/8).
Module 1: [Internal #73](https://github.com/aibuild-lab/agent-native-workforce-internal/pull/73),
stacked on Tyler #70. Lesson prompts: [Learn #507](https://github.com/aibuild-lab/aibuildlab-com/pull/507),
stacked on content-review #504. Both remain unmerged.

## Student outcome and source boundaries

Before: an Essentials student could receive Git enrollment instructions while
an older installer registry redirected them toward a different package publisher.
An already-added remote could also hide unfinished enrollment.
After: current native skills use `agent-workforce/student`, check actual access,
preview changes and preserve customizations. Retained package IDs and engines
keep their original semantics. Git adoption makes package receipts historical;
package repair is not used against subsequently updated Git files.

Installer owns the public handoff, update prompt and explicit `enrollment` registry
field. Template owns paired Claude/Codex skills and the read-only update hook.
Internal owns the eight-agent package, teaching and component records. No course
payloads, raw calls, personal work or credentials belong in this public PR.
No full #69/#7 graft: version summaries may read reviewed component records, but
missing versions stay unknown, and publication checks are not bypassed. No global
agent links or copies are installed by enrollment/update.

## Review cases

| Case | Evidence/status |
|---|---|
| Git destination distinct from historical package identity | PASS: installer registry contract regression |
| Fresh workbench fixture joins student branch | PASS: template real-Git rehearsal |
| Package-style overlapping files join Git, receipts preserved | PASS: synthetic real-Git rehearsal; not a real package acceptance run |
| Repeated enrollment | PASS: no extra commit in rehearsal |
| Ordinary update preserves Chief display name | PASS: real-Git fixture |
| Forced conflict, cancellation, explicit name-preserving combination | PASS: real-Git fixture |
| Personal files and settings preserved | PASS in synthetic enrollment/update fixture |
| Wrong program remote / unrelated remote | PASS: executable update-hook check |
| Older workbench refresh with keep/take choices | PASS: real-Git core-refresh fixture and existing choice regression |
| Missing access, wrong folder, dirty tree, ignored collision | Source stop rules present; native agent adherence NOT_RUN |
| Real Essentials setup record through Git adoption | BLOCKED: no designated student-level test account/workbench in this lane |
| GitHub cohort access and Learn visibility | NOT_RUN with student identity; administrator readability is not student proof |
| macOS Claude and Codex discovery and first job | Module 1 supplies prepared-workbench evidence; transition acceptance remains NOT_RUN |
| Windows Claude and Codex transition | BLOCKED: no native Windows test surface in this lane |
| Student screenshots | NOT_RUN: capture from the actual qualified app journey; do not use mockups as evidence |

Automated fixtures simulate account and program boundaries. They establish Git
behavior only. No synthetic Essentials record counts as ordinary installation.
The native checklist in WORKFORCE-HANDOFF.md is the review copy for the LMS;
no production LMS files are changed in this lane.

## Review and rollout order (proposal, not executed)

1. Review these two PRs and the Module 1 dependency together. Resolve source
   validation and package-closure failures; require actual source/projection IDs.
2. Qualify the local assembled course with real setup records, both apps and both
   operating systems. Capture redacted screenshots of folder selection, preview,
   conflict choices, restart, discovery and first response. Record account access
   and Learn visibility separately, without granting access in the test.
3. After explicit team acceptance, publish/read back the reviewed course revision
   through Internal's owning publication procedure. Do not bypass rights, private
   file filters, version reviews or allowed-root checks.
4. Land the template and installer changes as a coordinated cutover; the template
   has a safe official-table fallback when older retained registries lack the new
   field. Update the matching LMS handoff through its own reviewed deployment.
5. Observe a fresh Essentials student, an older workbench, and a package-enrolled
   student taking the first Git update before calling the transition ready.

## Recovery

Before committing, cancel an approved but unfinished merge with `git merge --abort`
from the previously clean tree. Preserve uncommitted work if unexpected changes
appear. After a committed update, preview a revert of that merge against the
recorded parent; require a new student decision and keep later student commits.
Never reset history or delete package receipts. If rollout is held, leave the
unmerged PRs intact; do not change active student branches or historical releases.

## Evidence binding

Module review export: source `d113873d87309e246f15120ef37b4993392dd391`, wrapper
`e1644bc96edace23b7c254d7e242222370d01c80`, source-plan SHA-256
`7c5a422b1af2cfb6bb20fe0cfd4084603210272f937f36645523e77097f56d3c`.
The local export is bound externally; private payloads are not copied into this
public repository. Its owner reports 432 verified payload files, installed=false,
native_qualified=false. Transition review independently checks every declared
file hash and required opening files. This is a local review assembly only.

The newer Internal #73 metadata correction at `251124d` adds the missing
sample-fetch inventory row. Family checks now reach the remaining missing or
invalid reviewed edition for `aibl-agent-setup`; this is a release hold, not
permission to assign an arbitrary version. Board-server 400/201 is a separate
reported full-suite failure. Newer source requires a newly bound export before
rollout; the earlier export above is not silently relabeled as the newer source.

Learn prompt source: `a96428b6e108932b64776a0bf0eb32a56ca02e23`.
Native orientation in both clients is reported by the Module 1 owner; the full
first-job result and transition qualification remain separate pending evidence.

Local checks: installer registry regression; template three-test real-Git
rehearsal, existing shell choice regression, client skill byte parity and Node
syntax check. Required full installer validation is recorded in the PR with
its exact tested source commit. Missing device/account evidence remains a hold.
