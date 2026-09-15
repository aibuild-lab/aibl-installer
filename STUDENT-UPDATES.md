# Student-owned update operations

Updates use a newly approved distribution, never polling or a mutable latest
pin. Obtain its verified candidate trio using `scripts/frozen_family.py` and
include every currently installed product. First-time program enrollment uses
the separate guided preview route in STANDALONE-WORKBENCH.md.

From the exact retained installer, request a portable unique operation ID and
run `scripts/student_updates.py prepare --workbench WORKBENCH --operation ID
--family-lock LOCK --family-sha256 INDEPENDENT_DIGEST --family-bundles BUNDLES`.
Before preparation, offer an optional selective `aibl-checkpoint`. Do not stage
all work or require unfinished work to be committed. The preparation worktree
lives outside the active workbench, so unaccepted skills are not discoverable.
Initial enrollment can still be local and uncommitted. The remote may contain
an older subset of installed packages only when its corresponding pins match
the local installed pins exactly. The grouped PR includes those first-enrolled
package files as well as the reviewed update; no extra checkpoint is required.

Inspect the returned exact package set and complete candidate diff. Then run
`propose --workbench WORKBENCH --operation ID` with the same script. It reconciles
the exact branch and creates at most one grouped PR in the student's own private
repository. Faculty have no routine review or merge role.

Only after the student approves the exact recorded PR head, run
`approve-and-merge --workbench WORKBENCH --operation ID --approved-head SHA`.
Remote base/head changes require fresh review. An uncertain response is resolved
by reading the same PR, not issuing a replacement. Then run
`synchronize --workbench WORKBENCH --operation ID`.

Synchronization verifies the actual merge graph and tree before fast-forwarding.
Close active agent sessions first. Any staged work, changed local HEAD, pending
package/learning recovery or another package writer pauses synchronization.
The tool saves exact current supplied bytes and modes, including the family
marker, under `.aibl-local/update-sync/ID/` before temporarily normalizing only
those reviewed supplied paths to their tracked HEAD state. This lets the
approved fast-forward include previously uncommitted enrollment without
staging student work. An immutable journal precedes any normalization. Seed
files, personal context, custom skills and local learning are never normalized.
The bound `.aibl-local/student-update-sync.json` marker blocks package
enrollment, repair, rollback and other update preparation across process
restarts until this same synchronization completes. Its removal follows the
durable `local_synchronized` record, and a retry reconciles an interrupted
removal without repeating the file transition. Do not delete this marker.
Retries reconcile before/tracked states during normalization and the exact
merged state after a lost Git response. An ordinary failed merge restores the
saved enrollment bytes when no later edit or partial Git transition prevents
that safe restoration. A partial Git index transition or lock remains held
for diagnosis, never reset or deleted by this tool.
Changed supplied files, new ignored collisions, unpushed divergence or a later
remote revision stop with all work retained. No reset, stash, force push or
automatic conflict resolution is used. After a remote merge or local-sync
interruption, resume the same operation. Once synchronized, open a fresh session
in the selected app, discover the capabilities and perform the first action.
`local_synchronized` is not native verification or student acceptance.

After that actual walkthrough, an observer may explicitly record its result:

```text
python scripts/student_updates.py record-verification --workbench WORKBENCH --operation ID \
  --observation PRIVATE_OBSERVATION_JSON --observation-sha256 INDEPENDENT_SHA256
```

The observation must use this exact shape (values below are illustrative, not
usable evidence):

```json
{
  "schema_version": "aibl.native-update-observation/v1",
  "operation": "example-operation",
  "repository": "student/my-workbench",
  "local_revision": "EXACT_LOCAL_SYNCHRONIZED_COMMIT",
  "family_sha256": "EXACT_OPERATION_FAMILY_SHA256",
  "observer": "The person or external observer supplying this report",
  "observed_at": "2026-09-14T00:00:00Z",
  "app": {"id": "codex", "version": "EXACT_OBSERVED_VERSION"},
  "os": {"name": "OBSERVED_OS", "version": "EXACT_OBSERVED_VERSION"},
  "fresh_session": true,
  "discovered_skills": ["aibl-enroll", "aibl-personalize", "aibl-checkpoint"],
  "first_action": {
    "status": "passed",
    "description": "A short sanitized account of the actual first action",
    "evidence": {"path": "/absolute/private/evidence-file", "sha256": "EVIDENCE_SHA256"}
  }
}
```

Use `claude` or `codex` for the selected app. Report every installed supplied
skill for that app, including program skills when present. The fresh-session
assertion, observer identity, app/OS versions and action outcome come from the
caller, not automated native inspection. Keep evidence private, free of secrets,
outside Git; retain the nonsymlink evidence file and observation JSON. The JSON
is limited to 1 MiB, and evidence to 32 MiB. Supply its independently checked
digest explicitly. This command checks hashes, exact operation/family/revision,
current origin, branch and managed bytes. Missing or failed observations leave
the operation pending. Repeating the same observation is idempotent; replacing
a recorded observation with another is a conflict requiring review.

The resulting `observation_recorded` stage means only `caller_observation_recorded`, with
provenance retained in the local receipt. It explicitly sets
`automated_native_proof: false` and `human_acceptance: not_recorded`. It does not
execute the app, independently establish that the reported session occurred,
grant student acceptance, or qualify another app, OS, revision or workbench.

Local learning data is outside Git. Use `scripts/local_learning_backup.py` for
an explicitly private backup/restore; neither a PR nor Git rollback restores
that state. Never copy local learning data into an update PR.

Operation receipts live in `.aibl-local/updates/`; retain them and their isolated
preparation worktrees until the operation is complete and recovery is no longer
needed. Package history is reconciled only after the exact local merge. This
source contains no unattended automation or fleet-wide student access.
